"""Bounded, derived lifecycle graph. Queries never consume a saved projection.

Reads validated board records under their existing lock; never dispatches work,
changes source records, calls Git, executes project code or contacts a service.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import time
import types
from collections import deque
from contextlib import contextmanager
from pathlib import Path

SCHEMA = "sf-trace/1"
MAX_FILES = 1024
MAX_FILE_BYTES = 1024 * 1024
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_NODES = 10000
MAX_EDGES = 20000
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{40}")
RELATIONS = {"depends-on", "covers", "implements", "verifies", "reviews", "supersedes", "deployed-as"}
QUESTIONS = ("ready", "blocked", "unproved", "stale", "shipped", "decisions", "path")


class TraceError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()


def token(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def text(value):
    return value[:1000] if isinstance(value, str) else None


def directory_names(path):
    names = []
    with os.scandir(path) as entries:
        for entry in entries:
            names.append(entry.name)
            if len(names) > MAX_FILES:
                raise TraceError("input file limit exceeded")
    return sorted(names)


def load_helper(name):
    # Executing trusted shipped source directly never writes a sibling __pycache__.
    path = Path(__file__).with_name(f"{name}.py")
    module = types.ModuleType(f"sf_trace_{name}")
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)  # noqa: S102 - trusted shipped helper only
    return module


def roadmap_module():
    module = load_helper("roadmap")
    module._STATE = load_helper("state")
    return module


class Inputs:
    """Bounded descriptor-relative captures; neither symlinks nor special files open."""

    def __init__(self, root):
        self.root = root
        self.data = {}
        self.directories = {}
        self.identities = {}
        self.total = 0
        self.root_identity = None

    def parts(self, relative):
        if not isinstance(relative, str) or not relative or len(relative) > 1000:
            raise TraceError("invalid source path")
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise TraceError("source path must name an entry inside the workspace")
        return path.parts

    @contextmanager
    def parent(self, relative, create=False):
        parts = self.parts(relative)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        descriptor = os.open("/", flags)
        try:
            for part in self.root.parts[1:]:
                child = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            identity = os.fstat(descriptor)
            identity = (identity.st_dev, identity.st_ino)
            if self.root_identity is None:
                self.root_identity = identity
            elif identity != self.root_identity:
                raise TraceError("workspace changed during graph derivation; retry")
            for part in parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                child = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            yield descriptor, parts[-1]
        except OSError as exc:
            raise TraceError("source or output inaccessible; symlink or special entry refused") from exc
        finally:
            os.close(descriptor)

    def path(self, relative):
        self.parts(relative)
        # Only a lexical label. All IO goes through descriptor-relative operations.
        return self.root / relative

    def inspect(self, relative):
        try:
            with self.parent(relative) as (parent, name):
                try:
                    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    return None
                if stat.S_ISLNK(info.st_mode):
                    raise TraceError("symlink source or output refused")
                return info
        except TraceError as exc:
            if isinstance(exc.__cause__, FileNotFoundError):
                return None
            raise

    def capture(self, relative):
        try:
            with self.parent(relative) as (parent, name):
                try:
                    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                except FileNotFoundError:
                    return None, None
                try:
                    info = os.fstat(descriptor)
                    if not stat.S_ISREG(info.st_mode):
                        raise TraceError("source must be a regular file")
                    if info.st_size > MAX_FILE_BYTES:
                        raise TraceError("source exceeds file byte limit")
                    with os.fdopen(descriptor, "rb", closefd=False) as stream:
                        payload = stream.read(MAX_FILE_BYTES + 1)
                    if len(payload) > MAX_FILE_BYTES:
                        raise TraceError("source exceeds file byte limit")
                    return payload, (info.st_dev, info.st_ino)
                finally:
                    os.close(descriptor)
        except TraceError as exc:
            if isinstance(exc.__cause__, FileNotFoundError):
                return None, None
            raise

    def read(self, relative, required=True):
        self.parts(relative)
        relative = Path(relative).as_posix()
        if relative not in self.data:
            payload, identity = self.capture(relative)
            self.data[relative] = payload
            self.identities[relative] = identity
            self.total += len(payload or b"")
            if len(self.data) > MAX_FILES or self.total > MAX_INPUT_BYTES:
                raise TraceError("input file or total byte limit exceeded")
        payload = self.data[relative]
        if payload is None and required:
            raise TraceError(f"missing source: {relative}")
        return payload

    def json(self, relative, required=True):
        raw = self.read(relative, required)
        if raw is None:
            return None
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise TraceError(f"invalid JSON source: {relative}") from exc
        if not isinstance(value, dict):
            raise TraceError(f"source must contain an object: {relative}")
        return value

    def listing(self, relative):
        try:
            with self.parent(relative) as (parent, name):
                try:
                    descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                except FileNotFoundError:
                    return None
                try:
                    return directory_names(descriptor)
                finally:
                    os.close(descriptor)
        except TraceError as exc:
            if isinstance(exc.__cause__, FileNotFoundError):
                return None
            raise

    def entries(self, relative, suffix):
        names = self.listing(relative)
        self.directories[relative] = names
        return [(Path(relative) / name).as_posix() for name in names or [] if Path(name).suffix == suffix]

    def anchor(self, relative, pointer="", line=None):
        raw = self.read(relative, required=False)
        value = {"path": relative, "sha256": digest(raw) if raw is not None else None}
        value["line" if line else "pointer"] = line if line else pointer
        return value

    def verify(self):
        for relative, names in self.directories.items():
            if names != self.listing(relative):
                raise TraceError("input directory changed during graph derivation; retry")
        for relative, captured in self.data.items():
            current, identity = self.capture(relative)
            if current != captured or identity != self.identities[relative]:
                raise TraceError("inputs changed during graph derivation; retry")

    def manifest(self):
        files = [{"path": path, "kind": "file", "sha256": digest(raw) if raw is not None else None}
                 for path, raw in sorted(self.data.items())]
        directories = [{"path": path, "kind": "directory", "sha256": digest(encoded(names))}
                       for path, names in sorted(self.directories.items())]
        return sorted(files + directories, key=lambda item: (item["path"], item["kind"]))


class SnapshotPath:
    """The board's existing validators see only captured bytes and directory lists."""

    def __init__(self, inputs, relative=""):
        self.inputs, self.relative = inputs, relative

    def __truediv__(self, name):
        return SnapshotPath(self.inputs, str(Path(self.relative) / name))

    @property
    def name(self):
        return Path(self.relative).name

    @property
    def stem(self):
        return Path(self.relative).stem

    def is_file(self):
        return self.inputs.data.get(self.relative) is not None

    def is_dir(self):
        return self.inputs.directories.get(self.relative) is not None

    def read_text(self):
        return self.inputs.data[self.relative].decode("utf-8")

    def glob(self, pattern):
        return [self / name for name in self.inputs.directories.get(self.relative) or []
                if name.endswith(".json")]

    def __lt__(self, other):
        return self.relative < other.relative


