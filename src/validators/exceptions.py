"""Port of the ``.dependably`` exception grammar (spec §6).

This mirrors checker-npm's ``src/exceptions.js`` semantics exactly so the
cross-language conformance fixtures under ``conformance/dependably/`` pass in
every runtime. An exception suppresses SPECIFIC findings so a run does not fail
on them, without excluding whole files (``exclude``) or disabling a rule
globally (``rules: {id: "off"}``). Each entry is::

    { rule, package?, path?, id?, reason, expires? }

``rule`` + ``reason`` are mandatory; at least one selector is required; all
selectors present on an entry must match a finding (AND within an entry, OR
across entries). Suppressed findings are still counted and reported.

pycheck findings carry ``package`` / ``path`` / ``id`` selectors; ``symbol`` is
a code-location selector used by the C# tools -- it is an error in pycheck's own
section but tolerated (ignored) in ``common`` (spec §6.7). The default applicable
set for pycheck is ``["package", "id"]`` (matching the nucheck subset).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Union

# Import the project's base exception. Flat layout (tests put ``src/`` on
# sys.path) exposes it as ``checker``; the installed wheel as ``src.checker``.
try:  # pragma: no cover - import shim
    from checker import ImportCheckerError
except ImportError:  # pragma: no cover - import shim
    from ..checker import ImportCheckerError


# The four finding selectors, in a stable order for messages.
SELECTORS = ["package", "path", "symbol", "id"]

_EXPIRES_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Regex metacharacters escaped when translating a glob literal to a pattern.
_GLOB_META = re.compile(r"[.+^${}()|\[\]\\]")


class ExceptionConfigError(ImportCheckerError):
    """A malformed exception entry.

    Subclass of :class:`ImportCheckerError` so an escaped instance is still
    caught by ``main()``; carries a stable ``code`` (spec §10) and a ``context``
    dict for diagnostics.
    """

    def __init__(self, message: str, code: str, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.context = context or {}


# --- glob (portable subset: ** any depth, * within a segment, ? one char) ----


def _glob_to_regexp(glob: str) -> "re.Pattern[str]":
    parts: List[str] = []
    i = 0
    n = len(glob)
    while i < n:
        c = glob[i]
        if c == "*" and i + 1 < n and glob[i + 1] == "*":
            if i + 2 < n and glob[i + 2] == "/":
                # ``**/`` -- zero or more leading path segments.
                parts.append("(?:.*/)?")
                i += 3
            elif parts and parts[-1].endswith("/"):
                # ``foo/**`` at the end -- match ``foo`` and ``foo/anything``.
                parts[-1] = parts[-1][:-1] + "(?:/.*)?"
                i += 2
            else:
                # bare ``**`` -- any number of characters including separators.
                parts.append(".*")
                i += 2
        elif c == "*":
            # ``*`` -- anything except a path separator.
            parts.append("[^/]*")
            i += 1
        elif c == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(_GLOB_META.sub(lambda m: "\\" + m.group(0), c))
            i += 1
    return re.compile("^" + "".join(parts) + "$")


def match_glob(glob: str, value: Any) -> bool:
    """Match a POSIX-style path against a portable glob (``**``, ``*``, ``?``)."""
    if not isinstance(value, str):
        return False
    return _glob_to_regexp(glob).match(value.replace("\\", "/")) is not None


# --- parsing / validation ----------------------------------------------------


def _ensure_list(raw: Any, context: Dict[str, Any]) -> List[Any]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ExceptionConfigError("exceptions must be an array", "INVALID_EXCEPTIONS", context)
    return raw


def _split_package_selector(pkg: str) -> Dict[str, Optional[str]]:
    """Split a ``package`` selector into ``{name, version}``.

    The version is optional, from an ``@<version>`` suffix. Scoped names keep
    their leading ``@`` (only an ``@`` after the first char introduces a version).
    """
    at = pkg.rfind("@")
    if at > 0:
        return {"name": pkg[:at].lower(), "version": pkg[at + 1 :]}
    return {"name": pkg.lower(), "version": None}


def parse_exceptions(
    raw: Any,
    *,
    source: str = "own",
    applicable_selectors: Optional[Sequence[str]] = None,
    known_rules: Optional[Sequence[str]] = None,
    config_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Parse and validate a raw ``exceptions`` array into normalized entries.

    ``source`` -- ``"own"`` enforces selector applicability (spec §6.7);
    ``"common"`` tolerates selectors this tool never emits.
    ``applicable_selectors`` -- selectors this tool's findings can carry
    (pycheck: ``["package", "id"]``). Defaults to all four.
    ``known_rules`` -- if given, an unknown ``rule`` in an ``own`` entry raises
    ``UNKNOWN_RULE`` (spec §8); in ``common`` it is tolerated.

    Returns a list of dicts::

        { "rule", "reason", "expires", "source", "selectors", "_raw" }
    """
    applicable = list(applicable_selectors) if applicable_selectors is not None else list(SELECTORS)
    entries = _ensure_list(raw, {"configPath": config_path})
    return [
        _parse_entry(entry, index, source, applicable, known_rules, config_path) for index, entry in enumerate(entries)
    ]


