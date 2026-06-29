"""Integration tests for the --validate mode (config artifact validation)."""

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