@contextmanager
def board_lock(inputs, board, create):
    """Anchor the same advisory lock without write-capable query access."""
    with inputs.parent(".software-factory/board.lock", create=create) as (parent, name):
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                                 | (os.O_CREAT if create else 0), 0o600, dir_fd=parent)
        except FileNotFoundError as exc:
            raise TraceError("board lock is absent; run an explicit build before querying") from exc
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise TraceError("board lock must be a regular file")
            deadline = time.monotonic() + board.state_module().LOCK_WAIT_SECONDS
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TraceError("board is busy; retry after its writer finishes") from None
                    time.sleep(0.05)
            inputs.read(".software-factory/board.lock")
            if inputs.identities[".software-factory/board.lock"] != (info.st_dev, info.st_ino):
                raise TraceError("board lock changed during acquisition; retry")
            yield
        finally:
            os.close(descriptor)


def captured_projection(board, inputs, root, config, relative, pointer):
    claims = {}
    if pointer is not None:
        if pointer.get("version") != 1 or not isinstance(pointer.get("run"), str):
            raise TraceError("ownership authority is invalid; reconcile before graph derivation")
        run = inputs.json(pointer["run"])
        try:
            board.state_module().validate_state(run)
        except board.state_module().StateError as exc:
            raise TraceError("ownership authority is invalid; reconcile before graph derivation") from exc
        claims = run["claims"]
    read_record, claims_reader = board.read_record, board.claims_or_empty
    try:
        board.read_record = lambda path: inputs.json(path.relative, required=False)
        board.claims_or_empty = lambda workspace: (claims, None)
        return board.compute_roadmap(root, config, SnapshotPath(inputs, relative))
    finally:
        board.read_record, board.claims_or_empty = read_record, claims_reader


