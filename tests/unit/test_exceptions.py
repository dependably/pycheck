"""Unit tests for the ``.dependably`` exception grammar (port of exceptions.test.js)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from validators.exceptions import (  # noqa: E402
    SELECTORS,
    ExceptionConfigError,
    apply_exceptions,
    is_expired,
    match_exception,
    match_glob,
    parse_exceptions,
)

PY_SELECTORS = ["package", "id"]


class TestMatchGlob:
    def test_double_star_across_separators(self):
        assert match_glob("src/**", "src/a/b.py") is True
        assert match_glob("src/**", "src") is True
        assert match_glob("src/**", "lib/a.py") is False

    def test_single_star_within_segment_and_question(self):
        assert match_glob("src/*.py", "src/a.py") is True
        assert match_glob("src/*.py", "src/a/b.py") is False
        assert match_glob("a?.py", "ab.py") is True
        assert match_glob("a?.py", "abc.py") is False

    def test_normalizes_backslashes(self):
        assert match_glob("src/**", "src\\a\\b.cs") is True

    def test_non_string_value(self):
        assert match_glob("src/**", None) is False


class TestParseValidation:
    def test_accepts_well_formed_entry(self):
        out = parse_exceptions(
            [{"rule": "unused-import", "package": "requests", "reason": "vendored"}],
            applicable_selectors=PY_SELECTORS,
        )
        assert len(out) == 1
        assert out[0]["rule"] == "unused-import"
        assert out[0]["selectors"]["package"] == {"name": "requests", "version": None}

    def test_none_yields_empty(self):
        assert parse_exceptions(None, applicable_selectors=PY_SELECTORS) == []

    def test_non_list_raises_invalid_exceptions(self):
        with pytest.raises(ExceptionConfigError) as exc:
            parse_exceptions({}, applicable_selectors=PY_SELECTORS)
        assert exc.value.code == "INVALID_EXCEPTIONS"

    def test_missing_reason(self):
        with pytest.raises(ExceptionConfigError) as exc:
            parse_exceptions([{"rule": "unused-import", "package": "x"}], applicable_selectors=PY_SELECTORS)
        assert exc.value.code == "EXCEPTION_MISSING_REASON"

    def test_empty_reason(self):
        with pytest.raises(ExceptionConfigError) as exc:
            parse_exceptions(
                [{"rule": "unused-import", "package": "x", "reason": "   "}],
                applicable_selectors=PY_SELECTORS,
            )
        assert exc.value.code == "EXCEPTION_MISSING_REASON"

    def test_no_selector(self):
        with pytest.raises(ExceptionConfigError) as exc:
            parse_exceptions([{"rule": "unused-import", "reason": "why"}], applicable_selectors=PY_SELECTORS)
        assert exc.value.code == "EXCEPTION_NO_SELECTOR"

    def test_bad_expires(self):
        with pytest.raises(ExceptionConfigError) as exc:
            parse_exceptions(
                [{"rule": "unused-import", "package": "x", "reason": "y", "expires": "31-12-2026"}],
                applicable_selectors=PY_SELECTORS,
            )
        assert exc.value.code == "EXCEPTION_BAD_EXPIRES"

    def test_inapplicable_selector_own_section_raises(self):
        with pytest.raises(ExceptionConfigError) as exc:
            parse_exceptions(
                [{"rule": "unused-import", "symbol": "Foo.Bar", "reason": "x"}],
                source="own",
                applicable_selectors=PY_SELECTORS,
            )
        assert exc.value.code == "EXCEPTION_BAD_SELECTOR"

    def test_inapplicable_selector_common_section_tolerated(self):
        out = parse_exceptions(
            [{"rule": "unused-import", "symbol": "Foo.Bar", "reason": "x"}],
            source="common",
            applicable_selectors=PY_SELECTORS,
        )
        assert len(out) == 1
        # A tolerated symbol selector simply never matches a pycheck finding.
        assert match_exception(out[0], {"ruleId": "unused-import", "package": "requests"}) is False

    def test_unknown_rule_own_section_raises_when_known_rules_given(self):
        with pytest.raises(ExceptionConfigError) as exc:
            parse_exceptions(
                [{"rule": "no-such", "package": "x", "reason": "y"}],
                source="own",
                applicable_selectors=SELECTORS,
                known_rules=["unused-import"],
            )
        assert exc.value.code == "UNKNOWN_RULE"

    def test_unknown_rule_common_section_tolerated(self):
        out = parse_exceptions(
            [{"rule": "cyclomatic", "path": "src/**", "reason": "y"}],
            source="common",
            applicable_selectors=SELECTORS,
            known_rules=["unused-import"],
        )
        assert len(out) == 1


def _parse(entry):
    return parse_exceptions([entry], source="common", applicable_selectors=SELECTORS)[0]


class TestMatchException:
    def test_package_case_insensitive(self):
        ex = _parse({"rule": "r", "package": "ReQuests", "reason": "x"})
        assert match_exception(ex, {"ruleId": "r", "package": "requests"}) is True

    def test_version_pin_exact(self):
        ex = _parse({"rule": "r", "package": "log4net@2.0.8", "reason": "x"})
        assert match_exception(ex, {"ruleId": "r", "package": "log4net", "version": "2.0.8"}) is True
        assert match_exception(ex, {"ruleId": "r", "package": "log4net", "version": "2.0.15"}) is False

    def test_selectors_within_entry_are_and(self):
        ex = _parse({"rule": "r", "path": "src/Parser/**", "symbol": "Parser.Parse", "reason": "x"})
        assert match_exception(ex, {"ruleId": "r", "path": "src/Parser/P.cs", "symbol": "Parser.Parse"}) is True
        assert match_exception(ex, {"ruleId": "r", "path": "src/Parser/P.cs", "symbol": "Parser.Other"}) is False

    def test_symbol_type_matches_member(self):
        ex = _parse({"rule": "r", "symbol": "Parser", "reason": "x"})
        assert match_exception(ex, {"ruleId": "r", "symbol": "Parser.Parse"}) is True
        assert match_exception(ex, {"ruleId": "r", "symbol": "Other.Parse"}) is False

    def test_id_exact(self):
        ex = _parse({"rule": "r", "id": "GHSA-x", "reason": "x"})
        assert match_exception(ex, {"ruleId": "r", "id": "GHSA-x"}) is True
        assert match_exception(ex, {"ruleId": "r", "id": "GHSA-y"}) is False

    def test_rule_must_match(self):
        ex = _parse({"rule": "r", "package": "x", "reason": "x"})
        assert match_exception(ex, {"ruleId": "other", "package": "x"}) is False

    def test_matches_plain_rule_field(self):
        ex = _parse({"rule": "r", "package": "x", "reason": "x"})
        assert match_exception(ex, {"rule": "r", "package": "x"}) is True


class TestIsExpired:
    def test_past_date_expired(self):
        ex = _parse({"rule": "r", "package": "x", "reason": "x", "expires": "2026-01-01"})
        assert is_expired(ex, "2026-07-03") is True

    def test_future_date_not_expired(self):
        ex = _parse({"rule": "r", "package": "x", "reason": "x", "expires": "2027-01-01"})
        assert is_expired(ex, "2026-07-03") is False

    def test_no_expires_never_expired(self):
        ex = _parse({"rule": "r", "package": "x", "reason": "x"})
        assert is_expired(ex, "2999-01-01") is False


class TestApplyExceptions:
    @staticmethod
    def _p(arr):
        return parse_exceptions(arr, source="own", applicable_selectors=SELECTORS)

    def test_suppresses_matched_keeps_rest(self):
        findings = [
            {"ruleId": "unused-import", "package": "requests"},
            {"ruleId": "unused-import", "package": "flask"},
        ]
        ex = self._p([{"rule": "unused-import", "package": "requests", "reason": "vendored"}])
        r = apply_exceptions(findings, ex)
        assert len(r["active"]) == 1
        assert r["active"][0]["package"] == "flask"
        assert len(r["suppressed"]) == 1
        assert r["suppressed"][0]["suppressed"] is True
        assert r["suppressed"][0]["suppressedBy"] == "vendored"
        assert len(r["unused_exceptions"]) == 0

    def test_reports_unused(self):
        ex = self._p([{"rule": "unused-import", "package": "never", "reason": "stale"}])
        r = apply_exceptions([], ex)
        assert len(r["unused_exceptions"]) == 1
        assert len(r["suppressed"]) == 0

    def test_expired_does_not_suppress(self):
        findings = [{"ruleId": "unused-import", "package": "requests"}]
        ex = self._p([{"rule": "unused-import", "package": "requests", "reason": "temp", "expires": "2026-01-01"}])
        r = apply_exceptions(findings, ex, today="2026-07-03")
        assert len(r["active"]) == 1
        assert len(r["suppressed"]) == 0
        assert len(r["expired_exceptions"]) == 1
