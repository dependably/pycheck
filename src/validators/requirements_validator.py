"""Validate a ``requirements.txt`` -- pip's dependency-consumption surface.

Line-oriented with accurate 1-based line numbers. Validates ordinary
requirements as PEP 508, warns on unpinned dependencies, and -- mirroring the
pip.conf validator -- treats credentials embedded in an index URL and
``--trusted-host`` as ALWAYS errors (see :data:`SECURITY_CODES`).
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from ._pep508 import is_valid_pep508
from .pip_conf_validator import _is_env_ref, _redact
from .result import ValidationResult

SECURITY_CODES: frozenset = frozenset({"REQ_PLAINTEXT_SECRET", "REQ_TRUSTED_HOST"})

# Pinned to an exact version (``==`` or ``===``).
_PINNED_RE = re.compile(r"(===|==)")
# Lines that are URLs / VCS / editable installs rather than name specifiers.
_URL_REQUIREMENT_RE = re.compile(r"^\s*(-e\s|--editable\s|git\+|hg\+|svn\+|bzr\+|https?://|file:)")
# An option line, e.g. ``--index-url https://...`` or ``-i https://...``.
_OPTION_RE = re.compile(r"^\s*(--?[A-Za-z][\w-]*)(?:[=\s]+(.*))?$")

_INDEX_OPTS = frozenset({"-i", "--index-url", "--extra-index-url"})
_INCLUDE_OPTS = frozenset({"-r", "--requirement", "-c", "--constraint"})


def validate_requirements(content: str) -> ValidationResult:
    """Validate requirements.txt content."""
    r = ValidationResult()
    r.info["requirements"] = 0
    includes: list[str] = []

    for i, raw in enumerate(content.splitlines(), start=1):
        # Strip inline comments (`` #`` per pip) and surrounding whitespace.
        line = raw.split(" #", 1)[0].strip() if " #" in raw else raw.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("-"):
            _check_option(line, i, includes, r)
            continue

        if _URL_REQUIREMENT_RE.match(line):
            _check_url_requirement(line, i, r)
            continue

        r.info["requirements"] += 1
        if not is_valid_pep508(line):
            r.add_error(f"invalid requirement: {line!r}", "REQ_INVALID", line=i)
        elif not _PINNED_RE.search(line) and ";" not in line:
            r.add_warning(f"unpinned dependency {line!r} (no == pin)", "REQ_UNPINNED", line=i)

    if includes:
        r.info["includes"] = includes
    return r


def _check_option(line: str, lineno: int, includes: list[str], r: ValidationResult) -> None:
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
            _check_index_url(url, opt, lineno, r)
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


def _check_index_url(url: str, opt: str, lineno: int, r: ValidationResult, *, scheme_check: bool = True) -> None:
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
