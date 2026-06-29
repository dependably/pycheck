"""Integration tests for the --validate mode (config artifact validation)."""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from checker import main  # noqa: E402
from validators.runner import run_validators  # noqa: E402

CONFIG_FIXTURES = Path(__file__).parent.parent / "fixtures" / "config"


def _copy(fixture_name: str, dest_dir: Path, dest_name: str) -> None:
    shutil.copy(CONFIG_FIXTURES / fixture_name, dest_dir / dest_name)


class TestRunValidators:
    @pytest.mark.integration
    def test_clean_project_exits_zero(self, tmp_path):
        _copy("valid_pyproject.toml", tmp_path, "pyproject.toml")
        _copy("valid_pip.conf", tmp_path, "pip.conf")
        _copy("valid_requirements.txt", tmp_path, "requirements.txt")

        assert run_validators(tmp_path) == 0

    @pytest.mark.integration
    def test_insecure_pip_conf_exits_one(self, tmp_path):
        _copy("insecure_pip.conf", tmp_path, "pip.conf")
        assert run_validators(tmp_path) == 1

    @pytest.mark.integration
    def test_planted_secret_exits_one(self, tmp_path):
        _copy("secret_pip.conf", tmp_path, "pip.conf")
        assert run_validators(tmp_path) == 1

    @pytest.mark.integration
    def test_env_ref_creds_exits_zero(self, tmp_path):
        _copy("envref_pip.conf", tmp_path, "pip.conf")
        assert run_validators(tmp_path) == 0

    @pytest.mark.integration
    def test_invalid_pyproject_exits_one(self, tmp_path):
        _copy("invalid_pyproject.toml", tmp_path, "pyproject.toml")
        assert run_validators(tmp_path) == 1

    @pytest.mark.integration
    def test_no_artifacts_exits_nonzero(self, tmp_path, capsys):
        # Validating nothing must not report success: an empty target is a
        # misconfiguration (wrong dir / misnamed manifest), not a clean pass.
        assert run_validators(tmp_path) != 0
        err = capsys.readouterr().err
        assert "no config artifacts" in err
        assert "found to validate at" in err

    @pytest.mark.integration
    def test_all_skipped_exits_nonzero(self, tmp_path, monkeypatch, capsys):
        # When every discovered artifact is skipped (e.g. tomllib/tomli
        # unavailable), nothing was actually validated -> non-zero, not a pass.
        from validators import pyproject_validator

        monkeypatch.setattr(pyproject_validator, "tomllib", None)
        _copy("valid_pyproject.toml", tmp_path, "pyproject.toml")
        assert run_validators(tmp_path) != 0
        assert "skipped" in capsys.readouterr().err


class TestValidateViaMain:
    @pytest.mark.integration
    def test_main_validate_clean(self, tmp_path):
        _copy("valid_pyproject.toml", tmp_path, "pyproject.toml")

        from unittest.mock import patch

        with patch.object(sys, "argv", ["checker.py", "--validate", str(tmp_path)]):
            assert main() == 0

    @pytest.mark.integration
    def test_main_validate_insecure(self, tmp_path):
        _copy("invalid_requirements.txt", tmp_path, "requirements.txt")

        from unittest.mock import patch

        with patch.object(sys, "argv", ["checker.py", "--validate", str(tmp_path)]):
            assert main() == 1

    @pytest.mark.integration
    def test_main_validate_empty_dir_exits_nonzero(self, tmp_path, capsys):
        # End-to-end through the CLI: --validate on a dir with no config
        # artifacts must exit non-zero with a clear message, not silently pass.
        from unittest.mock import patch

        with patch.object(sys, "argv", ["checker.py", "--validate", str(tmp_path)]):
            assert main() != 0
        assert "no config artifacts" in capsys.readouterr().err


class TestValidateJsonOutput:
    """--validate --format json emits a complete, clean JSON document."""

    @pytest.mark.integration
    def test_findings_json_is_valid_and_complete(self, tmp_path, capsys):
        # An insecure pip.conf produces both an error and a warning finding.
        _copy("insecure_pip.conf", tmp_path, "pip.conf")

        assert run_validators(tmp_path, output_format="json") == 1
        captured = capsys.readouterr()

        # stdout carries only the JSON document; status (if any) goes to stderr.
        doc = json.loads(captured.out)
        # Shared Dependably finding envelope (schema v1).
        assert doc["tool"] == "Dependably.pycheck"
        assert doc["schemaVersion"] == "1.0"
        assert doc["summary"]["exitCode"] == 1
        assert doc["summary"]["scanned"] == 1
        assert doc["summary"]["findings"] == len(doc["findings"])

        rule_ids = {f["ruleId"] for f in doc["findings"]}
        severities = {f["severity"] for f in doc["findings"]}
        assert "high" in severities  # at least one blocking finding (error -> high)
        assert doc["summary"]["bySeverity"]["high"] >= 1
        # Every finding carries the required shared-schema fields.
        for f in doc["findings"]:
            assert set(f) == {"severity", "ruleId", "category", "message", "location", "remediation"}
            assert f["category"] == "config"
            assert f["location"]["file"].endswith("pip.conf")
            assert set(f["location"]) == {"file", "line", "column"}
            assert f["severity"] in {"high", "low"}
        assert rule_ids  # non-empty

    @pytest.mark.integration
    def test_clean_json_exits_zero_no_error_findings(self, tmp_path, capsys):
        _copy("valid_pyproject.toml", tmp_path, "pyproject.toml")
        _copy("valid_pip.conf", tmp_path, "pip.conf")
        _copy("valid_requirements.txt", tmp_path, "requirements.txt")

        assert run_validators(tmp_path, output_format="json") == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["summary"]["exitCode"] == 0
        assert doc["summary"]["bySeverity"]["high"] == 0
        assert all(f["severity"] != "high" for f in doc["findings"])

    @pytest.mark.integration
    def test_no_artifacts_json_clean_stdout(self, tmp_path, capsys):
        # Misconfiguration still produces a valid JSON document on stdout, while
        # the human-readable error goes to stderr.
        assert run_validators(tmp_path, output_format="json") == 1
        captured = capsys.readouterr()
        doc = json.loads(captured.out)
        assert doc["findings"][0]["ruleId"] == "no-artifacts"
        assert doc["summary"]["scanned"] == 0
        assert "no config artifacts" in captured.err

    @pytest.mark.integration
    def test_main_validate_json_via_cli(self, tmp_path, capsys):
        from unittest.mock import patch

        _copy("insecure_pip.conf", tmp_path, "pip.conf")
        with patch.object(sys, "argv", ["checker.py", "--validate", "--format", "json", str(tmp_path)]):
            assert main() == 1
        doc = json.loads(capsys.readouterr().out)
        assert doc["tool"] == "Dependably.pycheck"
        assert len(doc["findings"]) >= 1
