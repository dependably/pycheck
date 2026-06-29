"""Tests for the ``--format json`` machine-readable output and exit codes."""

import json
import os
import sys
from unittest.mock import patch

import pytest

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from checker import main, setup_argument_parser  # noqa: E402


class TestFormatArgument:
    """The --format flag parses correctly and defaults to human."""

    def setup_method(self):
        self.parser = setup_argument_parser()

    def test_format_defaults_to_human(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("import os")
        args = self.parser.parse_args(["--check", str(f)])
        assert args.format == "human"

    def test_format_accepts_json(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("import os")
        args = self.parser.parse_args(["--check", "--format", "json", str(f)])
        assert args.format == "json"

    def test_format_rejects_unknown(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("import os")
        with pytest.raises(SystemExit):
            self.parser.parse_args(["--check", "--format", "xml", str(f)])


class TestCheckJsonOutput:
    """--check --format json emits a complete, valid JSON document."""

    def _run_json(self, argv, capsys):
        with patch.object(sys, "argv", argv):
            code = main()
        out = capsys.readouterr().out
        return code, out

    def test_json_is_valid_and_clean(self, tmp_path, capsys):
        f = tmp_path / "x.py"
        f.write_text("import os\nimport sys\nprint(os.getcwd())\n")  # sys unused

        code, out = self._run_json(["checker.py", "--check", "--format", "json", str(f)], capsys)

        # stdout must be ONLY the JSON document (no text/progress mixed in).
        assert out.lstrip().startswith("{")
        assert "Analyzing:" not in out
        doc = json.loads(out)  # raises if invalid -> proves clean valid JSON

        assert code == 1
        assert doc["tool"] == "python-import-checker"
        assert doc["mode"] == "check"
        assert doc["exitCode"] == 1
        assert doc["summary"]["files"] == 1
        assert doc["summary"]["errors"] == 1

        findings = doc["findings"]
        assert len(findings) == 1
        finding = findings[0]
        assert finding["code"] == "unused-import"
        assert finding["severity"] == "error"
        assert finding["line"] == 2
        assert finding["file"] == str(f)
        assert "sys" in finding["message"]

    def test_json_matches_human_finding_count(self, tmp_path, capsys):
        """The json finding set is COMPLETE -- same count the human report shows."""
        f = tmp_path / "x.py"
        f.write_text("import os\nimport sys\nimport json\nprint('hi')\n")  # 3 unused

        # Human run: count the per-import "Line N:" report lines.
        with patch.object(sys, "argv", ["checker.py", "--check", str(f)]):
            assert main() == 1
        human_out = capsys.readouterr().out
        human_count = sum(1 for line in human_out.splitlines() if line.strip().startswith("Line "))

        # JSON run on the same file.
        _, json_out = self._run_json(["checker.py", "--check", "--format", "json", str(f)], capsys)
        doc = json.loads(json_out)

        assert human_count == 3
        assert len(doc["findings"]) == human_count

    def test_clean_file_json_exits_zero_empty_findings(self, tmp_path, capsys):
        f = tmp_path / "x.py"
        f.write_text("import os\nprint(os.getcwd())\n")

        code, out = self._run_json(["checker.py", "--check", "--format", "json", str(f)], capsys)
        doc = json.loads(out)

        assert code == 0
        assert doc["exitCode"] == 0
        assert doc["findings"] == []
        assert doc["summary"]["errors"] == 0


class TestExitCodeConvention:
    """End-to-end exit codes follow the suite convention (0 / 1 / 2)."""

    def test_clean_exits_zero(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("import os\nprint(os.getcwd())\n")
        with patch.object(sys, "argv", ["checker.py", "--check", str(f)]):
            assert main() == 0

    def test_findings_exit_one(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("import os\n")  # unused
        with patch.object(sys, "argv", ["checker.py", "--check", str(f)]):
            assert main() == 1

    def test_usage_error_exits_two(self):
        with patch.object(sys, "argv", ["checker.py", "--bogus"]):
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 2

    def test_missing_mode_exits_two(self, tmp_path):
        f = tmp_path / "x.py"
        f.write_text("import os")
        with patch.object(sys, "argv", ["checker.py", str(f)]):
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 2

    def test_version_exits_zero(self):
        with patch.object(sys, "argv", ["checker.py", "--version"]):
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 0

    def test_help_exits_zero(self):
        with patch.object(sys, "argv", ["checker.py", "--help"]):
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 0

    def test_operational_error_exits_two(self, tmp_path):
        """A syntax error in the target is operational, not a finding -> exit 2."""
        f = tmp_path / "x.py"
        f.write_text("def broken(:\n")  # invalid syntax
        with patch.object(sys, "argv", ["checker.py", "--check", str(f)]):
            assert main() == 2