class Graph:
    def __init__(self, inputs):
        self.inputs = inputs
        self.nodes = {}
        self.edges = []
        self.diagnostics = []
        self.pending = []

    def node(self, identity, kind, label, anchor, **facts):
        if identity not in self.nodes:
            self.nodes[identity] = {"id": identity, "type": kind, "label": text(label),
                                    "provenance": [anchor], **facts}
        elif anchor not in self.nodes[identity]["provenance"]:
            self.nodes[identity]["provenance"].append(anchor)
        for key, value in facts.items():
            self.nodes[identity].setdefault(key, value)
        if len(self.nodes) > MAX_NODES:
            raise TraceError("graph node limit exceeded")
        return identity

    def edge(self, source, relation, target, anchor, **facts):
        self.edges.append({"source": source, "relation": relation, "target": target,
                           "provenance": [anchor], **facts})
        if len(self.edges) > MAX_EDGES:
            raise TraceError("graph edge limit exceeded")

    def diagnostic(self, kind, anchor, **facts):
        self.diagnostics.append({"kind": kind, "provenance": [anchor], **facts})
        if len(self.diagnostics) > MAX_EDGES:
            raise TraceError("diagnostic limit exceeded")

    def references(self, source, record, path, pointer):
        """Only explicitly typed extension links; titles never imply a relationship."""
        links = record.get("links", [])
        if not isinstance(links, list):
            raise TraceError("links must be an array")
        for index, link in enumerate(links):
            if not isinstance(link, dict) or link.get("relation") not in RELATIONS \
                    or not isinstance(link.get("target"), str):
                raise TraceError("invalid explicit lifecycle link")
            self.pending.append((source, link["relation"], link["target"],
                                 self.inputs.anchor(path, f"{pointer}/links/{index}")))

    def finish(self):
        for source, relation, target, anchor in self.pending:
            if target not in self.nodes:
                self.diagnostic("dangling-reference", anchor, source=source, target=text(target))
            else:
                self.edge(source, relation, target, anchor, basis="explicit-declaration")
        for edge in self.edges:
            if edge["source"] not in self.nodes or edge["target"] not in self.nodes:
                self.diagnostic("dangling-reference", edge["provenance"][0],
                                source=edge["source"], target=edge["target"])
        # Cycles of code relationships are factual; only prerequisite/supersession DAGs reject.
        for relation in ("depends-on", "supersedes"):
            adjacency = {}
            for edge in self.edges:
                if edge["relation"] == relation and edge["target"] in self.nodes:
                    adjacency.setdefault(edge["source"], set()).add(edge["target"])
            remaining = set(adjacency) | {target for values in adjacency.values() for target in values}
            indegree = dict.fromkeys(remaining, 0)
            for values in adjacency.values():
                for target in values:
                    indegree[target] += 1
            ready = deque(sorted(node for node, degree in indegree.items() if not degree))
            while ready:
                current = ready.popleft()
                remaining.remove(current)
                for target in sorted(adjacency.get(current, [])):
                    indegree[target] -= 1
                    if not indegree[target]:
                        ready.append(target)
            if remaining:
                raise TraceError(f"{relation} cycle rejected")
        for node in self.nodes.values():
            node["provenance"].sort(key=lambda item: json.dumps(item, sort_keys=True))
        return {"schema": SCHEMA, "nodes": sorted(self.nodes.values(), key=lambda node: node["id"]),
                "edges": sorted(self.edges, key=lambda edge: json.dumps(edge, sort_keys=True)),
                "diagnostics": sorted(self.diagnostics, key=lambda item: json.dumps(item, sort_keys=True))}