def _parse_entry(
    entry: Any,
    index: int,
    source: str,
    applicable: List[str],
    known_rules: Optional[Sequence[str]],
    config_path: Optional[str],
) -> Dict[str, Any]:
    """Validate + normalize one exception entry (raises on any violation)."""
    at = {"configPath": config_path, "source": source, "index": index}
    if not isinstance(entry, dict):
        raise ExceptionConfigError(f"exception #{index} must be an object", "INVALID_EXCEPTIONS", at)

    rule = entry.get("rule")
    if not isinstance(rule, str) or rule.strip() == "":
        raise ExceptionConfigError(f'exception #{index} is missing "rule"', "EXCEPTION_MISSING_RULE", at)

    reason = entry.get("reason")
    if not isinstance(reason, str) or reason.strip() == "":
        raise ExceptionConfigError(
            f'exception for rule "{rule}" is missing a non-empty "reason"', "EXCEPTION_MISSING_REASON", at
        )

    _validate_selectors(entry, rule, source, applicable, at)
    expires = _validate_expires(entry, rule, at)

    if source == "own" and known_rules is not None and rule not in known_rules:
        raise ExceptionConfigError(
            f'Unknown rule "{rule}" in exception (known rules: {", ".join(known_rules)})', "UNKNOWN_RULE", at
        )

    return {
        "rule": rule,
        "reason": reason,
        "expires": expires or None,
        "source": source,
        "selectors": _build_selectors(entry, rule),
        "_raw": entry,
    }


def _validate_selectors(
    entry: Dict[str, Any], rule: str, source: str, applicable: List[str], at: Dict[str, Any]
) -> None:
    present = [s for s in SELECTORS if entry.get(s) is not None]
    if not present:
        raise ExceptionConfigError(
            f'exception for rule "{rule}" needs at least one selector ({", ".join(SELECTORS)})',
            "EXCEPTION_NO_SELECTOR",
            at,
        )
    for sel in present:
        value = entry.get(sel)
        if not isinstance(value, str) or value.strip() == "":
            raise ExceptionConfigError(
                f'exception selector "{sel}" for rule "{rule}" must be a non-empty string',
                "EXCEPTION_BAD_SELECTOR",
                at,
            )
        # A selector this tool's findings never carry is an error in the tool's
        # OWN section but is tolerated in ``common`` (it simply never matches).
        if source == "own" and sel not in applicable:
            raise ExceptionConfigError(
                f'exception selector "{sel}" is not applicable to this tool ' f'(applicable: {", ".join(applicable)})',
                "EXCEPTION_BAD_SELECTOR",
                at,
            )


def _validate_expires(entry: Dict[str, Any], rule: str, at: Dict[str, Any]) -> Optional[str]:
    expires = entry.get("expires")
    if expires is not None and (
        not isinstance(expires, str) or not _EXPIRES_RE.match(expires) or not _parseable_date(expires)
    ):
        raise ExceptionConfigError(
            f'exception "expires" for rule "{rule}" must be a valid YYYY-MM-DD date', "EXCEPTION_BAD_EXPIRES", at
        )
    return expires


