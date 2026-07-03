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
- `--config <path>` — path to a `.dependably-check` config (validate mode); by default
  discovered by walking up from the target to the repo root.
- `--fail-on <key>=<value>` — CI gate (repeatable). Exit `1` when a rule trips:
  `severity=<critical|high|moderate|low|info>` trips at or above that level;
  `count=<N>` trips when total findings exceed `N`.
- `--version`, `--help`

### Examples

```bash
import-checker --check ./src               # analyze a project (recursive)
import-checker --cleanup myfile.py         # remove unused imports (creates myfile.py.backup)
import-checker --validate .                # validate packaging config in this repo
import-checker --check ./src --format json --fail-on severity=high
```

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
  "toolVersion": "1.2.0",
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

## Validate mode and `.dependably-check`

In `--validate` mode the tool flags any pip index host that is neither a public default
(`pypi.org`, `files.pythonhosted.org`) nor allowlisted. Declare trusted private registries
once in a repo-root `.dependably-check` JSON file:

```json
{
  "common": { "allowedRegistryHosts": ["dependably.northwardlabs.ca"] },
  "python": { "allowedRegistryHosts": [] }
}
```

The tool reads the union of `common.allowedRegistryHosts` and
`python.allowedRegistryHosts`; other sections are ignored.

## License

Apache-2.0 — see [LICENSE](LICENSE).