def receipt_node(graph, story, name, receipt, path):
    inputs = graph.inputs
    pointer = f"/receipts/{token(name)}"
    anchor = inputs.anchor(path, pointer)
    identity = f"receipt:{story['id']}:{name}"
    expected = story.get("merged_sha") if story["status"] == "done" else story.get("review_subject_sha")
    subject = receipt["subject_sha"]
    freshness = "current" if expected == subject else "stale" if expected else "unknown"
    integrity = "unknown"
    artifact = receipt.get("artifact")
    if isinstance(artifact, str):
        payload = inputs.read(artifact, required=False)
        expected_hash = receipt.get("artifact_sha256")
        if payload is None:
            integrity = "missing"
        elif isinstance(expected_hash, str):
            integrity = "matched" if digest(payload) == expected_hash else "mismatch"
        graph.node(f"surface:{artifact}", "surface", artifact, inputs.anchor(artifact), exists=payload is not None)
        graph.edge(identity, "records", f"surface:{artifact}", anchor, basis="artifact-reference")
    status = receipt.get("status") or receipt.get("verdict") or receipt.get("result")
    graph.node(identity, "receipt", name, anchor, subject_sha=text(subject), freshness=freshness,
               artifact_integrity=integrity, reported_status=text(status), story=story["id"])
    graph.edge(f"story:{story['id']}", "records", identity, anchor)
    if SHA.fullmatch(subject):
        graph.node(f"commit:{subject}", "commit", subject, inputs.anchor(path, pointer + "/subject_sha"))
        graph.edge(identity, "subject", f"commit:{subject}", anchor)
    targets = receipt.get("verifies", [])
    if not isinstance(targets, list) or not all(isinstance(target, str) for target in targets):
        raise TraceError("receipt verifies must be an array of graph IDs")
    for index, target in enumerate(targets):
        proof = status == "pass" and freshness == "current" and integrity == "matched"
        graph.edge(identity, "verifies", target, inputs.anchor(path, pointer + f"/verifies/{index}"),
                   structural_support=proof, basis="recorded-check-not-effect-authentication")
    graph.references(identity, receipt, path, pointer)
    for key in ("decision_ref", "decision"):
        if isinstance(receipt.get(key), str):
            decision_reference(graph, identity, receipt[key], path, pointer + "/" + key)
    deployed = receipt.get("deployed_sha")
    if isinstance(deployed, str) and SHA.fullmatch(deployed):
        deployment = graph.node(f"deployment:{story['id']}:{name}", "deployment", name, anchor,
                                reported_sha=deployed, environment=text(receipt.get("environment")))
        graph.node(f"commit:{deployed}", "commit", deployed, anchor)
        graph.edge(f"commit:{deployed}", "deployed-as", deployment, anchor, basis="recorded-report")
        graph.edge(identity, "records", deployment, anchor)
    if isinstance(receipt.get("effect"), str):
        effect = graph.node(f"effect:{story['id']}:{name}", "effect", receipt["effect"], anchor)
        graph.edge(identity, "records", effect, anchor, basis="recorded-report")


def decision_reference(graph, source, reference, path, pointer):
    anchor = graph.inputs.anchor(path, pointer)
    target = f"decision:{reference}"
    if target not in graph.nodes:
        payload = graph.inputs.read(reference, required=False)
        graph.node(target, "decision", reference, anchor, exists=payload is not None,
                   authenticated=False)
        if payload is None:
            graph.diagnostic("missing-decision-source", anchor, reference=text(reference))
    graph.edge(source, "records", target, anchor, basis="decision-reference-not-approval")


