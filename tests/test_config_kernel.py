"""Tests for the configuration kernel helper (config.py).

Encodes the VAL-KERNEL config assertions: standard-library parsing of the
documented JSON-compatible YAML subset, fail-closed refusal of anything the
documented rules cannot parse (never partial interpretation), and the
never-execute rule for configuration content.
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "sf_test_support", Path(__file__).resolve().parent / "support.py"
)
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)

config = support.helper("config")
SCRIPTS = support.SCRIPTS


class ConfigFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def file(self, text, name="config.yaml"):
        path = self.root / name
        path.write_text(text)
        return path

    def run_config(self, path):
        return support.run("config", "--config", path)


class ParseTests(ConfigFixture):
    def test_json_object_parses(self):
        text = json.dumps({"schema_version": 1, "project": {"name": "demo"}})
        self.assertEqual({"schema_version": 1, "project": {"name": "demo"}}, config.parse(text))

    def test_pretty_json_in_a_yaml_file_parses(self):
        text = (
            "{\n"
            '  "schema_version": 1,\n'
            '  "tracker": {"adapter": "markdown"}\n'
            "}\n"
        )
        self.assertEqual(1, config.parse(text)["schema_version"])

    def test_cli_reports_success_without_echoing_values(self):
        path = self.file(json.dumps({"schema_version": 1, "project": "MARKER-VALUE-77f3"}))
        result = self.run_config(path)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("parsed", result.stdout)
        self.assertNotIn("MARKER-VALUE-77f3", result.stdout)


class FailClosedTests(ConfigFixture):
    def test_unparseable_inputs_are_refused_with_a_clear_error(self):
        cases = {
            "truncated JSON": '{"schema_version": 1',
            "empty file": "",
            "plain YAML mapping": "tracker: markdown\n",
            "YAML anchor": "value: &anchor 1\n",
            "comment-only file": "# nothing here\n",
            "list root": '["a"]',
            "scalar root": "42",
            "string root": '"config"',
            "null root": "null",
        }
        for label, text in cases.items():
            with self.subTest(case=label):
                path = self.file(text, name=f"case-{abs(hash(label))}.yaml")
                result = self.run_config(path)
                self.assertNotEqual(0, result.returncode, label)
                lines = [line for line in result.stderr.strip().splitlines() if line]
                self.assertEqual(1, len(lines), label)
                self.assertIn("config", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual("", result.stdout)

    def test_parse_raises_config_error_not_partial_data(self):
        with self.assertRaises(config.ConfigError):
            config.parse('{"a": ')
        with self.assertRaises(config.ConfigError):
            config.parse("[]")
        with self.assertRaises(config.ConfigError):
            config.parse("")

    def test_missing_file_is_refused(self):
        result = self.run_config(self.root / "missing.yaml")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("unreadable", result.stderr)


class NoExecutionTests(ConfigFixture):
    def test_configuration_content_is_never_executed(self):
        side_effect = self.root / "side-effect"
        payload = {
            "schema_version": 1,
            "environments": {
                "staging": {
                    "deploy": ["touch", str(side_effect)],
                    "note": f"run `touch {side_effect}` now",
                }
            },
        }
        result = self.run_config(self.file(json.dumps(payload)))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(side_effect.exists())

    def test_source_has_no_execution_mechanism(self):
        source = (SCRIPTS / "config.py").read_text()
        for banned in ("subprocess", "os.system", "popen", "eval(", "exec(", "system("):
            self.assertNotIn(banned, source)

    def test_imports_are_standard_library_only(self):
        self.assertEqual([], support.non_stdlib_imports(SCRIPTS / "config.py"))


if __name__ == "__main__":
    unittest.main()
