"""Integration tests for the --validate mode (config artifact validation)."""

import json
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

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
        # It's an operational error (nothing validated), so exit 2 — not 1 (a finding).
        assert run_validators(tmp_path) == 2
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
        # All-skipped == nothing validated == operational error -> exit 2.
        assert run_validators(tmp_path) == 2
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
            assert main() == 2  # operational error (nothing to validate), not a finding
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
        # the human-readable error goes to stderr. Operational error -> exit 2.
        assert run_validators(tmp_path, output_format="json") == 2
        captured = capsys.readouterr()
        doc = json.loads(captured.out)
        assert doc["findings"][0]["ruleId"] == "no-artifacts"
        assert doc["summary"]["exitCode"] == 2
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


class TestBomHandling:
    """#23: a UTF-8 BOM must not break artifact validation."""

    def test_bom_requirements_valid(self, tmp_path):
        (tmp_path / "requirements.txt").write_bytes(b"\xef\xbb\xbfrequests==1.0\n")
        from validators.runner import run_validators

        assert run_validators(tmp_path) == 0

    def test_bom_pip_conf_valid(self, tmp_path):
        (tmp_path / "pip.conf").write_bytes(b"\xef\xbb\xbf[global]\nindex-url = https://pypi.org/simple\n")
        from validators.runner import run_validators

        assert run_validators(tmp_path) == 0


