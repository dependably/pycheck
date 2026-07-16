"""Unit tests for the .dependably rule-severity remapping (spec §4.1).

Covers ``apply_rule_severities`` (runner) plus the code->rule mapping helpers
in ``validators.config``.
"""

import os
import sys

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from validators.config import rule_for_code, rule_severity  # noqa: E402
from validators.result import ValidationResult  # noqa: E402
from validators.runner import apply_rule_severities  # noqa: E402


def _result_with(errors=(), warnings=()):
    r = ValidationResult()
    for code, msg in errors:
        r.add_error(msg, code)
    for code, msg in warnings:
        r.add_warning(msg, code)
    return r


def _error_codes(result):
    return {e.code for e in result.errors}


def _warning_codes(result):
    return {w.code for w in result.warnings}


class TestRuleForCode:
    def test_pinned_versions_codes(self):
        assert rule_for_code("REQ_UNPINNED") == "pinned-versions"
        assert rule_for_code("PP_UNPINNED") == "pinned-versions"

    def test_family_prefixes(self):
        assert rule_for_code("REQ_INVALID") == "valid-requirements"
        assert rule_for_code("PP_PARSE") == "valid-pyproject"
        assert rule_for_code("PIP_UNKNOWN_KEY") == "valid-pip-conf"

    def test_operational_codes_unmapped(self):
        assert rule_for_code("skipped-artifact") is None
        assert rule_for_code("unreadable-file") is None


class TestRuleSeverity:
    def test_string_entry(self):
        assert rule_severity({"pinned-versions": "warn"}, "pinned-versions") == "warn"

    def test_list_entry_with_options(self):
        assert rule_severity({"pinned-versions": ["off", {"ignore": []}]}, "pinned-versions") == "off"

    def test_unconfigured_is_none(self):
        assert rule_severity({}, "pinned-versions") is None
        assert rule_severity({"pinned-versions": "warn"}, None) is None


class TestApplyRuleSeverities:
    def test_warn_downgrades_error(self):
        r = _result_with(errors=[("REQ_UNPINNED", "unpinned")])
        out = apply_rule_severities(r, {"pinned-versions": "warn"})
        assert "REQ_UNPINNED" not in _error_codes(out)
        assert "REQ_UNPINNED" in _warning_codes(out)
        assert out.valid is True

    def test_error_upgrades_warning(self):
        r = _result_with(warnings=[("PP_MISSING_LICENSE", "no license")])
        out = apply_rule_severities(r, {"valid-pyproject": "error"})
        assert "PP_MISSING_LICENSE" in _error_codes(out)
        assert out.valid is False

    def test_off_drops_finding_entirely(self):
        r = _result_with(errors=[("REQ_UNPINNED", "unpinned")], warnings=[("REQ_INSECURE_INDEX", "http")])
        out = apply_rule_severities(r, {"pinned-versions": "off", "valid-requirements": "off"})
        assert out.errors == [] and out.warnings == []
        assert out.valid is True

    def test_family_remap_covers_all_codes(self):
        r = _result_with(errors=[("REQ_INVALID", "bad spec")])
        out = apply_rule_severities(r, {"valid-requirements": "warn"})
        assert "REQ_INVALID" in _warning_codes(out)

    def test_unconfigured_rule_keeps_native_severity(self):
        r = _result_with(errors=[("REQ_INVALID", "bad spec")], warnings=[("PP_MISSING_LICENSE", "no license")])
        out = apply_rule_severities(r, {"pinned-versions": "warn"})
        assert "REQ_INVALID" in _error_codes(out)
        assert "PP_MISSING_LICENSE" in _warning_codes(out)

    def test_security_codes_never_downgraded(self):
        # Security findings are always hard errors (suite convention).
        r = _result_with(errors=[("REQ_PLAINTEXT_SECRET", "secret"), ("PIP_TRUSTED_HOST", "no tls")])
        out = apply_rule_severities(r, {"valid-requirements": "off", "valid-pip-conf": "warn"})
        assert _error_codes(out) == {"REQ_PLAINTEXT_SECRET", "PIP_TRUSTED_HOST"}
        assert out.valid is False

    def test_options_entry_form_accepted(self):
        r = _result_with(errors=[("REQ_UNPINNED", "unpinned")])
        out = apply_rule_severities(r, {"pinned-versions": ["warn", {"ignore": []}]})
        assert "REQ_UNPINNED" in _warning_codes(out)

    def test_empty_rules_is_identity(self):
        r = _result_with(errors=[("REQ_UNPINNED", "unpinned")])
        assert apply_rule_severities(r, {}) is r

    def test_skipped_result_untouched(self):
        r = ValidationResult()
        r.info["skipped"] = True
        assert apply_rule_severities(r, {"pinned-versions": "off"}) is r

    def test_line_numbers_preserved_across_remap(self):
        r = ValidationResult()
        r.add_error("unpinned", "REQ_UNPINNED", line=7)
        out = apply_rule_severities(r, {"pinned-versions": "warn"})
        assert out.warnings[0].line == 7
