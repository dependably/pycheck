"""Validate a ``requirements.txt`` -- pip's dependency-consumption surface.

Line-oriented with accurate 1-based line numbers. Validates ordinary
requirements as PEP 508, warns on unpinned dependencies, and -- mirroring the
pip.conf validator -- treats credentials embedded in an index URL and
``--trusted-host`` as ALWAYS errors (see :data:`SECURITY_CODES`).
"""

from __future__ import annotations

import re
from typing import Optional, Sequence
from urllib.parse import urlsplit

from ._pep508 import is_valid_pep508
from .pip_conf_validator import PUBLIC_INDEX_HOSTS, _is_env_ref, _redact
from .result import ValidationResult

SECURITY_CODES: frozenset = frozenset({"REQ_PLAINTEXT_SECRET", "REQ_TRUSTED_HOST", "REQ_UNTRUSTED_INDEX"})

# Pinned to an exact version (``==`` or ``===``).
_PINNED_RE = re.compile(r"(===|==)")
# Lines that are URLs / VCS / editable installs rather than name specifiers.
_URL_REQUIREMENT_RE = re.compile(r"^\s*(-e\s|--editable\s|git\+|hg\+|svn\+|bzr\+|https?://|file:)")
# An option line, e.g. ``--index-url https://...`` or ``-i https://...``.
_OPTION_RE = re.compile(r"^\s*(--?[A-Za-z][\w-]*)(?:[=\s]+(.*))?$")

_INDEX_OPTS = frozenset({"-i", "--index-url", "--extra-index-url"})
_INCLUDE_OPTS = frozenset({"-r", "--requirement", "-c", "--constraint"})


def validate_requirements(content: str, *, allowed_hosts: Optional[Sequence[str]] = None) -> ValidationResult:
    """Validate requirements.txt content.

    ``allowed_hosts`` -- bare hostnames trusted in addition to the public
    defaults (:data:`PUBLIC_INDEX_HOSTS`); any ``--index-url`` /
    ``--extra-index-url`` host outside that union is flagged
    ``REQ_UNTRUSTED_INDEX``. Defaults to empty.
    """
    trusted = PUBLIC_INDEX_HOSTS | {h.strip().lower() for h in (allowed_hosts or []) if h and h.strip()}
    r = ValidationResult()
    r.info["requirements"] = 0
    includes: list[str] = []

    for i, raw in enumerate(content.splitlines(), start=1):
        # Strip inline comments (`` #`` per pip) and surrounding whitespace.
        line = raw.split(" #", 1)[0].strip() if " #" in raw else raw.strip()
        if line and not line.startswith("#"):
            _check_requirement_line(line, i, includes, r, trusted)

    if includes:
        r.info["includes"] = includes
    return r


def _check_requirement_line(
    line: str, lineno: int, includes: list[str], r: ValidationResult, trusted: frozenset
) -> None:
    """Classify and validate a single non-blank, non-comment requirements line."""
    if line.startswith("-"):
        _check_option(line, lineno, includes, r, trusted)
        return

    if _URL_REQUIREMENT_RE.match(line):
        _check_url_requirement(line, lineno, r)
        return

    r.info["requirements"] += 1
    if not is_valid_pep508(line):
        r.add_error(f"invalid requirement: {line!r}", "REQ_INVALID", line=lineno)
    elif not _PINNED_RE.search(line) and ";" not in line:
        r.add_warning(f"unpinned dependency {line!r} (no == pin)", "REQ_UNPINNED", line=lineno)


def _check_option(line: str, lineno: int, includes: list[str], r: ValidationResult, trusted: frozenset) -> None:
    m = _OPTION_RE.match(line)
    if not m:
        return
    opt, value = m.group(1), (m.group(2) or "").strip()

    if opt == "--trusted-host":
        for host in value.split():
            r.add_error(
                f"--trusted-host {host!r} disables TLS certificate verification",
                "REQ_TRUSTED_HOST",
                line=lineno,
            )
        return

    if opt in _INDEX_OPTS:
        for url in value.split():
            _check_index_url(url, opt, lineno, r, trusted=trusted)
        return

    if opt in _INCLUDE_OPTS and value:
        includes.append(value)


def _check_url_requirement(line: str, lineno: int, r: ValidationResult) -> None:
    # Pull the URL out of an editable/plain URL line and scan for credentials.
    candidate = line
    for prefix in ("-e ", "--editable "):
        if candidate.startswith(prefix):
            offset = len(prefix)
            candidate = candidate[offset:].strip()
    url = candidate.split()[0] if candidate.split() else candidate
    _check_index_url(url, "url requirement", lineno, r, scheme_check=False)


def _check_index_url(
    url: str,
    opt: str,
    lineno: int,
    r: ValidationResult,
    *,
    scheme_check: bool = True,
    trusted: Optional[frozenset] = None,
) -> None:
    try:
        parts = urlsplit(url)
    except ValueError:
        return
    if parts.username or parts.password:
        userinfo_ok = _is_env_ref(parts.username) and (parts.password is None or _is_env_ref(parts.password))
        if not userinfo_ok:
            r.add_error(
                f"plaintext credential in {opt} ({_redact(url)}) -- use an env var reference",
                "REQ_PLAINTEXT_SECRET",
                line=lineno,
            )
    if scheme_check and parts.scheme.lower() == "http":
        r.add_warning(f"{opt} over http:// ({url}) -- prefer https://", "REQ_INSECURE_INDEX", line=lineno)

    # Index-trust applies only to actual index options, not editable/url
    # requirements (scheme_check=False marks those).
    if scheme_check and trusted is not None and parts.scheme.lower() in ("http", "https") and parts.hostname:
        host = parts.hostname.lower()
        if host not in trusted:
            r.add_error(
                f"{opt} host {host!r} is not a public index and is not allowlisted "
                f"(add it to .dependably-check allowedRegistryHosts)",
                "REQ_UNTRUSTED_INDEX",
                line=lineno,
            )
