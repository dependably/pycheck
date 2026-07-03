"""Load the shared ``.dependably`` repo-root config (spec v1).

The Dependably toolchain (npm-check / nucheck / pycheck / cslint / codemetrics)
reads a single committed ``.dependably`` JSON file so an organisation declares
its trusted private registries, rule severities, CI gate, and finding
suppressions once. This module resolves the slice relevant to *this* tool --
pycheck -- by merging the ``common`` section under the ``pycheck`` section per
the single merge rule (spec §5).

``.dependably`` is canonical; ``.dependably-check`` is a deprecated alias name
kept for the migration window (spec §7). The section key is ``pycheck``;
``python`` is the deprecated alias section (spec §3.3).

Discovery walks UP from the validate target directory (or cwd) to the
filesystem root, preferring ``.dependably`` over ``.dependably-check`` at each
level, stopping at the first hit or at a directory that contains a ``.git``
marker (the repo root). An explicit ``--config`` path skips discovery entirely
and accepts either file name.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .exceptions import parse_exceptions

# Import the project's base exception. Flat layout (tests put ``src/`` on
# sys.path) exposes it as ``checker``; the installed wheel as ``src.checker``.
try:  # pragma: no cover - import shim
    from checker import ImportCheckerError
except ImportError:  # pragma: no cover - import shim
    from ..checker import ImportCheckerError

# Canonical shared-config filename, plus the deprecated alias kept for the
# migration window. Checked in this order at each directory level.
CONFIG_FILENAME = ".dependably"
DEPRECATED_CONFIG_FILENAME = ".dependably-check"
CONFIG_FILENAMES = (CONFIG_FILENAME, DEPRECATED_CONFIG_FILENAME)

# Canonical section key for pycheck, plus the deprecated ecosystem alias.
SECTION_KEY = "pycheck"
DEPRECATED_SECTION_KEY = "python"

# Highest .dependably format version this build understands.
SUPPORTED_CONFIG_VERSION = 1

# Rule severities (rule severity vocabulary, spec §4.2).
SEVERITIES = ("error", "warn", "off")

# Exception selectors a pycheck finding can carry (spec §6.7). ``path``/``symbol``
# are code-location selectors used by the C# tools; ``symbol`` is an error in
# pycheck's own section but tolerated (ignored) in ``common``.
APPLICABLE_SELECTORS = ["package", "id"]

# pycheck's stable rule-id registry (spec §4.4). The lint findings plus the
# config-validation rule families. An unknown rule id in the tool's OWN
# ``rules`` map is UNKNOWN_RULE; in ``common`` it is tolerated (sibling tool).
KNOWN_RULES = [
    # Import lint findings (checker.py).
    "unused-import",
    "possible-intentional-import",
    # Config artifact validation families (validators/*).
    "valid-pyproject",
    "valid-pip-conf",
    "valid-requirements",
]

# Keys pycheck recognizes inside ``common`` / its own section. Unknown keys warn.
_KNOWN_SECTION_KEYS = frozenset(
    {"rules", "exceptions", "exclude", "failOn", "allowedRegistryHosts", "allowedLocalFeeds"}
)

# Finding-severity ladder for failOn.severity, plus the spec §4.2 aliases
# (error -> high, warning/warn -> moderate) that map onto the shared ladder used
# by the CLI gate.
_LADDER = frozenset({"critical", "high", "moderate", "low", "info"})
_SEVERITY_ALIASES = {"error": "high", "warning": "moderate", "warn": "moderate"}
_FAIL_ON_SEVERITIES = _LADDER | set(_SEVERITY_ALIASES)


class SharedConfigError(ImportCheckerError):
    """A malformed shared config. Carries a stable ``code`` (spec §10)."""

    def __init__(self, message: str, code: str, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.context = context or {}


class Warning_:  # noqa: N801 - simple record; leading-cap avoids shadowing builtin
    """A non-gating config warning (spec §11). Rendered to stderr by callers."""

    __slots__ = ("code", "message")

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Warning_) and other.code == self.code and other.message == self.message

    def __repr__(self) -> str:
        return f"Warning_({self.code!r}, {self.message!r})"


# ---------------------------------------------------------------------------
# Public: full config model
# ---------------------------------------------------------------------------


def load_config(target: Optional[Path] = None, config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and resolve the shared ``.dependably`` config for pycheck.

    Returns a dict::

        {
          "config_path": Path | None,
          "rules": { ruleId: severity | [severity, options] },   # merged
          "exceptions": [ parsed exception dicts ],
          "exclude": [ glob strings ],
          "fail_on": { "severity"?: str, "count"?: int } | None,
          "allowed_registry_hosts": [ lowercased hostnames ],
          "warnings": [ Warning_ ],
        }

    Raises :class:`SharedConfigError` (typed ``code``) on a malformed config, and
    :class:`ImportCheckerError` when an explicit ``config_path`` does not exist.
    When no config file is found, returns an empty model (built-in defaults).
    """
    path, disc_warnings = _locate_config(target, config_path)
    if path is None:
        return _empty_model()

    parsed = _read_and_parse(path)
    _validate_shape(parsed, path)

    warnings: List[Warning_] = list(disc_warnings)
    model = _resolve_tool_section(parsed, warnings)
    model["config_path"] = path
    model["allowed_registry_hosts"] = _collect_hosts(parsed)
    model["warnings"] = warnings
    return model


