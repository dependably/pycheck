"""Discover committed config artifacts and run the matching validators.

``run_validators`` is the entry point used by ``checker.py``'s ``--validate``
mode: it discovers ``pyproject.toml`` / ``pip.conf`` / ``requirements*.txt``
under the target, validates each, prints a per-file report, and returns a
process exit code (0 = no errors anywhere, 1 = at least one error).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from .config import resolve_allowed_hosts
from .pip_conf_validator import validate_pip_conf
from .pyproject_validator import validate_pyproject
from .requirements_validator import validate_requirements
from .result import ValidationResult

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
) -> int:
    """Validate every discovered artifact and print a report. Returns exit code.

    ``allowed_hosts`` -- explicit trusted registry hosts to pass to the index
    validators. When ``None`` they are resolved from the shared
    ``.dependably-check`` config (an explicit ``config_path``, else discovery by
    walking up from ``target``).
    """
    target = Path(target)
    if allowed_hosts is None:
        allowed_hosts = resolve_allowed_hosts(target, config_path)
    files = discover_config_files(target)

    if not files:
        # Validating nothing is NOT a pass: pointing at the wrong directory or a
        # misnamed manifest must be distinguishable from "scanned and clean".
        # Exit non-zero (through the tool's error path) so CI / hooks catch it.
        print(
            "Error: no config artifacts (pyproject.toml, pip.conf, requirements*.txt) "
            f"found to validate at: {target}",
            file=sys.stderr,
        )
        return 1

    total_errors = 0
    total_warnings = 0
    total_skipped = 0

    for path, validator in files:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"Validating: {path}")
            print(f"  could not read file: {e}")
            total_errors += 1
            continue

        result = _invoke(validator, content, allowed_hosts)
        if result.info.get("skipped"):
            total_skipped += 1
        total_errors += len(result.errors)
        total_warnings += len(result.warnings)
        _print_result(path, result)

    print(
        f"\nValidation complete: {len(files)} file(s), {total_errors} error(s), "
        f"{total_warnings} warning(s), {total_skipped} skipped"
    )

    if total_errors:
        return 1
    # Every discovered artifact was skipped (e.g. tomllib/tomli unavailable on
    # Python < 3.11): nothing was actually validated, so this is not a pass
    # either -- same failure class as finding no artifacts at all.
    if total_skipped == len(files):
        print(
            f"Error: all {len(files)} discovered config artifact(s) were skipped "
            f"(validator unavailable); nothing was actually validated at: {target}",
            file=sys.stderr,
        )
        return 1
    return 0


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
