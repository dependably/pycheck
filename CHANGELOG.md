# Changelog

All notable changes to `pycheck` are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-07-16

### Changed

- **Unpinned dependencies now gate `--validate` by default (`pinned-versions`, error).**
  `REQ_UNPINNED` was a warning, and a warning never fails a `--validate` run — so unpinned
  ranges in `requirements*.txt` were never actually gated by a default run or a pre-commit
  hook built on it. Unpinned findings are now errors under the new cross-tool
  `pinned-versions` rule (suite parity with npm-check 1.8.0 / nucheck), so a default run
  exits 1. Restore the previous behavior per repo via `.dependably`
  (`"pycheck": { "rules": { "pinned-versions": "warn" } }` or `"off"`), or per run with
  `--rule pinned-versions:warn`.

### Added

- **`pyproject.toml` dependencies are pin-checked too.** Unpinned entries in
  `[project.dependencies]` and every `[project.optional-dependencies]` group are flagged
  `PP_UNPINNED` under the same `pinned-versions` rule. Direct-URL requirements count as
  pinned; `[build-system].requires` stays loose by design.
- **The `.dependably` `rules` map is now applied.** Previously parsed and validated but
  never consumed, per-rule severities (`error` / `warn` / `off`) now remap findings before
  reporting and exit-code resolution: `pinned-versions` covers `REQ_UNPINNED`/`PP_UNPINNED`,
  and the `valid-requirements` / `valid-pyproject` / `valid-pip-conf` families cover their
  code prefixes. `off` drops a finding entirely (unlike an `exceptions` entry, which keeps
  it visible as suppressed). Security findings (plaintext credentials, `--trusted-host`,
  untrusted indexes) remain hard errors and cannot be downgraded.
- **`--rule ID:SEVERITY` CLI flag** (repeatable) overrides the config's `rules` map for one
  run — e.g. `--rule pinned-versions:warn`. Unknown ids and bad severities are usage
  errors (exit 2).
- This `CHANGELOG.md`.

### Fixed

- The repo's own dev dependencies (`requirements-dev.txt`, the pyproject `dev` group) are
  now exact-pinned, so pycheck's pre-commit hook passes its own new gate (dogfooding).