def resolve_allowed_hosts(target: Optional[Path] = None, config_path: Optional[Path] = None) -> List[str]:
    """Return the union of trusted registry hosts for pycheck.

    Thin wrapper over :func:`load_config` kept for the runner / callers that only
    need the allowlist. Discovery / validation semantics are identical.
    """
    hosts: List[str] = load_config(target, config_path)["allowed_registry_hosts"]
    return hosts


def _empty_model() -> Dict[str, Any]:
    return {
        "config_path": None,
        "rules": {},
        "exceptions": [],
        "exclude": [],
        "fail_on": None,
        "allowed_registry_hosts": [],
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _locate_config(target: Optional[Path], config_path: Optional[Path]) -> Tuple[Optional[Path], List[Warning_]]:
    if config_path is not None:
        path = Path(config_path)
        if not path.is_file():
            raise ImportCheckerError(f"config file not found: {path}")
        # --config accepts either file name; emit the deprecation warning only
        # when the explicit file is actually the deprecated name.
        warnings: List[Warning_] = []
        if path.name == DEPRECATED_CONFIG_FILENAME:
            warnings.append(_deprecated_filename_warning())
        return path, warnings
    return _discover_config(target)


def _discover_config(target: Optional[Path]) -> Tuple[Optional[Path], List[Warning_]]:
    """Walk up from ``target``'s directory to the filesystem root.

    At each level ``.dependably`` is preferred over ``.dependably-check``. A
    directory holding a ``.git`` marker is the repo root: its config is honoured
    but the walk does not continue past it.
    """
    start = Path(target) if target is not None else Path.cwd()
    start = start.resolve()
    directory = start if start.is_dir() else start.parent

    for current in [directory, *directory.parents]:
        canonical = current / CONFIG_FILENAME
        deprecated = current / DEPRECATED_CONFIG_FILENAME
        if canonical.is_file():
            warnings: List[Warning_] = []
            if deprecated.is_file():
                warnings.append(_both_files_warning(current))
            return canonical, warnings
        if deprecated.is_file():
            return deprecated, [_deprecated_filename_warning()]
        if (current / ".git").exists():
            break
    return None, []


def _deprecated_filename_warning() -> Warning_:
    return Warning_(
        "DEPRECATED_FILENAME",
        f"{DEPRECATED_CONFIG_FILENAME} is deprecated; rename it to {CONFIG_FILENAME}",
    )


def _both_files_warning(directory: Path) -> Warning_:
    return Warning_(
        "BOTH_FILES_PRESENT",
        f"both {CONFIG_FILENAME} and {DEPRECATED_CONFIG_FILENAME} found in {directory}; "
        f"using {CONFIG_FILENAME} ({DEPRECATED_CONFIG_FILENAME} is ignored -- delete it)",
    )


# ---------------------------------------------------------------------------
# Read + shape validation
# ---------------------------------------------------------------------------


def _read_and_parse(path: Path) -> Any:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise SharedConfigError(f"could not read config file {path}: {e}", "CONFIG_READ", {"path": str(path)})
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise SharedConfigError(f"malformed config file {path}: {e}", "CONFIG_PARSE", {"path": str(path)})


def _validate_shape(parsed: Any, path: Path) -> None:
    if not isinstance(parsed, dict):
        raise SharedConfigError(
            f"malformed config file {path}: top-level value must be a JSON object",
            "CONFIG_SHAPE",
            {"path": str(path)},
        )
    version = parsed.get("version")
    if version is not None:
        if not isinstance(version, int) or isinstance(version, bool) or version > SUPPORTED_CONFIG_VERSION:
            raise SharedConfigError(
                f"unsupported .dependably version {json.dumps(version)} "
                f"(this build supports up to {SUPPORTED_CONFIG_VERSION})",
                "CONFIG_VERSION",
                {"path": str(path)},
            )


# ---------------------------------------------------------------------------
# Section resolution + merge
# ---------------------------------------------------------------------------


def _resolve_tool_section(parsed: Dict[str, Any], warnings: List[Warning_]) -> Dict[str, Any]:
    common = _as_section(parsed.get("common"))
    canonical = parsed.get(SECTION_KEY)
    alias = parsed.get(DEPRECATED_SECTION_KEY)

    tool_raw = canonical if canonical is not None else alias
    tool = _as_section(tool_raw)

    if canonical is None and alias is not None:
        warnings.append(
            Warning_(
                "DEPRECATED_ALIAS_SECTION",
                f'section "{DEPRECATED_SECTION_KEY}" is deprecated; rename it to "{SECTION_KEY}"',
            )
        )
    elif canonical is not None and alias is not None:
        warnings.append(
            Warning_(
                "DEPRECATED_ALIAS_SECTION",
                f'both "{SECTION_KEY}" and "{DEPRECATED_SECTION_KEY}" sections present; using "{SECTION_KEY}"',
            )
        )

    _warn_unknown_keys(common, "common", warnings)
    _warn_unknown_keys(tool, SECTION_KEY, warnings)

    rules = _merge_rules(common.get("rules"), tool.get("rules"))
    exclude = _union_list(common.get("exclude"), tool.get("exclude"))
    fail_on = _merge_fail_on(common.get("failOn"), tool.get("failOn"))

    exceptions = _resolve_exceptions(common, tool)

    return {
        "rules": rules,
        "exclude": exclude,
        "fail_on": fail_on,
        "exceptions": exceptions,
    }


def _as_section(section: Any) -> Dict[str, Any]:
    return section if isinstance(section, dict) else {}


def _warn_unknown_keys(section: Dict[str, Any], label: str, warnings: List[Warning_]) -> None:
    for key in section:
        if key not in _KNOWN_SECTION_KEYS:
            warnings.append(Warning_("UNKNOWN_KEY", f'unknown key "{label}.{key}" in shared config -- ignoring'))


def _merge_rules(common_rules: Any, tool_rules: Any) -> Dict[str, Any]:
    """Merge the ``rules`` maps per rule-id: the tool entry replaces common's
    wholesale (no cross-section option deep-merge, spec §5). Validates each entry.

    Unknown rule ids: an error in the tool's own section (``UNKNOWN_RULE``),
    tolerated in ``common`` (may belong to a sibling tool).
    """
    merged: Dict[str, Any] = {}
    if isinstance(common_rules, dict):
        for rule_id, entry in common_rules.items():
            _validate_severity(entry)  # value validity checked regardless of section
            merged[rule_id] = entry
    if isinstance(tool_rules, dict):
        for rule_id, entry in tool_rules.items():
            if rule_id not in KNOWN_RULES:
                raise SharedConfigError(
                    f'Unknown rule "{rule_id}" (known rules: {", ".join(KNOWN_RULES)})',
                    "UNKNOWN_RULE",
                    {"rule_id": rule_id},
                )
            _validate_severity(entry)
            merged[rule_id] = entry
    return merged


def _validate_severity(entry: Any) -> None:
    """Validate a rule entry: severity string or ``[severity, options]``."""
    if isinstance(entry, str):
        severity = entry
        options: Any = {}
    elif isinstance(entry, list) and len(entry) >= 1:
        severity = entry[0]
        if len(entry) > 1:
            options = entry[1]
            if not isinstance(options, dict):
                raise SharedConfigError(
                    f"Rule options must be an object, got: {json.dumps(options)}",
                    "INVALID_RULE_OPTIONS",
                )
    else:
        raise SharedConfigError(f"Invalid rule entry: {json.dumps(entry)}", "INVALID_SEVERITY")

    if severity not in SEVERITIES:
        raise SharedConfigError(
            f'Invalid severity "{severity}" (expected: {", ".join(SEVERITIES)})',
            "INVALID_SEVERITY",
        )


def _union_list(a: Any, b: Any) -> List[Any]:
    """Union two lists (ordinal dedupe, order-preserving), tolerating non-lists."""
    out: List[Any] = []
    seen: Set[Any] = set()
    for value in (a if isinstance(a, list) else []) + (b if isinstance(b, list) else []):
        key = value if isinstance(value, (str, int, float, bool)) else json.dumps(value, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _merge_fail_on(common_fail_on: Any, tool_fail_on: Any) -> Optional[Dict[str, Any]]:
    """Merge two ``failOn`` maps per key (tool wins). Validates and returns None
    when neither sets a key."""
    c = common_fail_on if isinstance(common_fail_on, dict) else {}
    t = tool_fail_on if isinstance(tool_fail_on, dict) else {}
    merged: Dict[str, Any] = {**c, **t}
    if "severity" not in merged and "count" not in merged:
        if common_fail_on is not None and not isinstance(common_fail_on, dict):
            raise SharedConfigError("failOn must be an object", "INVALID_FAIL_ON")
        if tool_fail_on is not None and not isinstance(tool_fail_on, dict):
            raise SharedConfigError("failOn must be an object", "INVALID_FAIL_ON")
        return None

    result: Dict[str, Any] = {}
    if "severity" in merged:
        severity = merged["severity"]
        if not isinstance(severity, str) or severity.lower() not in _FAIL_ON_SEVERITIES:
            raise SharedConfigError(
                f"failOn.severity must be one of critical/high/moderate/low/info, got: {json.dumps(severity)}",
                "INVALID_FAIL_ON",
            )
        result["severity"] = severity
    if "count" in merged:
        count = merged["count"]
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise SharedConfigError(
                f"failOn.count must be a non-negative integer, got: {json.dumps(count)}",
                "INVALID_FAIL_ON",
            )
        result["count"] = count
    return result


def _resolve_exceptions(common: Dict[str, Any], tool: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse exceptions from ``common`` (tolerant) + the tool section (strict
    selector checks). Byte-identical entries are de-duplicated (spec §6.6)."""
    common_ex = parse_exceptions(common.get("exceptions"), source="common", applicable_selectors=APPLICABLE_SELECTORS)
    own_ex = parse_exceptions(tool.get("exceptions"), source="own", applicable_selectors=APPLICABLE_SELECTORS)

    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for ex in [*common_ex, *own_ex]:
        key = json.dumps(ex["_raw"], sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(ex)
    return out


# ---------------------------------------------------------------------------
# Registry hosts (union of common + tool section, case-insensitive)
# ---------------------------------------------------------------------------


def _collect_hosts(parsed: Dict[str, Any]) -> List[str]:
    tool_raw = parsed.get(SECTION_KEY)
    if tool_raw is None:
        tool_raw = parsed.get(DEPRECATED_SECTION_KEY)
    hosts: List[str] = []
    seen: Set[str] = set()
    for section in (parsed.get("common"), tool_raw):
        for host in _section_hosts(section):
            if host not in seen:
                seen.add(host)
                hosts.append(host)
    return hosts


def _section_hosts(section: Any) -> List[str]:
    if not isinstance(section, dict):
        return []
    raw_hosts = section.get("allowedRegistryHosts")
    if raw_hosts is None:
        return []
    if not isinstance(raw_hosts, list):
        raise SharedConfigError(
            "'allowedRegistryHosts' must be a JSON array",
            "CONFIG_SHAPE",
        )
    out: List[str] = []
    for host in raw_hosts:
        if not isinstance(host, str):
            raise SharedConfigError(
                "'allowedRegistryHosts' entries must be strings",
                "CONFIG_SHAPE",
            )
        normalized = host.strip().lower()
        if normalized:
            out.append(normalized)
    return out


def resolve_config_gate(
    model: Dict[str, Any], cli_fail_on: Optional[Sequence[Tuple[str, str]]]
) -> List[Tuple[str, str]]:
    """Return the effective ``--fail-on`` rules: CLI overrides the file's ``failOn``.

    The file's ``failOn`` (spec §4.3) is the base; any CLI ``--fail-on`` replaces
    it wholesale (spec §4.3: "A CLI --fail-on MUST override the file's failOn").
    """
    if cli_fail_on:
        return list(cli_fail_on)
    fail_on = model.get("fail_on")
    if not fail_on:
        return []
    rules: List[Tuple[str, str]] = []
    if "severity" in fail_on:
        severity = str(fail_on["severity"]).lower()
        # Map the spec §4.2 aliases onto the shared ladder the CLI gate speaks.
        rules.append(("severity", _SEVERITY_ALIASES.get(severity, severity)))
    if "count" in fail_on:
        rules.append(("count", str(fail_on["count"])))
    return rules
