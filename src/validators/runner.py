"""Discover committed config artifacts and run the matching validators.

``run_validators`` is the entry point used by ``checker.py``'s ``--validate``
mode: it discovers ``pyproject.toml`` / ``pip.conf`` / ``requirements*.txt``
under the target, validates each, prints a per-file report, and returns a
process exit code (0 = no errors anywhere, 1 = at least one error).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Tuple

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


def run_validators(target: Path, *, verbose: bool = False) -> int:
    """Validate every discovered artifact and print a report. Returns exit code."""
    target = Path(target)
    files = discover_config_files(target)

    if not files:
        print(f"No config artifacts (pyproject.toml, pip.conf, requirements*.txt) found under: {target}")
        return 0

    total_errors = 0
    total_warnings = 0

    for path, validator in files:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"Validating: {path}")
            print(f"  could not read file: {e}")
            total_errors += 1
            continue

        result = validator(content)
        total_errors += len(result.errors)
        total_warnings += len(result.warnings)
        _print_result(path, result, verbose=verbose)

    print(f"\nValidation complete: {len(files)} file(s), " f"{total_errors} error(s), {total_warnings} warning(s)")
    return 1 if total_errors else 0


def _print_result(path: Path, result: ValidationResult, *, verbose: bool) -> None:
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
