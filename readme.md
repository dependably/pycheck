# pycheck

Find and remove unused imports in Python files, and validate your committed packaging
config (`pyproject.toml`, `pip.conf`, `requirements*.txt`). Pure standard library — no
runtime dependencies — with AST-based analysis, safe backups, and machine-readable output
for CI.

[![Python versions](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## Install

Requires Python 3.9 or later.

```bash
pip install Dependably.pycheck
```

This installs the `import-checker` command (also available as `python-import-checker`).

## Usage

```bash
import-checker [--check | --cleanup | --validate] <target> [options]
```

- `--check` — read-only analysis of unused imports (no changes)
- `--cleanup` — remove unused imports, writing a `.backup` beside each modified file
- `--validate` — validate committed packaging config under `<target>`

`<target>` is a `.py`/`.pyw` file or a directory (directories recurse by default).

Options:

- `--no-recursive` — scan only the top directory level
- `--verbose`, `-v` — detailed output
- `--format {human,json}` — output format (default `human`). `json` writes one
  machine-readable document to stdout; status/progress go to stderr.
- `--config <path>` — path to a `.dependably` config (or the deprecated
  `.dependably-check` alias) for validate mode; by default discovered by walking up
  from the target to the repo root.
- `--fail-on <key>=<value>` — CI gate (repeatable). Exit `1` when a rule trips:
  `severity=<critical|high|moderate|low|info>` trips at or above that level;
  `count=<N>` trips when total findings exceed `N`.
- `--remove-possible-reexports` — cleanup-mode opt-in: also remove imports flagged as
  possibly-intentional (see below). Off by default.
- `--version`, `--help`

### Examples

```bash
import-checker --check ./src               # analyze a project (recursive)
import-checker --cleanup myfile.py         # remove unused imports (creates myfile.py.backup)
import-checker --validate .                # validate packaging config in this repo
import-checker --check ./src --format json --fail-on severity=high
```

### Check-mode output

`--check` is quiet by default: a clean file prints nothing (pass `--verbose` to see every
file, including "No unused imports found"). A file with findings prints its unused
imports, real line-per-name, followed by a `run --cleanup` hint when any were found:

```
Analyzing: src/server.py
  Found 1 unused import:
    Line 12: json  (from typing)

Analysis complete:
  Files processed: 3
  1 unused import found
  2 files clean

Run 'import-checker --cleanup src' to fix (writes a .backup beside each modified file;
possibly-intentional imports are left in place unless --remove-possible-reexports is
also set).
```

### Possibly-intentional imports

An import that is never referenced by name can still be intentional: a module imported
purely to run its side effects at import time (e.g. a decorator that registers a
plugin/tool), or a package's re-exported public API, looks identical to dead code by
reference counting alone. `import-checker` downgrades these shapes to a separate
"possibly-intentional" category instead of calling them unused, and `--cleanup` never
removes them without the `--remove-possible-reexports` opt-in:

- imports in a package's `__init__.py` (overwhelmingly re-exports),
- a bare, dotted whole-module import (`import pkg.sub`) that is never attribute-accessed,
- a `from pkg import a, b, c` statement where **every** name (3 or more) is unused — the
  shape a plugin/tool-registry import takes, where each name exists only to trigger a
  decorator side effect, never to be referenced by its local identifier.

They are reported under the `possible-intentional-import` JSON `ruleId` (severity `low`,
vs. `unused-import`'s `high`) so CI/editor consumers can tell "clear dead code" apart from
"review before removing".

## Exit codes

| Code | Meaning |
| ---- | ------- |
| `0`  | Clean — no findings (also `--help` / `--version`). |
| `1`  | Findings — unused imports, validation errors, or a tripped `--fail-on` gate. |
| `2`  | Usage error or an operational/internal error. |

`--validate` exits non-zero only on **errors**; warnings (such as unpinned dependencies)
are reported but still pass.

## JSON output

`--format json` writes one object to stdout following the shared Dependably finding
schema, so every tool in the suite parses the same way:

```json
{
  "tool": "Dependably.pycheck",
  "toolVersion": "1.2.1",
  "schemaVersion": "1.0",
  "target": "src",
  "summary": {
    "scanned": 1,
    "findings": 1,
    "bySeverity": { "critical": 0, "high": 1, "moderate": 0, "low": 0, "info": 0 },
    "exitCode": 1
  },
  "findings": [
    {
      "severity": "high",
      "ruleId": "unused-import",
      "category": "lint",
      "message": "unused import: import os",
      "location": { "file": "src/x.py", "line": 1, "column": null },
      "remediation": "Remove the unused import."
    }
  ]
}
```

## Validate mode and `.dependably`

In `--validate` mode the tool flags any pip index host that is neither a public default
(`pypi.org`, `files.pythonhosted.org`) nor allowlisted. Declare trusted private registries
once in a repo-root `.dependably` JSON file (the deprecated `.dependably-check` filename is
still read for the migration window, with a one-time stderr warning):

```json
{
  "common": { "allowedRegistryHosts": ["dependably.northwardlabs.ca"] },
  "pycheck": { "allowedRegistryHosts": [] }
}
```

The tool reads the union of `common.allowedRegistryHosts` and `pycheck.allowedRegistryHosts`
(the section key `python` is the deprecated alias, still read with a warning); other
top-level sections are ignored.

### Rules, exceptions, and the CI gate

`.dependably` is the shared, cross-tool config for the whole Dependably suite. Alongside
the registry allowlist, pycheck reads its own section (`pycheck`) plus `common` for:

- `rules` — per-rule severity (`error` / `warn` / `off`).
- `failOn` — the file form of the `--fail-on` CI gate (`{ "severity": ..., "count": ... }`).
  A CLI `--fail-on` overrides it.
- `exceptions` — targeted suppression of specific findings without disabling a rule or
  excluding whole files. Each entry needs a `rule` and a `reason`, plus at least one
  selector (`package`, `id`); a `package@version` suffix pins to an exact version, and an
  optional `expires: YYYY-MM-DD` date makes the exception inert (and warned about) after it
  passes. Suppressed findings are still reported (with `"suppressed": true` in JSON) but no
  longer gate the run.

```json
{
  "pycheck": {
    "failOn": { "severity": "high" },
    "exceptions": [
      { "rule": "REQ_UNTRUSTED_INDEX", "id": "REQ_UNTRUSTED_INDEX", "reason": "internal nexus" }
    ]
  }
}
```

`common` and `pycheck` are merged per the suite convention: scalars and `failOn` in the tool
section override `common`; list keys (`exclude`, `exceptions`, `allowedRegistryHosts`) union;
`rules` merge per rule-id.

## License

Apache-2.0 — see [LICENSE](LICENSE).