def _build_selectors(entry: Dict[str, Any], rule: str) -> Dict[str, Any]:
    selectors: Dict[str, Any] = {"rule": rule}
    if entry.get("package") is not None:
        selectors["package"] = _split_package_selector(entry["package"])
    for sel in ("path", "symbol", "id"):
        if entry.get(sel) is not None:
            selectors[sel] = entry[sel]
    return selectors


def _parseable_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


# --- matching ----------------------------------------------------------------


def _to_date(today: Union[None, str, date, datetime]) -> date:
    if isinstance(today, datetime):
        return today.date()
    if isinstance(today, date):
        return today
    if isinstance(today, str):
        return datetime.strptime(today, "%Y-%m-%d").date()
    return datetime.now(timezone.utc).date()


def is_expired(exception: Dict[str, Any], today: Union[None, str, date, datetime] = None) -> bool:
    """True when an exception's ``expires`` date is strictly before ``today``."""
    expires = exception.get("expires")
    if not expires:
        return False
    exp = datetime.strptime(expires, "%Y-%m-%d").date()
    return _to_date(today) > exp


def _match_package(sel: Dict[str, Optional[str]], finding: Dict[str, Any]) -> bool:
    name = str(finding.get("package") or "").lower()
    if name != sel["name"]:
        return False
    if sel["version"] is None:
        return True
    version = finding.get("version")
    return version is not None and str(version) == sel["version"]


def _match_symbol(sel_symbol: str, finding_symbol: Any) -> bool:
    if not isinstance(finding_symbol, str):
        return False
    # ``Type`` matches ``Type`` and any ``Type.Member``; ``Type.Member`` exact.
    return finding_symbol == sel_symbol or finding_symbol.startswith(sel_symbol + ".")


def match_exception(exception: Dict[str, Any], finding: Dict[str, Any]) -> bool:
    """True when every selector on ``exception`` matches ``finding`` (AND).

    Expiry is NOT consulted here -- callers skip expired entries via
    :func:`is_expired`. A finding is a dict with ``rule``/``ruleId``,
    ``package``/``version``/``path``/``symbol``/``id``.
    """
    s = exception["selectors"]
    finding_rule = finding.get("rule") if finding.get("rule") is not None else finding.get("ruleId")
    if s["rule"] != finding_rule:
        return False
    if "package" in s and not _match_package(s["package"], finding):
        return False
    if "path" in s and not match_glob(s["path"], finding.get("path")):
        return False
    if "symbol" in s and not _match_symbol(s["symbol"], finding.get("symbol")):
        return False
    if "id" in s and s["id"] != finding.get("id"):
        return False
    return True


def apply_exceptions(
    findings: Sequence[Dict[str, Any]],
    exceptions: Sequence[Dict[str, Any]],
    *,
    today: Union[None, str, date, datetime] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Partition findings by the exceptions, returning suppression bookkeeping.

    Returns a dict with:

    * ``active`` -- findings that still gate (kept)
    * ``suppressed`` -- findings matched by a live exception (each carries
      ``suppressed: True`` + ``suppressedBy``)
    * ``unused_exceptions`` -- exceptions that matched no finding
    * ``expired_exceptions`` -- exceptions past their ``expires`` date (never
      suppress)
    """
    live: List[Dict[str, Any]] = []
    expired: List[Dict[str, Any]] = []
    for ex in exceptions:
        (expired if is_expired(ex, today) else live).append(ex)

    used_ids = set()
    active: List[Dict[str, Any]] = []
    suppressed: List[Dict[str, Any]] = []

    for finding in findings:
        hit = next((ex for ex in live if match_exception(ex, finding)), None)
        if hit is not None:
            used_ids.add(id(hit))
            suppressed.append({**finding, "suppressed": True, "suppressedBy": hit["reason"]})
        else:
            active.append(finding)

    unused = [ex for ex in live if id(ex) not in used_ids]
    return {
        "active": active,
        "suppressed": suppressed,
        "unused_exceptions": unused,
        "expired_exceptions": expired,
    }