def add_crawl(graph, relative):
    report = graph.inputs.json(relative)
    if report.get("schema") != "sf-crawl/1":
        raise TraceError("unsupported crawl schema")
    python = report.get("python")
    if not isinstance(python, dict):
        raise TraceError("invalid crawl Python section")
    modules = python.get("modules")
    if not isinstance(modules, list) or len(modules) > MAX_NODES:
        raise TraceError("invalid or oversized crawl module list")
    names = {}
    functions = {}
    for index, module in enumerate(modules):
        if not isinstance(module, dict) or not isinstance(module.get("name"), str) \
                or not isinstance(module.get("path"), str):
            raise TraceError("invalid crawl module")
        anchor = graph.inputs.anchor(relative, f"/python/modules/{index}")
        payload = graph.inputs.read(module["path"], required=False)
        identity = graph.node(f"surface:{module['path']}", "surface", module["path"], anchor,
                              exists=payload is not None, analysis_binding="unverified")
        if payload is not None:
            graph.node(identity, "surface", module["path"], graph.inputs.anchor(module["path"], line=1))
        else:
            graph.diagnostic("missing-code-source", anchor)
        if module["name"] in names:
            names[module["name"]] = None
            graph.diagnostic("ambiguous-module-name", anchor, name=text(module["name"]))
        else:
            names[module["name"]] = identity
        calls = module.get("calls", [])
        if not isinstance(calls, list) or not all(isinstance(call, dict) for call in calls):
            raise TraceError("invalid crawl call records")
        for position, call in enumerate(calls):
            if not isinstance(call.get("function"), str):
                raise TraceError("invalid crawl function")
            target = graph.node(f"function:{module['path']}#{call['function']}", "surface", call["function"],
                                graph.inputs.anchor(relative, f"/python/modules/{index}/calls/{position}"),
                                analysis_binding="unverified")
            key = f"{module['name']}.{call['function']}"
            functions[key] = None if key in functions else target
    for index, module in enumerate(modules):
        imports = module.get("internal_imports", [])
        if not isinstance(imports, list) or not all(isinstance(item, str) for item in imports):
            raise TraceError("invalid crawl import list")
        for position, target in enumerate(imports):
            anchor = graph.inputs.anchor(relative, f"/python/modules/{index}/internal_imports/{position}")
            if names.get(target):
                graph.edge(f"surface:{module['path']}", "imports", names[target], anchor,
                           basis="reported-static-analysis", current_source_binding="unknown")
            else:
                graph.diagnostic("unresolved-import", anchor, target=text(target))
        for position, call in enumerate(module.get("calls", [])):
            resolved = call.get("resolved", {})
            if not isinstance(resolved, dict) or not all(isinstance(value, str) for value in resolved.values()):
                raise TraceError("invalid resolved crawl calls")
            for name, target in sorted(resolved.items()):
                anchor = graph.inputs.anchor(relative, f"/python/modules/{index}/calls/{position}/resolved/{token(name)}")
                if functions.get(target):
                    graph.edge(f"function:{module['path']}#{call['function']}", "calls", functions[target],
                               anchor, basis="reported-static-analysis", current_source_binding="unknown")
                else:
                    graph.diagnostic("unresolved-call", anchor, target=text(target))
    graph.diagnostic("crawl-binding-unverified", graph.inputs.anchor(relative),
                     reason="crawl v1 has no per-source content hashes; current relationship freshness is unknown")


