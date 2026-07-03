"""Replay the cross-language ``.dependably`` conformance fixtures.

The fixtures under ``tests/conformance/dependably/cases`` are vendored verbatim
from checker-npm's ``conformance/dependably/`` and pin the spec behaviour every
Dependably tool must implement (docs/dependably-config-spec.md). This adapter
exercises pycheck's exception grammar (``src/validators/exceptions.py``) against
them.

Scope: pycheck ports the exception matcher + parse-validation. This runner
replays the two fixture families that exercise those:

* ``exceptions-*`` -- feed the synthetic findings to the matcher and assert the
  suppressed indices, unused-exception count, and expired-exception count.
* ``validation-exception-*`` -- assert the expected typed error code is raised.

pycheck's applicable selector set is ``["package", "id"]`` (the nucheck subset);
``path``/``symbol`` selectors from ``common`` are tolerated (never match) and are
an ``EXCEPTION_BAD_SELECTOR`` error only in the tool's own section.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from validators.exceptions import (  # noqa: E402
    ExceptionConfigError,
    apply_exceptions,
    parse_exceptions,
)

CASES_DIR = Path(__file__).parent / "dependably" / "cases"

# pycheck's applicable finding selectors (spec §6.7).
APPLICABLE_SELECTORS = ["package", "id"]


def _load(name: str) -> Dict[str, Any]:
    return json.loads((CASES_DIR / name).read_text(encoding="utf-8"))


def _cases(prefix: str) -> List[str]:
    return sorted(p.name for p in CASES_DIR.glob(f"{prefix}*.json"))


def _tool_section(case: Dict[str, Any]) -> Dict[str, Any]:
    """The config object the case materializes under its selected file.

    Cases nest the config under ``files[".dependably"]`` (or the deprecated
    filename); an explicit ``cli.config`` points at another file. This adapter
    only needs the parsed config object, not real on-disk discovery.
    """
    files = case.get("files", {})
    cli = case.get("cli") or {}
    if cli.get("config"):
        return files[cli["config"]]
    for name in (".dependably", ".dependably-check"):
        if name in files:
            return files[name]
    raise AssertionError(f"case {case['name']} has no config file")


def _sections(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``(common, own)`` sections from a materialized config object.

    Fixtures target several tools; for the exception replay we merge every
    non-``common`` tool section as the "own" section so a case authored for
    cslint/nucheck/codemetrics still exercises the matcher. ``common`` is parsed
    tolerantly; the tool section strictly (pycheck's applicability rules).
    """
    common = config.get("common", {}) if isinstance(config.get("common"), dict) else {}
    own: Dict[str, Any] = {}
    for key, value in config.items():
        if key in ("common", "version", "$schema") or not isinstance(value, dict):
            continue
        own = value  # last tool section wins; fixtures carry exactly one
    return common, own


def _parse_all(config: Dict[str, Any], *, strict_own: bool = True) -> List[Dict[str, Any]]:
    """Parse a case's common + tool-section exceptions.

    ``strict_own`` -- when True (validation cases) the tool section is parsed as
    the tool's OWN section, so an inapplicable selector (e.g. ``symbol`` for
    pycheck) raises ``EXCEPTION_BAD_SELECTOR``. When False (matching cases) both
    sections are parsed tolerantly: cross-tool fixtures authored for cslint /
    codemetrics carry ``path`` / ``symbol`` selectors that pycheck's findings
    never emit, and we still want to exercise the matcher against them.
    """
    common, own = _sections(config)
    parsed = parse_exceptions(common.get("exceptions"), source="common", applicable_selectors=APPLICABLE_SELECTORS)
    parsed += parse_exceptions(
        own.get("exceptions"),
        source="own" if strict_own else "common",
        applicable_selectors=APPLICABLE_SELECTORS,
    )
    return parsed


def _finding_shape(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a fixture finding for the matcher.

    Fixtures carry ``package`` as ``name`` or ``name@version``; split on the
    last ``@`` into name + version so version-pin matching works. Null fields are
    dropped so absent selectors don't accidentally match.
    """
    pkg = raw.get("package")
    name, version = pkg, None
    if isinstance(pkg, str):
        at = pkg.rfind("@")
        if at > 0:
            name, version = pkg[:at], pkg[at + 1 :]
    shape: Dict[str, Any] = {"rule": raw.get("rule")}
    if name is not None:
        shape["package"] = name
    if version is not None:
        shape["version"] = version
    for field in ("path", "symbol", "id"):
        if raw.get(field) is not None:
            shape[field] = raw[field]
    return shape


@pytest.mark.parametrize("case_name", _cases("exceptions-"))
def test_exception_matching(case_name: str) -> None:
    case = _load(case_name)
    config = _tool_section(case)
    exceptions = _parse_all(config, strict_own=False)

    findings = [_finding_shape(f) for f in case.get("findings", [])]
    today = case.get("today")
    result = apply_exceptions(findings, exceptions, today=today)

    expect = case["expect"]

    if "suppressedFindings" in expect:
        suppressed_indices = _suppressed_indices(findings, exceptions, today)
        assert suppressed_indices == sorted(expect["suppressedFindings"])

    if "unusedExceptions" in expect:
        # Indices into the resolved exceptions list.
        unused_indices = sorted(i for i, ex in enumerate(exceptions) if ex in result["unused_exceptions"])
        assert unused_indices == sorted(expect["unusedExceptions"])

    if "expiredExceptions" in expect:
        expired_indices = sorted(i for i, ex in enumerate(exceptions) if ex in result["expired_exceptions"])
        assert expired_indices == sorted(expect["expiredExceptions"])

    if "warnings" in expect:
        codes = set(expect["warnings"])
        if "UNUSED_EXCEPTION" in codes:
            assert result["unused_exceptions"]
        if "EXPIRED_EXCEPTION" in codes:
            assert result["expired_exceptions"]


def _suppressed_indices(findings, exceptions, today):
    """Indices of findings suppressed by a live exception (matcher replay)."""
    from validators.exceptions import is_expired, match_exception

    live = [ex for ex in exceptions if not is_expired(ex, today)]
    return sorted(i for i, f in enumerate(findings) if any(match_exception(ex, f) for ex in live))


@pytest.mark.parametrize("case_name", _cases("validation-exception-"))
def test_exception_validation(case_name: str) -> None:
    case = _load(case_name)
    config = _tool_section(case)
    expected_code = case["expect"].get("error")

    if expected_code is None:
        _parse_all(config)  # must not raise
        return

    with pytest.raises(ExceptionConfigError) as exc:
        _parse_all(config)
    assert exc.value.code == expected_code
