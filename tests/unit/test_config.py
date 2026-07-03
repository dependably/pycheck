"""Unit tests for the grown ``.dependably`` unified config loader."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from validators.config import (  # noqa: E402
    SharedConfigError,
    load_config,
    resolve_config_gate,
)
from validators.exceptions import ExceptionConfigError  # noqa: E402


def _write(path, text):
    path.write_text(text, encoding="utf-8")


def _codes(model):
    return {w.code for w in model["warnings"]}


class TestFilenameRename:
    def test_canonical_dependably_no_warning(self, tmp_path):
        _write(tmp_path / ".dependably", '{"pycheck": {"failOn": {"count": 3}}}')
        model = load_config(target=tmp_path)
        assert model["config_path"].name == ".dependably"
        assert _codes(model) == set()

    def test_deprecated_filename_warns(self, tmp_path):
        _write(tmp_path / ".dependably-check", '{"pycheck": {"failOn": {"count": 3}}}')
        model = load_config(target=tmp_path)
        assert model["config_path"].name == ".dependably-check"
        assert "DEPRECATED_FILENAME" in _codes(model)

    def test_both_present_prefers_canonical_and_warns(self, tmp_path):
        _write(tmp_path / ".dependably", '{"pycheck": {"failOn": {"count": 1}}}')
        _write(tmp_path / ".dependably-check", '{"pycheck": {"failOn": {"count": 99}}}')
        model = load_config(target=tmp_path)
        assert model["config_path"].name == ".dependably"
        assert "BOTH_FILES_PRESENT" in _codes(model)
        assert model["fail_on"] == {"count": 1}

    def test_explicit_config_accepts_either_name(self, tmp_path):
        cfg = tmp_path / "custom.json"
        _write(cfg, '{"pycheck": {"failOn": {"count": 7}}}')
        model = load_config(target=tmp_path, config_path=cfg)
        assert model["fail_on"] == {"count": 7}
        assert _codes(model) == set()


class TestSectionAlias:
    def test_python_alias_read_and_warns(self, tmp_path):
        _write(tmp_path / ".dependably", '{"python": {"failOn": {"count": 5}}}')
        model = load_config(target=tmp_path)
        assert "DEPRECATED_ALIAS_SECTION" in _codes(model)
        assert model["fail_on"] == {"count": 5}

    def test_canonical_beats_alias(self, tmp_path):
        _write(
            tmp_path / ".dependably",
            '{"pycheck": {"failOn": {"count": 2}}, "python": {"failOn": {"count": 99}}}',
        )
        model = load_config(target=tmp_path)
        assert "DEPRECATED_ALIAS_SECTION" in _codes(model)
        assert model["fail_on"] == {"count": 2}


class TestValidation:
    def test_version_too_high_errors(self, tmp_path):
        _write(tmp_path / ".dependably", '{"version": 99, "pycheck": {}}')
        with pytest.raises(SharedConfigError) as exc:
            load_config(target=tmp_path)
        assert exc.value.code == "CONFIG_VERSION"

    def test_non_object_root_errors(self, tmp_path):
        _write(tmp_path / ".dependably", "[1, 2, 3]")
        with pytest.raises(SharedConfigError) as exc:
            load_config(target=tmp_path)
        assert exc.value.code == "CONFIG_SHAPE"

    def test_unknown_key_warns(self, tmp_path):
        _write(tmp_path / ".dependably", '{"pycheck": {"exclde": ["typo/**"], "failOn": {"count": 1}}}')
        model = load_config(target=tmp_path)
        assert "UNKNOWN_KEY" in _codes(model)
        assert model["fail_on"] == {"count": 1}

    def test_unknown_key_in_common_warns(self, tmp_path):
        _write(tmp_path / ".dependably", '{"common": {"bogus": 1}}')
        model = load_config(target=tmp_path)
        assert "UNKNOWN_KEY" in _codes(model)

    def test_bad_severity_errors(self, tmp_path):
        _write(tmp_path / ".dependably", '{"pycheck": {"rules": {"unused-import": "fatal"}}}')
        with pytest.raises(SharedConfigError) as exc:
            load_config(target=tmp_path)
        assert exc.value.code == "INVALID_SEVERITY"

    def test_unknown_rule_own_section_errors(self, tmp_path):
        _write(tmp_path / ".dependably", '{"pycheck": {"rules": {"no-such-rule": "error"}}}')
        with pytest.raises(SharedConfigError) as exc:
            load_config(target=tmp_path)
        assert exc.value.code == "UNKNOWN_RULE"

    def test_unknown_rule_in_common_tolerated(self, tmp_path):
        _write(
            tmp_path / ".dependably",
            '{"common": {"rules": {"cyclomatic": ["error", {"max": 25}]}}, '
            '"pycheck": {"rules": {"unused-import": "warn"}}}',
        )
        model = load_config(target=tmp_path)
        assert model["rules"]["unused-import"] == "warn"
        assert "cyclomatic" in model["rules"]

    def test_bad_fail_on_count_errors(self, tmp_path):
        _write(tmp_path / ".dependably", '{"pycheck": {"failOn": {"count": -1}}}')
        with pytest.raises(SharedConfigError) as exc:
            load_config(target=tmp_path)
        assert exc.value.code == "INVALID_FAIL_ON"


class TestMerge:
    def test_rules_merge_per_id(self, tmp_path):
        _write(
            tmp_path / ".dependably",
            '{"common": {"rules": {"unused-import": "error"}}, '
            '"pycheck": {"rules": {"possible-intentional-import": "warn"}}}',
        )
        model = load_config(target=tmp_path)
        assert model["rules"]["unused-import"] == "error"
        assert model["rules"]["possible-intentional-import"] == "warn"

    def test_tool_rule_replaces_common_wholesale(self, tmp_path):
        _write(
            tmp_path / ".dependably",
            '{"common": {"rules": {"unused-import": ["warn", {"a": 1}]}}, '
            '"pycheck": {"rules": {"unused-import": "error"}}}',
        )
        model = load_config(target=tmp_path)
        assert model["rules"]["unused-import"] == "error"

    def test_exclude_unions(self, tmp_path):
        _write(
            tmp_path / ".dependably",
            '{"common": {"exclude": ["dist/**"]}, "pycheck": {"exclude": ["dist/**", "vendor/**"]}}',
        )
        model = load_config(target=tmp_path)
        assert model["exclude"] == ["dist/**", "vendor/**"]

    def test_fail_on_merges_per_key(self, tmp_path):
        _write(
            tmp_path / ".dependably",
            '{"common": {"failOn": {"severity": "high", "count": 20}}, '
            '"pycheck": {"failOn": {"severity": "warning"}}}',
        )
        model = load_config(target=tmp_path)
        assert model["fail_on"] == {"severity": "warning", "count": 20}

    def test_hosts_union_case_insensitive(self, tmp_path):
        _write(
            tmp_path / ".dependably",
            '{"common": {"allowedRegistryHosts": ["Nexus.Corp.Dev"]}, '
            '"pycheck": {"allowedRegistryHosts": ["nexus.corp.dev", "pypi.corp"]}}',
        )
        model = load_config(target=tmp_path)
        assert model["allowed_registry_hosts"] == ["nexus.corp.dev", "pypi.corp"]


class TestExceptions:
    def test_exceptions_parsed(self, tmp_path):
        _write(
            tmp_path / ".dependably",
            '{"pycheck": {"exceptions": [{"rule": "unused-import", "package": "requests", ' '"reason": "vendored"}]}}',
        )
        model = load_config(target=tmp_path)
        assert len(model["exceptions"]) == 1
        assert model["exceptions"][0]["selectors"]["package"] == {"name": "requests", "version": None}

    def test_common_and_own_unioned(self, tmp_path):
        _write(
            tmp_path / ".dependably",
            '{"common": {"exceptions": [{"rule": "unused-import", "id": "A", "reason": "c"}]}, '
            '"pycheck": {"exceptions": [{"rule": "unused-import", "package": "x", "reason": "o"}]}}',
        )
        model = load_config(target=tmp_path)
        assert len(model["exceptions"]) == 2

    def test_bad_selector_in_own_section_errors(self, tmp_path):
        _write(
            tmp_path / ".dependably",
            '{"pycheck": {"exceptions": [{"rule": "unused-import", "symbol": "Foo.Bar", "reason": "x"}]}}',
        )
        with pytest.raises(ExceptionConfigError) as exc:
            load_config(target=tmp_path)
        assert exc.value.code == "EXCEPTION_BAD_SELECTOR"


class TestFailOnGate:
    def test_config_fail_on_becomes_gate(self, tmp_path):
        _write(tmp_path / ".dependably", '{"pycheck": {"failOn": {"severity": "high", "count": 5}}}')
        model = load_config(target=tmp_path)
        rules = resolve_config_gate(model, None)
        assert ("severity", "high") in rules
        assert ("count", "5") in rules

    def test_severity_alias_mapped(self, tmp_path):
        _write(tmp_path / ".dependably", '{"pycheck": {"failOn": {"severity": "warning"}}}')
        model = load_config(target=tmp_path)
        rules = resolve_config_gate(model, None)
        assert rules == [("severity", "moderate")]

    def test_cli_overrides_file(self, tmp_path):
        _write(tmp_path / ".dependably", '{"pycheck": {"failOn": {"count": 5}}}')
        model = load_config(target=tmp_path)
        rules = resolve_config_gate(model, [("severity", "critical")])
        assert rules == [("severity", "critical")]

    def test_no_config_no_gate(self, tmp_path):
        model = load_config(target=tmp_path)
        assert resolve_config_gate(model, None) == []
