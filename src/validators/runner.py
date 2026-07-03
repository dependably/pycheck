"""Discover committed config artifacts and run the matching validators.

``run_validators`` is the entry point used by ``checker.py``'s ``--validate``
mode: it discovers ``pyproject.toml`` / ``pip.conf`` / ``requirements*.txt``
under the target, validates each, prints a per-file report, and returns a
process exit code per the suite convention: 0 = nothing to report, 1 = a
validation error (a finding), 2 = operational error — nothing could be
validated at all (no artifacts found, or every artifact skipped).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .config import resolve_allowed_hosts
from .pip_conf_validator import validate_pip_conf
from .pyproject_validator import validate_pyproject
from .requirements_validator import validate_requirements
from .result import ValidationResult

# The JSON document is assembled with the shared helpers from ``checker`` so the
# shape matches the import-checker's json output. Flat layout (tests put ``src/``
# on sys.path) exposes them as ``checker``; the installed wheel as ``src.checker``.
try:  # pragma: no cover - import shim
    from checker import build_json_report, emit_json, gate_trips
except ImportError:  # pragma: no cover - import shim
    from ..checker import build_json_report, emit_json, gate_trips

# Validator signature: takes file text, returns a ValidationResult.
_Validator = Callable[[str], ValidationResult]

# Finding codes that describe an operational condition (nothing was validated),
# not a validation finding. They are reported but never feed the --fail-on gate.
_OPERATIONAL_CODES = frozenset({"skipped-artifact", "unreadable-file", "no-artifacts", "all-skipped"})

# Directories never descended into during a recursive validate walk (vendored /
# cache / build output). ``.pip`` is intentionally NOT excluded so the
# conventional ``.pip/pip.conf`` location is still discovered.
_EXCLUDED_WALK_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "site-packages",
        "__pycache__",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".pytest_cache",
        ".eggs",
        "build",
        "dist",
        ".idea",
        ".vscode",
    }
)


def _validator_for_file(path: Path) -> Optional[_Validator]:
    """Return the validator for a config file by its name, or ``None``."""
    name = path.name
    if name == "pyproject.toml":
        return validate_pyproject
    if name in ("pip.conf", "pip.ini"):
        return validate_pip_conf
    if name.startswith("requirements") and name.endswith(".txt"):
        return validate_requirements
    return None


def _discover_in_dir(directory: Path) -> List[Tuple[Path, _Validator]]:
    """Discover the recognized config artifacts directly inside ``directory``."""
    found: List[Tuple[Path, _Validator]] = []
    pyproject = directory / "pyproject.toml"
    if pyproject.is_file():
        found.append((pyproject, validate_pyproject))
    for name in ("pip.conf", "pip.ini"):
        pip_conf = directory / name
        if pip_conf.is_file():
            found.append((pip_conf, validate_pip_conf))
    for req in sorted(directory.glob("requirements*.txt")):
        if req.is_file():
            found.append((req, validate_requirements))
    return found


def discover_config_files(target: Path, recursive: bool = True) -> List[Tuple[Path, _Validator]]:
    """Return existing config artifacts under ``target`` paired with a validator.

    A file ``target`` validates exactly that file (when it is a recognized
    artifact). A directory ``target`` is scanned for artifacts; with
    ``recursive`` (the default) the whole tree is walked, skipping vendored and
    cache directories, so artifacts in subprojects are not silently missed.
    """
    if not target.is_dir():
        validator = _validator_for_file(target) if target.is_file() else None
        return [(target, validator)] if validator else []

    if not recursive:
        directories = [target]
        pip_dir = target / ".pip"
        if pip_dir.is_dir():
            directories.append(pip_dir)
    else:
        directories = []
        for dirpath, dirnames, _files in os.walk(target):
            dirnames[:] = sorted(d for d in dirnames if d not in _EXCLUDED_WALK_DIRS)
            directories.append(Path(dirpath))

    found: List[Tuple[Path, _Validator]] = []
    seen: set = set()
    for directory in directories:
        for path, validator in _discover_in_dir(directory):
            if path not in seen:
                seen.add(path)
                found.append((path, validator))
    return found


def run_validators(
    target: Path,
    *,
    recursive: bool = True,
    allowed_hosts: Optional[Sequence[str]] = None,
    config_path: Optional[Path] = None,
    output_format: str = "human",
    fail_on: Optional[Sequence[Tuple[str, str]]] = None,
) -> int:
    """Validate every discovered artifact and print a report. Returns exit code.

    ``allowed_hosts`` -- explicit trusted registry hosts to pass to the index
    validators. When ``None`` they are resolved from the shared
    ``.dependably-check`` config (an explicit ``config_path``, else discovery by
    walking up from ``target``).

    ``output_format`` -- ``"human"`` (default) prints the text report to stdout;
    ``"json"`` emits a single machine-readable JSON document to stdout (kept
    clean) carrying the full set of findings, while status messages go to stderr.

    ``fail_on`` -- the unified ``--fail-on`` gate rules. Additive: validation
    errors already gate (exit 1); these rules can only escalate an otherwise
    clean run to a finding, never relax the default gate.
    """
    target = Path(target)
    json_mode = output_format == "json"
    if allowed_hosts is None:
        allowed_hosts = resolve_allowed_hosts(target, config_path)
    files = discover_config_files(target, recursive)

    if not files:
        return _report_no_artifacts(target, json_mode)

    findings, total_errors, total_warnings, total_skipped, total_unreadable = _collect_results(
        files, allowed_hosts, json_mode
    )

    if not json_mode:
        print(
            f"\nValidation complete: {len(files)} file(s), {total_errors} error(s), "
            f"{total_warnings} warning(s), {total_skipped} skipped"
        )

    exit_code = _resolve_exit_code(
        target, len(files), total_errors, total_skipped, total_unreadable, findings, json_mode
    )

    # The unified --fail-on gate is additive: escalate a clean run to a finding
    # (exit 1) if any rule trips; never downgrade an existing error exit.
    # Operational findings (skipped/unreadable/no-artifacts) are excluded — the
    # gate rates validation findings, not environment limitations.
    if exit_code == 0 and fail_on:
        gate_findings = [f for f in findings if f.get("code") not in _OPERATIONAL_CODES]
        if gate_trips(gate_findings, list(fail_on)):
            exit_code = 1

    if json_mode:
        emit_json(build_json_report(target, len(files), findings, "config", exit_code))

    return exit_code


def _report_no_artifacts(target: Path, json_mode: bool) -> int:
    """Validating nothing is NOT a pass: report the misconfiguration, exit 2.

    Pointing at the wrong directory or a misnamed manifest must be
    distinguishable from "scanned and clean". This is an OPERATIONAL error
    (nothing could be validated), not a finding, so per the suite convention it
    is exit 2 (not 1) -- still non-zero, so CI / hooks catch it.
    """
    message = "no config artifacts (pyproject.toml, pip.conf, requirements*.txt) found to validate"
    print(f"Error: {message} at: {target}", file=sys.stderr)
    if json_mode:
        finding = {"code": "no-artifacts", "file": str(target), "line": None, "message": message, "severity": "error"}
        emit_json(build_json_report(target, 0, [finding], "config", 2))
    return 2


def _collect_results(
    files: List[Tuple[Path, _Validator]],
    allowed_hosts: Sequence[str],
    json_mode: bool,
) -> Tuple[List[Dict[str, Any]], int, int, int, int]:
    """Validate each artifact.

    Returns ``(findings, errors, warnings, skipped, unreadable)``.
    """
    findings: List[Dict[str, Any]] = []
    total_errors = 0
    total_warnings = 0
    total_skipped = 0
    total_unreadable = 0

    for path, validator in files:
        try:
            # utf-8-sig transparently strips a leading BOM (common on
            # Windows-authored files) so it does not corrupt the first line.
            content = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as e:
            if not json_mode:
                print(f"Validating: {path}")
                print(f"  could not read file: {e}")
            findings.append(
                {
                    "code": "unreadable-file",
                    "file": str(path),
                    "line": None,
                    "message": f"could not read file: {e}",
                    "severity": "error",
                }
            )
            total_errors += 1
            total_unreadable += 1
            continue

        result = _invoke(validator, content, allowed_hosts, path)
        if result.info.get("skipped"):
            total_skipped += 1
        total_errors += len(result.errors)
        total_warnings += len(result.warnings)
        findings.extend(_result_findings(path, result))
        if not json_mode:
            _print_result(path, result)

    return findings, total_errors, total_warnings, total_skipped, total_unreadable


def _resolve_exit_code(
    target: Path,
    file_count: int,
    total_errors: int,
    total_skipped: int,
    total_unreadable: int,
    findings: List[Dict[str, Any]],
    json_mode: bool,
) -> int:
    """Derive the process exit code (and report the nothing-validated failure).

    When every discovered artifact was skipped (e.g. tomllib/tomli unavailable
    on Python < 3.11) OR unreadable (encoding/permission), nothing was actually
    validated -- the same operational failure class as finding no artifacts at
    all, so it is exit 2 (operational error), not 1 (a finding) and not 0 (a
    pass). Only when at least one artifact was validated do real errors gate at
    exit 1.
    """
    validated = file_count - total_skipped - total_unreadable
    if validated > 0:
        return 1 if total_errors else 0

    message = (
        f"none of the {file_count} discovered config artifact(s) could be validated "
        "(all skipped or unreadable); nothing was actually validated"
    )
    print(f"Error: {message} at: {target}", file=sys.stderr)
    if json_mode:
        findings.append(
            {"code": "all-skipped", "file": str(target), "line": None, "message": message, "severity": "error"}
        )
    return 2


def _result_findings(path: Path, result: ValidationResult) -> List[Dict[str, Any]]:
    """Flatten one ``ValidationResult`` into machine-readable finding dicts.

    Skipped artifacts produce a single ``skipped-artifact`` warning so the json
    consumer sees the same information the human ``Skipped: ...`` line conveys.
    """
    if result.info.get("skipped"):
        return [
            {
                "code": "skipped-artifact",
                "file": str(path),
                "line": None,
                "message": str(result.info.get("reason", "validation unavailable")),
                "severity": "warning",
            }
        ]
    out: List[Dict[str, Any]] = []
    for err in result.errors:
        out.append(
            {
                "code": err.code,
                "file": str(path),
                "line": err.line,
                "message": str(err),
                "severity": "error",
            }
        )
    for warn in result.warnings:
        out.append(
            {
                "code": warn.code,
                "file": str(path),
                "line": warn.line,
                "message": warn.message,
                "severity": "warning",
            }
        )
    return out


def _invoke(validator: _Validator, content: str, allowed_hosts: Sequence[str], path: Path) -> ValidationResult:
    """Call a validator, threading ``allowed_hosts`` into the index validators.

    The pip.conf and requirements validators take an ``allowed_hosts`` keyword;
    pyproject does not. pip.conf also takes ``base_dir`` (the config's directory)
    so relative cert paths resolve against the committed config, not the CWD.
    Dispatch by identity so each receives only what it accepts.
    """
    if validator is validate_pip_conf:
        return validate_pip_conf(content, allowed_hosts=allowed_hosts, base_dir=path.parent)
    if validator is validate_requirements:
        return validate_requirements(content, allowed_hosts=allowed_hosts)
    return validator(content)


def _print_result(path: Path, result: ValidationResult) -> None:
    if result.info.get("skipped"):
        print(f"Skipped: {path} ({result.info.get('reason', 'validation unavailable')})")
        return

    print(f"Validating: {path}")
    if not result.errors and not result.warnings:
        print("  OK (no issues)")
        return

    if result.errors:
        print(f"  {len(result.errors)} error(s):")
        for err in result.errors:
            print(f"    {_format_finding(err.code, str(err), err.line)}")
    if result.warnings:
        print(f"  {len(result.warnings)} warning(s):")
        for warn in result.warnings:
            print(f"    {_format_finding(warn.code, warn.message, warn.line)}")


def _format_finding(code: str, message: str, line: Optional[int]) -> str:
    loc = f" line {line}:" if line is not None else ""
    return f"[{code}]{loc} {message}"
