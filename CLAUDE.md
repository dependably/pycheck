# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python Library Checker - A tool to analyze Python files for unused imports and
optionally clean them up, plus validate committed packaging config artifacts.

**Core functionality:**
1. **Check mode** (`--check`): Read-only analysis of unused imports
2. **Cleanup mode** (`--cleanup`): Remove unused imports from files (with backups)
3. **Validate mode** (`--validate`): Validate committed config artifacts
   (`pyproject.toml`, `pip.conf`/`pip.ini`, `requirements*.txt`)

Pure standard library at runtime — no external dependencies. Requires Python 3.9+.

## Architecture

- `src/checker.py` - CLI entry point and the AST-based import checker
  (`ImportChecker`, `ImportInfo`, `_NameReferenceVisitor`). Handles arg parsing,
  file/directory traversal, and `--check`/`--cleanup`/`--validate` dispatch.
  `main()` is the entry point exposed as the `import-checker` console script.
- `src/validators/` - The `--validate` package:
  - `runner.py` - discovers config artifacts under the target and runs the
    matching validator; prints a per-file report and returns the exit code.
  - `pyproject_validator.py`, `pip_conf_validator.py`,
    `requirements_validator.py` - one validator per artifact type.
  - `result.py` - `ValidationResult` plus the error/warning finding types.
  - `_pep508.py` - minimal PEP 508 requirement parsing shared by the validators.

The package supports both the flat layout (tests put `src/` on `sys.path`, so
sibling modules import as `validators.*`) and the installed-wheel layout
(`src.validators.*`). `checker.py` lazily imports the runner under a try/except
to handle both.

## Development Commands

**Running the tool:**
```bash
python src/checker.py --check <file_or_directory>      # read-only analysis
python src/checker.py --cleanup <file_or_directory>    # remove unused imports
python src/checker.py --validate <dir>                 # validate config artifacts
```

**Quality gates (mirror CI in `.gitlab-ci.yml`):**
```bash
black --check src/ tests/
flake8 src/ tests/
mypy src/
python -m pytest tests/ --cov=src --cov-report=term

# Dogfood the tool on this repo (matches the CI unit-tests job)
python src/checker.py --check src/      # src/ only; fixtures carry unused imports on purpose
python src/checker.py --validate .
```

## Implementation Notes

**Import analysis:**
- Parses files with the `ast` module; never executes target code
- Tracks loaded names via `_NameReferenceVisitor`; an import is "used" if its
  name (or alias) is referenced, or re-exported through `__all__`
- Distinguishes `import module` (matches dotted base) from
  `from module import name` (tracks individual names; partial removal supported)
- `from __future__ import ...` is skipped (compiler directives, never "unused")
- Cleanup preserves formatting, handles parenthesized/backslash-continued
  statements, keeps inline comments, and writes a `.backup` before modifying

**CLI conventions:**
- `--check`/`--cleanup`/`--validate` are a required mutually-exclusive group
- `--check` exits non-zero when unused imports are found (lints/gates CI/hooks)
- `--validate` exits non-zero only on errors; warnings (e.g. unpinned deps) pass
- Directory scans recurse by default; `--no-recursive` limits to the top level
  (there is no `--recursive` flag — it was a dead `default=True` no-op, removed)
- `--fail-on <key>=<value>` is the suite-canonical CI gate (repeatable), parsed
  by `parse_fail_on` and evaluated by `gate_trips` in `checker.py`:
  `severity=<critical|high|moderate|low|info>` trips on any finding at/above the
  level (internal `error`->`high`, `warning`->`low`); `count=<N>` trips when
  findings exceed N. A malformed rule is an argparse usage error (exit 2). The
  gate is **additive**: it can only escalate an otherwise-clean run (exit 0) to a
  finding (exit 1) — it never relaxes the default `--check`/`--validate` gates.
  `run_validators` takes a `fail_on` kwarg so the gate also applies in `--validate`.