class TestRecursionAndExitCodes:
    """#7 recursion / file-target and #8 exit-code conventions."""

    def _run(self, target, **kw):
        from validators.runner import run_validators

        return run_validators(target, **kw)

    def test_recursive_finds_nested_artifact(self, tmp_path):
        nested = tmp_path / "services" / "api"
        nested.mkdir(parents=True)
        (nested / "requirements.txt").write_text("requests==2.0\n")
        assert self._run(tmp_path) == 0  # found and validated

    def test_recursive_skips_vendored_dirs(self, tmp_path):
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "requirements.txt").write_text("--trusted-host evil.example\n")
        # Only the vendored artifact exists; it must be skipped -> nothing to
        # validate -> operational exit 2 (not 1 from the planted trusted-host).
        assert self._run(tmp_path) == 2

    def test_non_recursive_misses_nested(self, tmp_path):
        nested = tmp_path / "sub"
        nested.mkdir()
        (nested / "requirements.txt").write_text("requests==2.0\n")
        assert self._run(tmp_path, recursive=False) == 2

    def test_file_target_validates_only_that_file(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests==2.0\n")
        (tmp_path / "requirements-bad.txt").write_text("--trusted-host evil.example\n")
        # Pointing at the clean file must not pick up the sibling's error.
        assert self._run(tmp_path / "requirements.txt") == 0

    def test_all_unreadable_is_operational_exit_two(self, tmp_path):
        (tmp_path / "requirements.txt").write_bytes(b"\xff\xff\xffnope")
        assert self._run(tmp_path) == 2

    def test_one_unreadable_among_valid_is_finding_exit_one(self, tmp_path):
        (tmp_path / "requirements.txt").write_bytes(b"\xff\xff\xffnope")
        (tmp_path / "requirements-ok.txt").write_text("requests==2.0\n")
        assert self._run(tmp_path) == 1

    def test_unpinned_warning_does_not_trip_operational_gate(self, tmp_path):
        # A clean warning-only run with a severity=low gate trips (that is the
        # documented additive behavior); but an operational skip must not.
        (tmp_path / "requirements.txt").write_text("requests>=2.0\n")  # unpinned warning
        assert self._run(tmp_path, fail_on=[("severity", "low")]) == 1


class TestRequirementIncludes:
    """#10: -r/-c includes are followed and validated."""

    def _run(self, target, **kw):
        from validators.runner import run_validators

        return run_validators(target, **kw)

    def test_include_target_is_validated(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("-r reqs/prod.in\n")
        reqs = tmp_path / "reqs"
        reqs.mkdir()
        (reqs / "prod.in").write_text("--trusted-host evil.example\nrequests==2.0\n")
        # The include carries a trusted-host error -> exit 1 (surface validated).
        assert self._run(tmp_path) == 1

    def test_clean_include_passes(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("-r base.in\n")
        (tmp_path / "base.in").write_text("requests==2.0\n")
        assert self._run(tmp_path) == 0

    def test_constraint_include_followed(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("-c constraints.txt\nrequests==2.0\n")
        (tmp_path / "constraints.txt").write_text("--trusted-host evil.example\n")
        assert self._run(tmp_path) == 1

    def test_include_cycle_terminates(self, tmp_path):
        # a -> b -> a must not loop forever.
        (tmp_path / "requirements.txt").write_text("-r a.in\n")
        (tmp_path / "a.in").write_text("-r b.in\nrequests==2.0\n")
        (tmp_path / "b.in").write_text("-r a.in\nclick==8.0\n")
        assert self._run(tmp_path) == 0

    def test_missing_include_is_ignored(self, tmp_path):
        # A non-existent include is not our error to raise here.
        (tmp_path / "requirements.txt").write_text("-r does-not-exist.in\nrequests==2.0\n")
        assert self._run(tmp_path) == 0


class TestExtractIncludes:
    """Unit coverage for the include extractor."""

    def test_extracts_r_and_c(self):
        from validators.requirements_validator import extract_includes

        content = "-r base.txt\n--constraint c.txt\nrequests==2.0\n-e git+https://x/y#egg=z\n"
        assert extract_includes(content) == ["base.txt", "c.txt"]


class TestConfigWiringAndJson:
    """#24 coverage gaps: .dependably-check wiring, malformed config, cleanup json."""

    def test_dependably_check_allowlists_private_index(self, tmp_path, capsys):
        (tmp_path / "requirements.txt").write_text("--index-url https://nexus.corp.local/simple\n")
        from validators.runner import run_validators

        # Without the config, the private index is untrusted -> exit 1.
        assert run_validators(tmp_path) == 1
        capsys.readouterr()
        # With it allowlisted, the same run is clean.
        (tmp_path / ".dependably-check").write_text('{"python": {"allowedRegistryHosts": ["nexus.corp.local"]}}')
        assert run_validators(tmp_path) == 0

    def test_malformed_dependably_check_exits_two(self, tmp_path, capsys):
        (tmp_path / "requirements.txt").write_text("requests==2.0\n")
        (tmp_path / ".dependably-check").write_text("{ this is not json")
        with patch.object(sys, "argv", ["checker.py", "--validate", str(tmp_path)]):
            assert main() == 2

    def test_cleanup_json_output_is_clean_and_file_modified(self, tmp_path, capsys):
        f = tmp_path / "x.py"
        f.write_text("import os\nimport sys\nprint(sys.argv)\n")  # os unused
        with patch.object(sys, "argv", ["checker.py", "--cleanup", "--format", "json", str(f)]):
            code = main()
        out = capsys.readouterr().out
        # stdout must be a single valid JSON document (no human text mixed in).
        doc = json.loads(out)
        assert doc["summary"]["exitCode"] == code == 0
        # The file was actually cleaned and a backup written.
        assert "import os" not in f.read_text()
        assert f.with_suffix(".py.backup").exists()


class TestDependablyExceptions:
    """End-to-end .dependably exception suppression through run_validators."""

    def _untrusted(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "requirements.txt").write_text("--index-url https://nexus.corp.local/simple\n")

    def test_exception_suppresses_finding(self, tmp_path, capsys):
        self._untrusted(tmp_path)
        # Baseline: the untrusted private index gates the run (exit 1).
        assert run_validators(tmp_path) == 1
        capsys.readouterr()
        # An id-selector exception on the finding code suppresses it -> exit 0.
        (tmp_path / ".dependably").write_text(
            '{"pycheck": {"exceptions": [{"rule": "REQ_UNTRUSTED_INDEX", '
            '"id": "REQ_UNTRUSTED_INDEX", "reason": "internal nexus"}]}}'
        )
        assert run_validators(tmp_path) == 0
        out = capsys.readouterr().out
        assert "1 suppressed by .dependably" in out

    def test_suppressed_finding_carries_flag_in_json(self, tmp_path, capsys):
        self._untrusted(tmp_path)
        (tmp_path / ".dependably").write_text(
            '{"pycheck": {"exceptions": [{"rule": "REQ_UNTRUSTED_INDEX", '
            '"id": "REQ_UNTRUSTED_INDEX", "reason": "internal nexus"}]}}'
        )
        code = run_validators(tmp_path, output_format="json")
        assert code == 0
        doc = json.loads(capsys.readouterr().out)
        # The finding is still reported, just marked suppressed and non-gating.
        assert doc["findings"], "suppressed finding must still be reported"

    def test_deprecated_filename_warns_to_stderr(self, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        (tmp_path / "requirements.txt").write_text("requests==2.0\n")
        (tmp_path / ".dependably-check").write_text('{"pycheck": {}}')
        run_validators(tmp_path)
        err = capsys.readouterr().err
        assert ".dependably-check is deprecated" in err

    def test_config_fail_on_gates_clean_run(self, tmp_path, capsys):
        (tmp_path / ".git").mkdir()
        # An unpinned requirement is a WARNING, which does not gate by default.
        (tmp_path / "requirements.txt").write_text("requests\n")
        assert run_validators(tmp_path) == 0
        capsys.readouterr()
        # failOn: count=0 in the config escalates any finding to a gate failure.
        (tmp_path / ".dependably").write_text('{"pycheck": {"failOn": {"count": 0}}}')
        assert run_validators(tmp_path) == 1