def derive(workspace, crawl=None, output=None):
    root = Path(workspace).resolve()
    if not root.is_dir():
        raise TraceError("workspace must be a directory")
    inputs = Inputs(root)
    board = roadmap_module()
    inputs.read(board.CONFIG_FILE, required=False)
    try:
        with board_lock(inputs, board, create=output is not None):
            config = board.board_config(SnapshotPath(inputs))
            parts = inputs.parts(config["dir"])
            if len(parts) < 2 or parts[-1] == "context":
                raise TraceError("board.dir must be a dedicated board directory")
            relative = Path(config["dir"]).as_posix()
            for name in ("streams.json", "meta.json"):
                inputs.json(f"{relative}/{name}")
            records = []
            identities = set()
            for kind, validator in (("epics", board.validate_epic), ("stories", board.validate_story)):
                for path in inputs.entries(f"{relative}/{kind}", ".json"):
                    record = inputs.json(path)
                    reason = validator(record)
                    if reason:
                        raise TraceError(f"invalid {kind} record: {path}")
                    identity = (kind, record["id"])
                    if identity in identities:
                        raise TraceError("duplicate board identity")
                    identities.add(identity)
                    records.append((kind, path, record))
            pointer = inputs.json(".software-factory/active.json", required=False)
            if pointer is not None:
                run = pointer.get("run")
                if not isinstance(run, str):
                    raise TraceError("invalid active run reference")
                inputs.read(run)
            projection = captured_projection(board, inputs, root, config, relative, pointer)
            inputs.verify()
            if any(problem.get("file") == "active.json" for problem in projection["problems"]):
                raise TraceError("ownership authority is invalid; reconcile before graph derivation")
            graph = Graph(inputs)
            source_paths = {(kind, record["id"]): path for kind, path, record in records}
            for problem in projection["problems"]:
                path = source_paths.get(("stories", problem.get("story")), f"{relative}/streams.json")
                graph.diagnostic("board-problem", inputs.anchor(path),
                                 detail={key: text(value) for key, value in problem.items()})
            for category, observations in projection["diagnostics"].items():
                for observation in observations:
                    path = source_paths.get(("stories", observation.get("story")))
                    path = path or source_paths.get(("epics", observation.get("epic")))
                    graph.diagnostic("board-diagnostic", inputs.anchor(path or f"{relative}/streams.json"),
                                     category=category)
            for kind, path, record in records:
                identity = f"{'epic' if kind == 'epics' else 'story'}:{record['id']}"
                graph.node(identity, "epic" if kind == "epics" else "story", record["title"],
                           inputs.anchor(path), status=record["status"])
            for kind, path, record in records:
                identity = f"{'epic' if kind == 'epics' else 'story'}:{record['id']}"
                for index, requirement in enumerate(record["covers"]):
                    anchor = inputs.anchor(path, f"/covers/{index}")
                    graph.node(f"requirement:{requirement}", "requirement", requirement, anchor)
                    graph.edge(identity, "covers", f"requirement:{requirement}", anchor, basis="declared-coverage")
                graph.references(identity, record, path, "")
                if kind == "epics":
                    checkpoint = record.get("acceptance")
                    if isinstance(checkpoint, dict):
                        target = graph.node(f"checkpoint:epic:{record['id']}", "checkpoint", "Recorded epic acceptance",
                                            inputs.anchor(path, "/acceptance"), authenticated=False)
                        graph.edge(identity, "records", target, inputs.anchor(path, "/acceptance"))
                    continue
                graph.edge(identity, "part-of", f"epic:{record['epic']}", inputs.anchor(path, "/epic"))
                for index, prerequisite in enumerate(record["after"]):
                    target = f"epic:{prerequisite['epic']}" if isinstance(prerequisite, dict) else f"story:{prerequisite}"
                    graph.edge(identity, "depends-on", target, inputs.anchor(path, f"/after/{index}"))
                for index, scope in enumerate(record.get("scope", [])):
                    anchor = inputs.anchor(path, f"/scope/{index}")
                    target = inputs.inspect(scope)
                    payload = None
                    if target is not None and stat.S_ISDIR(target.st_mode):
                        inputs.entries(scope, "")
                        exists = inputs.directories[scope] is not None
                        graph.diagnostic("directory-scope-unmeasured", anchor)
                    else:
                        payload = inputs.read(scope, required=False)
                        exists = payload is not None
                    graph.node(f"surface:{scope}", "surface", scope, anchor, exists=exists)
                    if payload is not None:
                        graph.node(f"surface:{scope}", "surface", scope, inputs.anchor(scope, line=1))
                    graph.edge(identity, "scope", f"surface:{scope}", anchor, basis="declared-scope-not-implementation")
                merged = record.get("merged_sha")
                if isinstance(merged, str) and SHA.fullmatch(merged):
                    graph.node(f"commit:{merged}", "commit", merged, inputs.anchor(path, "/merged_sha"))
                    graph.edge(f"commit:{merged}", "implements", identity, inputs.anchor(path, "/merged_sha"), basis="recorded-merge")
                if record.get("pr"):
                    target = graph.node(f"pr:{record['pr']}", "pr", record["pr"], inputs.anchor(path, "/pr"))
                    graph.edge(identity, "records", target, inputs.anchor(path, "/pr"))
                for name, receipt in sorted(record["receipts"].items()):
                    receipt_node(graph, record, name, receipt, path)
                for index, finding in enumerate(record.get("findings", [])):
                    if not isinstance(finding, dict):
                        raise TraceError("finding must be an object")
                    target = graph.node(f"finding:{record['id']}:{index}", "finding", finding.get("text"),
                                        inputs.anchor(path, f"/findings/{index}"))
                    graph.edge(identity, "records", target, inputs.anchor(path, f"/findings/{index}"))
            if pointer is not None:
                run_path = pointer["run"]
                run = inputs.json(run_path)
                for task, claim in sorted(run.get("claims", {}).items()):
                    anchor = inputs.anchor(run_path, f"/claims/{token(task)}")
                    target = graph.node(f"claim:{task}", "claim", claim.get("owner"), anchor,
                                        liveness="unknown")
                    graph.edge(target, "assigned-to", f"story:{task}", anchor)
                if run.get("checkpoint"):
                    graph.node("checkpoint:active", "checkpoint", "Active recovery context",
                               inputs.anchor(run_path, "/checkpoint"), authorization=False)
            decision_dir = ".software-factory/context/decisions"
            for path in inputs.entries(decision_dir, ".md"):
                raw = inputs.read(path)
                graph.node(f"decision:{path}", "decision", path, inputs.anchor(path, line=1),
                           authenticated=False, content_sha256=digest(raw))
            if crawl:
                add_crawl(graph, crawl)
            result = graph.finish()
            result["answers"] = answers(projection, result)
            inputs.verify()
            result["inputs"] = inputs.manifest()
            result["source_fingerprint"] = digest(encoded(result["inputs"]))
            result["limits"] = {"files": MAX_FILES, "file_bytes": MAX_FILE_BYTES,
                                "input_bytes": MAX_INPUT_BYTES, "nodes": MAX_NODES, "edges": MAX_EDGES}
            result["limitations"] = [
                "Declarations and recorded reports do not authenticate authority or observed effects.",
                "Structural receipt support is not an independent gate verdict.",
                "Directory scopes are not recursively inspected; code-map source bindings are unverified.",
            ]
            if len(encoded(result)) > MAX_OUTPUT_BYTES:
                raise TraceError("graph output byte limit exceeded")
            if output is not None:
                output = f"{relative}/lifecycle-graph.json" if output is True else output
                build_output(root, output, result, inputs)
            return result
    except (board.BoardError, board.state_module().StateError, OSError, RecursionError) as exc:
        raise TraceError("board derivation failed; reconcile sources before retrying") from exc


