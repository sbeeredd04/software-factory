"""Derived trace views preserve source authority, provenance and uncertainty."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from test_board import SHA_A, SHA_B, Board

trace = support.helper("trace")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.board = Board(self)
        self.board.derive()
        self.root = self.board.root
        source = self.root / "src"
        source.mkdir()
        (source / "state.py").write_text("VALUE = 1\n")
        (source / "gate.py").write_text("VALUE = 2\n")

    def change_story(self, number, **fields):
        record = self.board.story(number)
        record.update(fields)
        write_json(self.board.story_file(number), record)

    def derive(self, crawl=None):
        return trace.derive(self.root, crawl)

    def node(self, graph, identity):
        return next(node for node in graph["nodes"] if node["id"] == identity)

    def snapshot(self):
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file() and ".git" not in path.parts}

    def passing_receipt(self):
        artifact = self.root / "proof.txt"
        artifact.write_text("observed fixture result\n")
        return {"subject_sha": SHA_A, "status": "pass", "artifact": "proof.txt",
                "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "verifies": ["requirement:R1"]}

    def test_all_seven_questions_keep_declarations_proof_and_shipping_distinct(self):
        receipt = self.passing_receipt()
        receipt.update(deployed_sha=SHA_A, effect="Fixture effect observed", environment="disposable")
        self.change_story(1, status="done", merged_sha=SHA_A, receipts={"check": receipt})
        second = self.board.epic_record(2)
        second["status"] = "awaiting-acceptance"
        write_json(self.board.epic_file(2), second)
        graph = self.derive()
        self.assertEqual([2], [entry["id"] for entry in graph["answers"]["ready"]])
        self.assertTrue(graph["answers"]["blocked"]["waiting"])
        self.assertNotIn("requirement:R1", graph["answers"]["unproved"]["requirements"])
        self.assertIn("requirement:R2", graph["answers"]["unproved"]["requirements"])
        self.assertEqual([], graph["answers"]["stale"])
        shipped = graph["answers"]["shipped"]
        self.assertEqual([{"story": 1, "board_status": "done", "recorded_merge_sha": SHA_A}],
                         shipped["recorded_done"])
        self.assertIn("not established", shipped["shipping_verification"])
        self.assertEqual(1, len(shipped["recorded_deployments"]))
        self.assertTrue(graph["answers"]["decisions"])
        path = trace.find_path(graph, "story:1", "requirement:R1")["path"]
        self.assertEqual("covers", path[0]["relation"])
        self.assertEqual("declared-coverage", path[0]["basis"])
        self.assertIsNone(trace.find_path(graph, "unknown", "story:1")["path"])
        self.assertIsNone(trace.find_path(graph, "requirement:R1", "story:1")["path"])

    def test_provenance_fingerprint_and_build_use_dirty_bytes_deterministically(self):
        graph = self.derive()
        self.assertEqual(graph, self.derive())
        for item in graph["nodes"] + graph["edges"]:
            self.assertTrue(item["provenance"])
            for anchor in item["provenance"]:
                raw = (self.root / anchor["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), anchor["sha256"])
                self.assertTrue("pointer" in anchor or "line" in anchor)
        old = graph["source_fingerprint"]
        (self.root / "src/state.py").write_text("VALUE = 3  # dirty input\n")
        self.assertNotEqual(old, self.derive()["source_fingerprint"])
        output = ".software-factory/context/board/lifecycle-graph.json"
        trace.derive(self.root, output=output)
        first = (self.root / output).read_bytes()
        trace.derive(self.root, output=output)
        self.assertEqual(first, (self.root / output).read_bytes())
        (self.root / output).unlink()
        trace.derive(self.root, output=output)
        self.assertEqual(first, (self.root / output).read_bytes())

    def test_query_reads_records_instead_of_saved_roadmap_and_does_not_write(self):
        self.board.roadmap_file().write_text("stale projection intentionally unusable\n")
        before = self.snapshot()
        result = support.run("trace", "query", "ready", "--workspace", self.root)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([1], [entry["id"] for entry in json.loads(result.stdout)["answer"]])
        self.assertEqual(before, self.snapshot())

    def test_query_with_missing_lock_creates_no_files_or_directories(self):
        lock = self.root / ".software-factory/board.lock"
        lock.unlink()
        before = self.snapshot()
        directories = {path.relative_to(self.root).as_posix() for path in self.root.rglob("*") if path.is_dir()}
        result = support.run("trace", "query", "ready", "--workspace", self.root)
        self.assertEqual(2, result.returncode)
        self.assertIn("board lock is absent", result.stderr)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(directories, {path.relative_to(self.root).as_posix()
                                      for path in self.root.rglob("*") if path.is_dir()})
        self.assertFalse(lock.exists())
        built = support.run("trace", "build", "--workspace", self.root)
        self.assertEqual(0, built.returncode, built.stderr)
        self.assertTrue(lock.is_file())

    def test_legacy_subjects_and_attestations_do_not_become_verified_coverage(self):
        self.change_story(1, status="in-review", receipts={"attestation": {"subject_sha": SHA_A,
                          "status": "pass", "verifies": ["requirement:R1"]}})
        graph = self.derive()
        self.assertIn("requirement:R1", graph["answers"]["unproved"]["requirements"])
        node = self.node(graph, "receipt:1:attestation")
        self.assertEqual("unknown", node["freshness"])
        self.assertEqual("unknown", node["artifact_integrity"])

    def test_changed_subject_or_artifact_exposes_stale_support(self):
        self.change_story(1, status="in-review", review_subject_sha=SHA_A,
                          receipts={"check": self.passing_receipt()})
        self.assertNotIn("requirement:R1", self.derive()["answers"]["unproved"]["requirements"])
        self.change_story(1, review_subject_sha=SHA_B)
        graph = self.derive()
        self.assertEqual("stale", graph["answers"]["stale"][0]["freshness"])
        self.assertIn("requirement:R1", graph["answers"]["unproved"]["requirements"])
        self.change_story(1, review_subject_sha=SHA_A)
        (self.root / "proof.txt").write_text("changed fixture evidence\n")
        self.assertEqual("mismatch", self.derive()["answers"]["stale"][0]["artifact_integrity"])
        (self.root / "proof.txt").unlink()
        self.assertEqual("missing", self.derive()["answers"]["stale"][0]["artifact_integrity"])

    def test_dangling_links_missing_sources_and_declared_relationships_are_explicit(self):
        self.change_story(1, after=[999], scope=["absent.py"], links=[
            {"relation": "implements", "target": "surface:absent.py"},
            {"relation": "reviews", "target": "receipt:999:absent"}],
            receipts={"review": {"subject_sha": SHA_A, "decision_ref": "decisions/missing.md"}})
        graph = self.derive()
        self.assertFalse(self.node(graph, "surface:absent.py")["exists"])
        kinds = {entry["kind"] for entry in graph["diagnostics"]}
        self.assertTrue({"dangling-reference", "missing-decision-source", "board-problem"} <= kinds)
        self.assertTrue(any(edge["relation"] == "implements" and edge["basis"] == "explicit-declaration"
                            for edge in graph["edges"]))
        self.assertFalse(self.node(graph, "decision:decisions/missing.md")["authenticated"])

    def test_prerequisite_and_supersession_cycles_reject_without_replacing_output(self):
        output = ".software-factory/context/board/lifecycle-graph.json"
        trace.derive(self.root, output=output)
        before = (self.root / output).read_bytes()
        self.change_story(1, after=[2])
        with self.assertRaises(trace.TraceError):
            trace.derive(self.root, output=output)
        self.assertEqual(before, (self.root / output).read_bytes())
        self.change_story(1, after=[], receipts={
            "a": {"subject_sha": SHA_A, "links": [{"relation": "supersedes", "target": "receipt:1:b"}]},
            "b": {"subject_sha": SHA_A, "links": [{"relation": "supersedes", "target": "receipt:1:a"}]}})
        with self.assertRaisesRegex(trace.TraceError, "supersedes cycle"):
            trace.derive(self.root, output=output)
        self.assertEqual(before, (self.root / output).read_bytes())

    def test_actual_crawl_shape_retains_import_cycles_and_states_binding_limit(self):
        (self.root / "src/state.py").write_text("from src.gate import b\ndef a():\n    b()\n")
        (self.root / "src/gate.py").write_text("from src.state import a\ndef b():\n    a()\n")
        path = support.REPO / "skills/sf-crawl/scripts/crawl.py"
        spec = importlib.util.spec_from_file_location("sf_trace_crawl_fixture", path)
        crawler = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(crawler)
        write_json(self.root / "crawl.json", crawler.crawl(self.root, 100))
        graph = self.derive("crawl.json")
        imports = [edge for edge in graph["edges"] if edge["relation"] == "imports"]
        self.assertEqual(2, len(imports))
        self.assertEqual(2, sum(edge["relation"] == "calls" for edge in graph["edges"]))
        self.assertTrue(all(edge["current_source_binding"] == "unknown" for edge in imports))
        self.assertTrue(any(item["kind"] == "crawl-binding-unverified" for item in graph["diagnostics"]))
        self.assertTrue(trace.find_path(graph, "surface:src/state.py", "surface:src/gate.py")["path"])

    def test_atomic_failure_output_limits_and_source_output_collision_preserve_inputs(self):
        output = ".software-factory/context/board/lifecycle-graph.json"
        trace.derive(self.root, output=output)
        before = (self.root / output).read_bytes()
        with (mock.patch.object(trace.os, "replace", side_effect=OSError("fixture write failure")),
              self.assertRaises(trace.TraceError)):
            trace.derive(self.root, output=output)
        self.assertEqual(before, (self.root / output).read_bytes())
        self.assertFalse(list((self.root / output).parent.glob(".factory-trace-*")))
        for limit in ("MAX_INPUT_BYTES", "MAX_OUTPUT_BYTES", "MAX_FILES"):
            with (self.subTest(limit=limit), mock.patch.object(trace, limit, 1),
                  self.assertRaises(trace.TraceError)):
                trace.derive(self.root, output=output)
            self.assertEqual(before, (self.root / output).read_bytes())
        artifact = self.root / "lifecycle-graph.json"
        artifact.write_text("retained evidence\n")
        self.change_story(1, receipts={"tests": {"subject_sha": SHA_A, "artifact": artifact.name}})
        with self.assertRaisesRegex(trace.TraceError, "separate from sources"):
            trace.derive(self.root, output="./lifecycle-graph.json")
        self.assertEqual("retained evidence\n", artifact.read_text())

    def test_bad_optional_crawl_leaves_prior_projection_intact(self):
        output = ".software-factory/context/board/lifecycle-graph.json"
        trace.derive(self.root, output=output)
        before = (self.root / output).read_bytes()
        for value in ({"schema": "sf-crawl/2"}, {"schema": "sf-crawl/1", "python": []}):
            write_json(self.root / "crawl.json", value)
            with self.assertRaises(trace.TraceError):
                trace.derive(self.root, "crawl.json", output)
            self.assertEqual(before, (self.root / output).read_bytes())

    def test_claims_and_checkpoints_keep_relative_provenance_without_repo_path_disclosure(self):
        self.board.make_ready(1, "worker", "src/state.py")
        self.board.ws.checkpoint(support.notes())
        decisions = self.root / ".software-factory/context/decisions"
        decisions.mkdir()
        (decisions / "0001-choice.md").write_text("# Recorded choice\n")
        graph = self.derive()
        self.assertEqual("unknown", self.node(graph, "claim:1")["liveness"])
        self.assertFalse(self.node(graph, "checkpoint:active")["authorization"])
        self.assertFalse(self.node(graph, "decision:.software-factory/context/decisions/0001-choice.md")["authenticated"])
        self.assertNotIn(str(self.root), trace.encoded(graph).decode())

    def test_input_replacement_during_computation_fails_and_keeps_last_projection(self):
        output = ".software-factory/context/board/lifecycle-graph.json"
        trace.derive(self.root, output=output)
        before = (self.root / output).read_bytes()
        board_module = trace.roadmap_module()
        original = board_module.compute_roadmap

        def changed(*args):
            result = original(*args)
            self.change_story(1, title="Concurrent source replacement")
            return result

        with (mock.patch.object(trace, "roadmap_module", return_value=board_module),
              mock.patch.object(board_module, "compute_roadmap", side_effect=changed),
              self.assertRaisesRegex(trace.TraceError, "changed during")):
            trace.derive(self.root, output=output)
        self.assertEqual(before, (self.root / output).read_bytes())

    def test_claim_replacement_during_computation_is_detected(self):
        board_module = trace.roadmap_module()
        original = board_module.compute_roadmap

        def changed(*args):
            result = original(*args)
            run = json.loads(self.board.ws.run_file().read_text())
            run["checkpoint"] = support.notes()
            write_json(self.board.ws.run_file(), run)
            return result

        with (mock.patch.object(trace, "roadmap_module", return_value=board_module),
              mock.patch.object(board_module, "compute_roadmap", side_effect=changed),
              self.assertRaisesRegex(trace.TraceError, "changed during")):
            self.derive()

    def test_bad_inputs_symlinks_escapes_and_bounds_refuse_without_source_changes(self):
        before = self.snapshot()
        self.change_story(1, scope=["../outside.py"])
        with self.assertRaisesRegex(trace.TraceError, "inside"):
            self.derive()
        self.change_story(1, scope=["src/state.py"])
        (self.root / "src/state.py").unlink()
        (self.root / "src/state.py").symlink_to(self.root / "src/gate.py")
        with self.assertRaisesRegex(trace.TraceError, "symlink"):
            self.derive()
        (self.root / "src/state.py").unlink()
        (self.root / "src/state.py").write_bytes(before["src/state.py"])
        with (mock.patch.object(trace, "MAX_FILE_BYTES", 10),
              self.assertRaisesRegex(trace.TraceError, "byte limit")):
            self.derive()
        with (mock.patch.object(trace, "MAX_NODES", 1),
              self.assertRaisesRegex(trace.TraceError, "node limit")):
            self.derive()
        with (mock.patch.object(trace, "MAX_EDGES", 1),
              self.assertRaisesRegex(trace.TraceError, "edge limit")):
            self.derive()
        write_json(self.board.ws.pointer_file(), {"version": 2, "run": ".software-factory/runs/demo/run.json"})
        with self.assertRaisesRegex(trace.TraceError, "ownership authority"):
            self.derive()

    def test_fresh_copied_pack_query_writes_neither_pack_nor_consumer(self):
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary) / "scripts"
            pack.mkdir()
            for name in ("trace.py", "roadmap.py", "state.py"):
                shutil.copyfile(support.SCRIPTS / name, pack / name)
            before = {path.name: path.read_bytes() for path in pack.iterdir()}
            consumer_before = self.snapshot()
            result = subprocess.run([sys.executable, str(pack / "trace.py"), "query", "ready",
                                     "--workspace", str(self.root)], capture_output=True, text=True,
                                    timeout=10, check=False)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(before, {path.name: path.read_bytes() for path in pack.iterdir()})
            self.assertEqual(consumer_before, self.snapshot())

    def test_projection_uses_captured_board_claims_and_config_through_aba_replacement(self):
        config = self.root / ".software-factory/config.yaml"
        write_json(config, {"board": {"dir": ".software-factory/context/board"}})
        baseline = self.derive()
        module = trace.roadmap_module()
        original, original_config = module.compute_roadmap, module.board_config
        story_path, run_path = self.board.story_file(1), self.board.ws.run_file()
        saved = {path: path.read_bytes() for path in (story_path, run_path, config)}

        def config_aba(workspace):
            try:
                write_json(config, {"board": {"dir": "unavailable/other"}})
                return original_config(workspace)
            finally:
                config.write_bytes(saved[config])

        def changed(*args):
            try:
                self.change_story(1, title="Transient B title", status="done", merged_sha=SHA_B)
                run = json.loads(saved[run_path])
                run["claims"]["1"] = {"owner": "transient", "repo": "untrusted",
                                      "identity": "x", "claimed_at": "x", "paths": ["src/state.py"]}
                write_json(run_path, run)
                return original(*args)
            finally:
                for path in (story_path, run_path):
                    path.write_bytes(saved[path])

        with (mock.patch.object(trace, "roadmap_module", return_value=module),
              mock.patch.object(module, "board_config", side_effect=config_aba),
              mock.patch.object(module, "compute_roadmap", side_effect=changed)):
            result = self.derive()
        self.assertEqual(baseline, result)
        self.assertEqual([1], [entry["id"] for entry in result["answers"]["ready"]])

    def test_leaf_replacement_with_symlink_or_fifo_is_refused_without_blocking(self):
        path = self.root / "proof.txt"
        output = ".software-factory/context/board/lifecycle-graph.json"
        self.change_story(1, receipts={"check": self.passing_receipt()})
        trace.derive(self.root, output=output)
        before = (self.root / output).read_bytes()
        original = trace.os.open
        for replacement in ("symlink", "fifo"):
            path.write_text("observed fixture result\n")
            replaced = False

            def opening(name, flags, *args, replacement=replacement, **kwargs):
                nonlocal replaced
                if name == "proof.txt" and not replaced:
                    replaced = True
                    path.unlink()
                    if replacement == "symlink":
                        path.symlink_to(self.root / "src/state.py")
                    else:
                        os.mkfifo(path)
                return original(name, flags, *args, **kwargs)

            with (mock.patch.object(trace.os, "open", side_effect=opening),
                  self.assertRaises(trace.TraceError)):
                trace.derive(self.root, output=output)
            self.assertTrue(replaced)
            self.assertEqual(before, (self.root / output).read_bytes())
            path.unlink()

    def test_ancestor_replacement_is_refused_for_inputs_and_publication(self):
        output = "derived/lifecycle-graph.json"
        trace.derive(self.root, output=output)
        before = (self.root / output).read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            outside = Path(temporary)
            (outside / "state.py").write_text("EXTERNAL = True\n")
            (outside / "lifecycle-graph.json").write_text("external preserved\n")
            original = trace.os.open
            replaced = False

            def opening(name, flags, *args, **kwargs):
                nonlocal replaced
                if name == "src" and not replaced:
                    replaced = True
                    (self.root / "src").rename(self.root / "src-retained")
                    (self.root / "src").symlink_to(outside, target_is_directory=True)
                return original(name, flags, *args, **kwargs)

            with (mock.patch.object(trace.os, "open", side_effect=opening),
                  self.assertRaises(trace.TraceError)):
                trace.derive(self.root, output=output)
            self.assertEqual(before, (self.root / output).read_bytes())
            (self.root / "src").unlink()
            (self.root / "src-retained").rename(self.root / "src")
            original_verify = trace.Inputs.verify
            calls = 0

            def verifying(inputs):
                nonlocal calls
                original_verify(inputs)
                calls += 1
                if calls == 3:
                    (self.root / "derived").rename(self.root / "derived-retained")
                    (self.root / "derived").symlink_to(outside, target_is_directory=True)

            with (mock.patch.object(trace.Inputs, "verify", verifying),
                  self.assertRaises(trace.TraceError)):
                trace.derive(self.root, output=output)
            self.assertEqual(before, (self.root / "derived-retained/lifecycle-graph.json").read_bytes())
            self.assertEqual("external preserved\n", (outside / "lifecycle-graph.json").read_text())
            self.assertFalse(list(outside.glob(".factory-trace-*")))
            self.assertFalse(list((self.root / "derived-retained").glob(".factory-trace-*")))

    def test_root_scope_and_artifact_refuse_without_replacing_prior_output(self):
        output = ".software-factory/context/board/lifecycle-graph.json"
        trace.derive(self.root, output=output)
        before = (self.root / output).read_bytes()
        for fields in ({"scope": ["."]}, {"scope": ["src/state.py"],
                       "receipts": {"check": {"subject_sha": SHA_A, "artifact": "./"}}}):
            self.change_story(1, **fields)
            with self.assertRaisesRegex(trace.TraceError, "entry inside"):
                trace.derive(self.root, output=output)
            self.assertEqual(before, (self.root / output).read_bytes())

    def test_scope_existence_comes_from_captured_payload_after_inspect_create_or_delete(self):
        path = self.root / "src/optional.py"
        self.change_story(1, scope=["src/optional.py"])
        original = trace.Inputs.inspect
        for create in (True, False):
            if not create:
                path.write_text("VALUE = 1\n")

            def inspecting(inputs, relative, create=create):
                info = original(inputs, relative)
                if relative == "src/optional.py":
                    if create:
                        path.write_text("VALUE = 2\n")
                    else:
                        path.unlink()
                return info

            with mock.patch.object(trace.Inputs, "inspect", inspecting):
                graph = self.derive()
            node = self.node(graph, "surface:src/optional.py")
            self.assertEqual(create, node["exists"])
            source = next(item for item in graph["inputs"] if item["path"] == "src/optional.py")
            self.assertEqual(hashlib.sha256(b"VALUE = 2\n").hexdigest() if create else None,
                             source["sha256"])
            if create:
                path.unlink()

    def test_helpers_have_no_execution_or_network_client_dependency(self):
        self.assertEqual([], support.non_stdlib_imports(support.SCRIPTS / "trace.py"))
        imports = support.imported_top_modules(support.SCRIPTS / "trace.py")
        self.assertFalse({"subprocess", "socket", "urllib", "http"} & imports)


if __name__ == "__main__":
    unittest.main()
