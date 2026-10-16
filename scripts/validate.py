#!/usr/bin/env python3
"""Validate the canonical Software Factory pack layout.

Checks, all offline and standard-library only:

- layout: exactly the canonical skill folders under ``skills/`` and role
  files under ``agents/`` (the palettes below are the single source of
  truth; counts are derived, never re-hardcoded);
- frontmatter: ``name`` matches the folder/file, ``description`` budget,
  standard keys only, string ``metadata`` values, no projection-only keys;
- budgets: every cap class is enforced - the entry skill, non-entry
  skills, agents, descriptions, and reference files by class (prose vs
  data/catalog/index) - with the cap reported beside the measured value
  on any breach, and the current maximum per class printed on success;
- references: relative Markdown links inside skill files resolve;
- agents: ``model: inherit`` and no isolation field;
- legacy names: retired pre-rename names (the old role and skill names)
  never appear in prose content, only the current ``sf-*`` names;
- manifests: any ``plugin.json``/``marketplace.json`` parses and every
  repo-relative path it names stays inside the repo and exists.

Clearly-marked placeholder skill files (an explicit "not the shipped
skill" marker) are accepted per the validation contract's palette note.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# The canonical palette. Define the sets ONCE here; everything else
# (messages, budgets, summaries) derives from these constants.
SKILLS = (
    "software-factory",
    "sf-help",
    "sf-agents",
    "sf-evolve",
    "sf-eval",
    "sf-principles",
    "sf-crawl",
    "sf-design",
    "sf-smell-audit",
    "sf-refactor",
    "sf-patterns",
)
AGENTS = (
    "sf-product-manager",
    "sf-architect",
    "sf-design-reviewer",
    "sf-engineer",
    "sf-principal-engineer",
    "sf-qa-engineer",
    "sf-code-reviewer",
    "sf-evaluator",
    "sf-ai-engineer",
    "sf-release-engineer",
    "sf-security-reviewer",
)

ENTRY_SKILL = "software-factory"

# The budget cap classes, stated in CONTRIBUTING.md ("File budgets") and
# enforced below. Every cap carries headroom above the measured maximum at
# the 2026-10-11 baseline rather than sitting exactly on it:
#   entry skill            138 measured -> 150 cap (pinned by the contract)
#   non-entry skill         86 measured -> 120 cap (34 lines of headroom;
#                          sf-smell-audit is the largest)
#   agent                   28 measured ->  60 cap (32 lines of headroom)
#   description            296 measured -> 300 characters (contract cap)
#   prose reference        195 measured -> 240 cap (45 lines of headroom;
#                          references/recovery.md is the largest)
#   data/catalog/index     127 measured -> 320 cap (headroom for the planned
#                          sf-help question bank and growing catalogs;
#                          technique-index.md is the largest today)
ENTRY_SKILL_MAX_LINES = 150
SKILL_MAX_LINES = 120
AGENT_MAX_LINES = 60
DESCRIPTION_MAX_CHARS = 300
COMPATIBILITY_MAX_CHARS = 500
REFERENCE_PROSE_MAX_LINES = 240
REFERENCE_DATA_MAX_LINES = 320

# Reference-file classes. Every Markdown file under ``skills/`` that is not
# a ``SKILL.md`` entry (references and workflows) belongs to exactly one
# class: data/catalog/index when its file name is listed here, prose
# otherwise. Adding a catalog, index, map or question-bank file means
# adding its name to this set.
REFERENCE_DATA_FILES = frozenset(
    {
        "pattern-index.md",
        "questions.md",  # the sf-help interview bank (onboarding milestone)
        "smell-technique-map.md",
        "sources.md",
        "technique-index.md",
    }
)

SKILL_KEYS = frozenset({"name", "description", "license", "compatibility", "metadata"})
AGENT_KEYS = frozenset({"name", "description", "model"})
# Host projections add these; canonical sources must never carry them.
PROJECTION_KEYS = frozenset(
    {"argument-hint", "disable-model-invocation", "allowed-tools", "isolation"}
)

PLACEHOLDER_MARKERS = ("placeholder", "not the shipped skill")

# Retired pre-rename names. Folder/file names are already pinned by the
# SKILLS/AGENTS palettes above; this guards prose content (bodies only, so
# frontmatter keys such as ``factory-role`` are never matched). The
# ``factory-`` prefix excludes the ``factory-role`` metadata key and requires
# the hyphenated form, so plain words like "software-factory" never match.
LEGACY_NAME_RE = re.compile(
    r"\b("
    r"risk-coder"
    r"|coder"
    r"|factory-(?!role\b)[a-z0-9-]*[a-z0-9]"
    r"|software-design"
    r"|code-smell-audit"
    r"|refactoring-playbook"
    r"|design-pattern-judgment"
    r")\b",
    re.IGNORECASE,
)

LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE_RE = re.compile(r"^\s*(```|~~~)")

MANIFEST_NAMES = ("plugin.json", "marketplace.json")


class FrontmatterError(Exception):
    """A frontmatter block is missing, malformed, or has a bad value."""


def strip_fences(text: str) -> str:
    """Return the markdown text with fenced code blocks removed."""
    out = []
    in_fence = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def split_frontmatter(text: str, path: Path) -> tuple[list[str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError(f"{path}: missing opening '---' frontmatter fence")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[1:index], "\n".join(lines[index + 1 :])
    raise FrontmatterError(f"{path}: missing closing '---' frontmatter fence")


def parse_scalar(key: str, raw: str, path: Path, line_no: int) -> tuple[str, bool]:
    """Parse a simple YAML scalar; returns (value, was_quoted)."""
    value = raw.strip()
    if value == "":
        return "", False
    if value[0] in "\"'":
        quote = value[0]
        if len(value) < 2 or not value.endswith(quote):
            raise FrontmatterError(
                f"{path}:{line_no}: unterminated quoted scalar for '{key}'"
            )
        return value[1:-1], True
    if ": " in value or value.endswith(":"):
        raise FrontmatterError(
            f"{path}:{line_no}: mapping values are not allowed here - the value "
            f"for '{key}' contains an unquoted ': '. Quote the whole value, "
            f'for example: {key}: "{value}"'
        )
    return value, False


def looks_non_string(value: str) -> bool:
    """True when an unquoted scalar would parse as int/float/bool/null/list/map."""
    if value == "":
        return True
    if re.fullmatch(r"[-+]?\d+", value):
        return True
    if re.fullmatch(r"[-+]?\d+\.\d+", value):
        return True
    if value.lower() in {"true", "false", "null", "yes", "no", "on", "off", "~"}:
        return True
    return value[0] in "[{"


def parse_frontmatter(text: str, path: Path) -> dict[str, object]:
    """Parse the small YAML subset used by canonical frontmatter blocks."""
    raw_lines, body = split_frontmatter(text, path)
    data: dict[str, object] = {}
    current_map: str | None = None
    for offset, line in enumerate(raw_lines, start=2):
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            current_map = None
            match = re.match(r"^([A-Za-z0-9_-]+):(\s+(.*))?$", line)
            if not match:
                raise FrontmatterError(
                    f"{path}:{offset}: cannot parse frontmatter line: {line!r}"
                )
            key, _, raw = match.group(1), match.group(2), match.group(3)
            if raw is None or raw.strip() == "":
                data[key] = None
                current_map = key
            else:
                data[key] = parse_scalar(key, raw, path, offset)[0]
        else:
            if current_map is None:
                raise FrontmatterError(
                    f"{path}:{offset}: unexpected indentation outside a mapping"
                )
            match = re.match(r"^\s+([A-Za-z0-9_-]+):(\s+(.*))?$", line)
            if not match:
                raise FrontmatterError(
                    f"{path}:{offset}: cannot parse nested line: {line!r}"
                )
            sub_key = match.group(1)
            raw = match.group(3)
            value, quoted = (
                parse_scalar(sub_key, raw, path, offset)
                if raw is not None
                else ("", False)
            )
            nested = data.get(current_map)
            if not isinstance(nested, dict):
                nested = {}
                data[current_map] = nested
            nested[sub_key] = {"value": value, "quoted": quoted}
    return data | {"__body__": body}


def is_placeholder(body: str) -> bool:
    lowered = body.lower()
    return all(marker in lowered for marker in PLACEHOLDER_MARKERS)


class Validator:
    def __init__(self, root: Path):
        self.root = root
        self.errors: list[str] = []
        self.placeholders = 0
        # Measured maximum per budget cap class, reported on success.
        self.budget_max: dict[str, int] = {}

    def error(self, message: str) -> None:
        self.errors.append(message)

    def observe(self, cap_class: str, measured: int) -> None:
        self.budget_max[cap_class] = max(
            measured, self.budget_max.get(cap_class, 0)
        )

    def check_skill(self, folder: Path) -> None:
        name = folder.name
        skill_md = folder / "SKILL.md"
        if not folder.is_dir():
            self.error(f"skills/{name}: expected a directory")
            return
        if not skill_md.is_file():
            self.error(f"skills/{name}: missing SKILL.md")
            return
        text = skill_md.read_text(encoding="utf-8")
        try:
            meta = parse_frontmatter(text, skill_md)
        except FrontmatterError as exc:
            self.error(str(exc))
            return
        body = str(meta.pop("__body__"))
        if is_placeholder(body):
            self.placeholders += 1
        for key in sorted(meta):
            if key in PROJECTION_KEYS:
                self.error(
                    f"{skill_md}: '{key}' is added by host projections and must "
                    "not appear in canonical frontmatter"
                )
            elif key not in SKILL_KEYS:
                allowed = ", ".join(sorted(SKILL_KEYS))
                self.error(
                    f"{skill_md}: non-standard frontmatter key '{key}' "
                    f"(allowed: {allowed})"
                )
        declared = meta.get("name")
        if declared != name:
            self.error(
                f"{skill_md}: frontmatter name '{declared}' does not match "
                f"folder '{name}'"
            )
        description = meta.get("description")
        if not isinstance(description, str) or not description.strip():
            self.error(f"{skill_md}: description is empty or missing")
        else:
            self.observe("description", len(description))
            if len(description) > DESCRIPTION_MAX_CHARS:
                self.error(
                    f"{skill_md}: description is {len(description)} characters, "
                    f"over the {DESCRIPTION_MAX_CHARS}-character budget"
                )
        compatibility = meta.get("compatibility")
        if isinstance(compatibility, str) and len(compatibility) > COMPATIBILITY_MAX_CHARS:
            self.error(
                f"{skill_md}: compatibility is {len(compatibility)} characters, "
                f"over the {COMPATIBILITY_MAX_CHARS}-character budget"
            )
        metadata = meta.get("metadata")
        if metadata is not None:
            if not isinstance(metadata, dict):
                self.error(f"{skill_md}: metadata must be a mapping of strings")
            else:
                for sub_key, sub in metadata.items():
                    if not sub["quoted"] and (
                        sub["value"] == "" or looks_non_string(sub["value"])
                    ):
                        self.error(
                            f"{skill_md}: metadata.{sub_key} must be a string; "
                            "quote the value"
                        )
        line_count = len(text.splitlines())
        if name == ENTRY_SKILL:
            self.observe("entry skill", line_count)
            if line_count > ENTRY_SKILL_MAX_LINES:
                self.error(
                    f"{skill_md}: entry skill is {line_count} lines, over the "
                    f"{ENTRY_SKILL_MAX_LINES}-line budget"
                )
        else:
            self.observe("non-entry skill", line_count)
            if line_count > SKILL_MAX_LINES:
                self.error(
                    f"{skill_md}: non-entry skill is {line_count} lines, over "
                    f"the {SKILL_MAX_LINES}-line budget"
                )

    def check_agent(self, path: Path) -> None:
        name = path.stem
        text = path.read_text(encoding="utf-8")
        try:
            meta = parse_frontmatter(text, path)
        except FrontmatterError as exc:
            self.error(str(exc))
            return
        meta.pop("__body__")
        for key in sorted(meta):
            if key in PROJECTION_KEYS:
                self.error(
                    f"{path}: '{key}' is not allowed in canonical agent "
                    "frontmatter (no isolation or projection-only keys)"
                )
            elif key not in AGENT_KEYS:
                allowed = ", ".join(sorted(AGENT_KEYS))
                self.error(
                    f"{path}: non-standard agent key '{key}' (allowed: {allowed})"
                )
        if meta.get("name") != name:
            self.error(
                f"{path}: frontmatter name '{meta.get('name')}' does not match "
                f"file name '{name}'"
            )
        description = meta.get("description")
        if not isinstance(description, str) or not description.strip():
            self.error(f"{path}: description is empty or missing")
        else:
            self.observe("description", len(description))
            if len(description) > DESCRIPTION_MAX_CHARS:
                self.error(
                    f"{path}: description is {len(description)} characters, "
                    f"over the {DESCRIPTION_MAX_CHARS}-character budget"
                )
        if meta.get("model") != "inherit":
            self.error(f"{path}: agents must declare 'model: inherit'")
        line_count = len(text.splitlines())
        self.observe("agent", line_count)
        if line_count > AGENT_MAX_LINES:
            self.error(
                f"{path}: agent is {line_count} lines, over the "
                f"{AGENT_MAX_LINES}-line budget"
            )

    def check_reference_budgets(self) -> None:
        """Enforce the per-class line budget on every reference file."""
        skills_dir = self.root / "skills"
        if not skills_dir.is_dir():
            return
        for md in sorted(skills_dir.rglob("*.md")):
            if md.name == "SKILL.md":
                continue
            if md.name in REFERENCE_DATA_FILES:
                cap_class, cap = "data/catalog/index reference", REFERENCE_DATA_MAX_LINES
            else:
                cap_class, cap = "prose reference", REFERENCE_PROSE_MAX_LINES
            line_count = len(md.read_text(encoding="utf-8").splitlines())
            self.observe(cap_class, line_count)
            if line_count > cap:
                rel = md.relative_to(self.root)
                self.error(
                    f"{rel}: {cap_class} is {line_count} lines, over the "
                    f"{cap}-line budget for its class"
                )

    def check_references(self) -> None:
        skills_dir = self.root / "skills"
        if not skills_dir.is_dir():
            return
        for md in sorted(skills_dir.rglob("*.md")):
            text = strip_fences(md.read_text(encoding="utf-8"))
            for target in LINK_RE.findall(text):
                if "://" in target or target.startswith(("mailto:", "#")):
                    continue
                path_part = target.split("#", 1)[0]
                if not path_part:
                    continue
                resolved = (md.parent / path_part).resolve()
                if not resolved.is_relative_to(self.root.resolve()):
                    self.error(f"{md}: link '{target}' escapes the repository root")
                elif not resolved.exists():
                    self.error(f"{md}: link target '{path_part}' does not exist")

    def check_legacy_names(self) -> None:
        """Flag retired pre-rename names in prose bodies (frontmatter exempt)."""
        candidates: list[Path] = []
        for base, pattern in (
            (self.root / "skills", "**/*.md"),
            (self.root / "agents", "*.md"),
        ):
            if base.is_dir():
                candidates.extend(sorted(base.glob(pattern)))
        for md in candidates:
            text = md.read_text(encoding="utf-8")
            try:
                raw_lines, body = split_frontmatter(text, md)
                first_body_line = len(raw_lines) + 3
            except FrontmatterError:
                body, first_body_line = text, 1
            for line_no, line in enumerate(body.splitlines(), start=first_body_line):
                for match in LEGACY_NAME_RE.finditer(line):
                    self.error(
                        f"{md}:{line_no}: legacy name '{match.group(0)}' in "
                        "prose content; use the current sf-* names"
                    )

    def check_manifest(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.error(f"{path}: manifest does not parse: {exc}")
            return

        # Native catalogs/components are relative to the owning marketplace
        # or plugin root, not its hidden manifest directory. Ordinary nested
        # manifests retain their existing parent-relative interpretation.
        base = path.parent
        native = False
        if base.name in {".claude-plugin", ".cursor-plugin"}:
            base = base.parent
            native = True
        elif (path.name == "marketplace.json" and base.name == "plugins"
              and base.parent.name == ".agents"):
            base = base.parent.parent
            native = True

        def walk(node: object) -> None:
            if isinstance(node, dict):
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)
            elif isinstance(node, str) and node.startswith(("./", "../")):
                resolved = (base / node).resolve()
                if not resolved.is_relative_to(self.root.resolve()):
                    self.error(
                        f"{path}: path '{node}' points outside the repository"
                    )
                elif native and not resolved.is_relative_to(base.resolve()):
                    self.error(f"{path}: path '{node}' points outside its manifest root")
                elif not resolved.exists():
                    self.error(f"{path}: path '{node}' does not exist")

        walk(data)

    def run(self) -> int:
        skills_dir = self.root / "skills"
        agents_dir = self.root / "agents"
        found_skills = sorted(
            entry.name for entry in skills_dir.iterdir() if entry.name != ".DS_Store"
        ) if skills_dir.is_dir() else []
        for name in SKILLS:
            if name not in found_skills:
                self.error(f"skills/{name}: missing required skill folder")
        for name in found_skills:
            if name not in SKILLS:
                self.error(f"skills/{name}: unexpected skill folder")
        for name in SKILLS:
            if name in found_skills:
                self.check_skill(skills_dir / name)

        found_agents = sorted(
            entry.stem for entry in agents_dir.glob("*.md")
        ) if agents_dir.is_dir() else []
        for name in AGENTS:
            if name not in found_agents:
                self.error(f"agents/{name}.md: missing required role agent")
        for name in found_agents:
            if name not in AGENTS:
                self.error(f"agents/{name}.md: unexpected agent file")
        for name in AGENTS:
            if name in found_agents:
                self.check_agent(agents_dir / f"{name}.md")

        self.check_references()
        self.check_reference_budgets()
        self.check_legacy_names()
        for manifest in sorted(self.root.rglob("*")):
            if (
                manifest.is_file()
                and manifest.name in MANIFEST_NAMES
                and ".git" not in manifest.parts
            ):
                self.check_manifest(manifest)

        if self.errors:
            for message in self.errors:
                print(f"error: {message}")
            print(f"validate: {len(self.errors)} problem(s) found")
            return 1
        note = f", {self.placeholders} marked placeholders" if self.placeholders else ""
        print(
            f"validate ok: {len(SKILLS)} skills, {len(AGENTS)} agents{note} "
            f"validated under {self.root}"
        )
        caps = (
            ("entry skill", ENTRY_SKILL_MAX_LINES, "lines"),
            ("non-entry skill", SKILL_MAX_LINES, "lines"),
            ("agent", AGENT_MAX_LINES, "lines"),
            ("description", DESCRIPTION_MAX_CHARS, "characters"),
            ("prose reference", REFERENCE_PROSE_MAX_LINES, "lines"),
            ("data/catalog/index reference", REFERENCE_DATA_MAX_LINES, "lines"),
        )
        parts = []
        for cap_class, cap, unit in caps:
            measured = self.budget_max.get(cap_class)
            value = str(measured) if measured is not None else "none"
            parts.append(f"{cap_class} {value}/{cap} {unit}")
        print("validate budgets: " + "; ".join(parts))
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repository root to validate (default: current directory)",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        print(f"validate: root '{root}' is not a directory")
        return 2
    return Validator(root).run()


if __name__ == "__main__":
    sys.exit(main())