def answers(projection, graph):
    supported = {edge["target"] for edge in graph["edges"] if edge.get("structural_support")}
    receipts = [node for node in graph["nodes"] if node["type"] == "receipt"]
    return {
        "ready": projection["frontier"]["ready"],
        "blocked": {"waiting": projection["frontier"]["waiting_on_prereq"],
                    "blockers": projection["blockers"], "problems": projection["problems"]},
        "unproved": {"requirements": [node["id"] for node in graph["nodes"]
                                          if node["type"] == "requirement" and node["id"] not in supported],
                     "meaning": "No explicit current passing receipt with a matching local artifact digest; coverage alone is a declaration."},
        "stale": [node for node in receipts if node["freshness"] == "stale"
                  or node["artifact_integrity"] in ("missing", "mismatch")],
        "shipped": {"recorded_done": [{"story": story["id"], "board_status": story["status"],
                                       "recorded_merge_sha": story.get("merged_sha")}
                                      for story in projection["stories"] if story["status"] == "done"],
                    "shipping_verification": "not established by local board status",
                    "recorded_deployments": [node for node in graph["nodes"] if node["type"] == "deployment"]},
        "decisions": projection["decision_queue"],
    }


def find_path(graph, source, target):
    nodes = {node["id"] for node in graph["nodes"]}
    if source not in nodes or target not in nodes:
        return {"path": None, "reason": "unknown endpoint"}
    queue = deque([source])
    previous = {source: None}
    outgoing = {}
    for edge in graph["edges"]:
        outgoing.setdefault(edge["source"], []).append(edge)
    while queue:
        current = queue.popleft()
        if current == target:
            path = []
            while previous[current] is not None:
                edge = previous[current]
                path.append(edge)
                current = edge["source"]
            path.reverse()
            return {"path": path, "meaning": "Directed factual links; relation types retain their distinct semantics."}
        for edge in outgoing.get(current, []):
            if edge["target"] not in previous:
                previous[edge["target"]] = edge
                queue.append(edge["target"])
    return {"path": None, "reason": "no directed path"}


