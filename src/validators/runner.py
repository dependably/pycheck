"""Discover committed config artifacts and run the matching validators.

``run_validators`` is the entry point used by ``checker.py``'s ``--validate``
mode: it discovers ``pyproject.toml`` / ``pip.conf`` / ``requirements*.txt``
under the target, validates each, prints a per-file report, and returns a
process exit code (0 = no errors anywhere, 1 = at least one error).
"""

from __future__ import annotations

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
    from checker import build_json_report, emit_json
except ImportError:  # pragma: no cover - import shim
    from ..checker import build_json_report, emit_json

# Validator signature: takes file text, returns a ValidationResult.
_Validator = Callable[[str], ValidationResult]


def discover_config_files(target: Path) -> List[Tuple[Path, _Validator]]:
    """Return existing config artifacts under ``target`` paired with a validator.

    If ``target`` is a file, its parent directory is scanned.
    """
    directory = target if target.is_dir() else target.parent
    found: List[Tuple[Path, _Validator]] = []

    pyproject = directory / "pyproject.toml"
    if pyproject.is_file():
        found.append((pyproject, validate_pyproject))

    for pip_conf in (directory / "pip.conf", directory / "pip.ini", directory / ".pip" / "pip.conf"):
        if pip_conf.is_file():
            found.append((pip_conf, validate_pip_conf))

    for req in sorted(directory.glob("requirements*.txt")):
        if req.is_file():
            found.append((req, validate_requirements))

    return found


def run_validators(
    target: Path,
    *,
    allowed_hosts: Optional[Sequence[str]] = None,
    config_path: Optional[Path] = None,
    output_format: str = "human",
) -> int:
    """Validate every discovered artifact and print a report. Returns exit code.

    ``allowed_hosts`` -- explicit trusted registry hosts to pass to the index
    validators. When ``None`` they are resolved from the shared
    ``.dependably-check`` config (an explicit ``config_path``, else discovery by
    walking up from ``target``).

    ``output_format`` -- ``"human"`` (default) prints the text report to stdout;
    ``"json"`` emits a single machine-readable JSON document to stdout (kept
    clean) carrying the full set of findings, while status messages go to stderr.
    """
    target = Path(target)
    json_mode = output_format == "json"
    if allowed_hosts is None:
        allowed_hosts = resolve_allowed_hosts(target, config_path)
    files = discover_config_files(target)

    if not files:
        return _report_no_artifacts(target, json_mode)

    findings, total_errors, total_warnings, total_skipped = _collect_results(files, allowed_hosts, json_mode)

    if not json_mode:
        print(
            f"\nValidation complete: {len(files)} file(s), {total_errors} error(s), "
            f"{total_warnings} warning(s), {total_skipped} skipped"
        )

    exit_code = _resolve_exit_code(target, len(files), total_errors, total_skipped, findings, json_mode)

    if json_mode:
        summary = {
            "files": len(files),
            "errors": total_errors,
            "warnings": total_warnings,
            "skipped": total_skipped,
        }
        emit_json(build_json_report("validate", findings, summary, exit_code))

    return exit_code


def _report_no_artifacts(target: Path, json_mode: bool) -> int:
    """Validating nothing is NOT a pass: report the misconfiguration, exit 1.

    Pointing at the wrong directory or a misnamed manifest must be
    distinguishable from "scanned and clean", so this exits non-zero (the
    tool's error path) for CI / hooks to catch.
    """
    message = "no config artifacts (pyproject.toml, pip.conf, requirements*.txt) found to validate"
    print(f"Error: {message} at: {target}", file=sys.stderr)
    if json_mode:
        finding = {"code": "no-artifacts", "file": str(target), "line": None, "message": message, "severity": "error"}
        summary = {"files": 0, "errors": 1, "warnings": 0, "skipped": 0}
        emit_json(build_json_report("validate", [finding], summary, 1))
    return 1


def _collect_results(
    files: List[Tuple[Path, _Validator]],
    allowed_hosts: Sequence[str],
    json_mode: bool,
) -> Tuple[List[Dict[str, Any]], int, int, int]:
    """Validate each artifact; return (findings, errors, warnings, skipped)."""
    findings: List[Dict[str, Any]] = []
    total_errors = 0
    total_warnings = 0
    total_skipped = 0

    for path, validator in files:
        try:
            content = path.read_text(encoding="utf-8")
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
            continue

        result = _invoke(validator, content, allowed_hosts)
        if result.info.get("skipped"):
            total_skipped += 1
        total_errors += len(result.errors)
        total_warnings += len(result.warnings)
        findings.extend(_result_findings(path, result))
        if not json_mode:
            _print_result(path, result)

    return findings, total_errors, total_warnings, total_skipped


def _resolve_exit_code(
    target: Path,
    file_count: int,
    total_errors: int,
    total_skipped: int,
    findings: List[Dict[str, Any]],
    json_mode: bool,
) -> int:
    """Derive the process exit code (and report the all-skipped failure class).

    Every discovered artifact being skipped (e.g. tomllib/tomli unavailable on
    Python < 3.11) means nothing was actually validated -- the same failure
    class as finding no artifacts at all, so it is non-zero, not a pass.
    """
    if total_errors:
        return 1
    if total_skipped != file_count:
        return 0

    message = (
        f"all {file_count} discovered config artifact(s) were skipped "
        "(validator unavailable); nothing was actually validated"
    )
    print(f"Error: {message} at: {target}", file=sys.stderr)
    if json_mode:
        findings.append(
            {"code": "all-skipped", "file": str(target), "line": None, "message": message, "severity": "error"}
        )
    return 1


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


def _invoke(validator: _Validator, content: str, allowed_hosts: Sequence[str]) -> ValidationResult:
    """Call a validator, threading ``allowed_hosts`` into the index validators.

    The pip.conf and requirements validators take an ``allowed_hosts`` keyword;
    pyproject does not. Dispatch by identity so each receives only what it
    accepts.
    """
    if validator is validate_pip_conf:
        return validate_pip_conf(content, allowed_hosts=allowed_hosts)
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