def build_output(root, relative, graph, inputs):
    relative = Path(relative).as_posix()
    path = inputs.path(relative)
    if path.name != "lifecycle-graph.json" or relative in {item["path"] for item in graph["inputs"]}:
        raise TraceError("output must be a derived lifecycle-graph.json, separate from sources")
    payload = encoded(graph)
    if len(payload) > MAX_OUTPUT_BYTES:
        raise TraceError("graph output byte limit exceeded")
    with inputs.parent(relative, create=True) as (parent, name):
        temporary = f".factory-trace-{secrets.token_hex(12)}"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            inputs.verify()
            with inputs.parent(relative) as (current_parent, current_name):
                old, current = os.fstat(parent), os.fstat(current_parent)
                if (old.st_dev, old.st_ino) != (current.st_dev, current.st_ino):
                    raise TraceError("output parent changed during graph derivation; retry")
                try:
                    target = os.stat(current_name, dir_fd=current_parent, follow_symlinks=False)
                except FileNotFoundError:
                    target = None
                if target is not None and not stat.S_ISREG(target.st_mode):
                    raise TraceError("symlink or special output refused")
                os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
        finally:
            try:
                os.unlink(temporary, dir_fd=parent)
            except FileNotFoundError:
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "query"))
    parser.add_argument("question", nargs="?", choices=QUESTIONS)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--crawl", help="workspace-relative existing sf-crawl JSON")
    parser.add_argument("--output", help="derived lifecycle-graph.json; defaults to the configured board directory")
    parser.add_argument("--from", dest="source")
    parser.add_argument("--to", dest="target")
    args = parser.parse_args(argv)
    try:
        if args.command == "build" and args.question is not None:
            parser.error("build does not take a query")
        if args.command == "query" and (args.question is None or args.output is not None):
            parser.error("query requires a question and does not write an output")
        graph = derive(args.workspace, args.crawl, (args.output or True) if args.command == "build" else None)
        if args.command == "build":
            print(f"trace: built {len(graph['nodes'])} nodes and {len(graph['edges'])} edges")
        else:
            if args.question is None:
                parser.error("query requires a question")
            result = find_path(graph, args.source, args.target) if args.question == "path" else graph["answers"][args.question]
            print(encoded({"schema": SCHEMA, "source_fingerprint": graph["source_fingerprint"],
                           "answer": result}).decode(), end="")
        return 0
    except (TraceError, ValueError, TypeError, KeyError) as exc:
        print(f"trace: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
