"""Validate a ``requirements.txt`` -- pip's dependency-consumption surface.

Line-oriented with accurate 1-based line numbers. Validates ordinary
requirements as PEP 508, flags unpinned dependencies as errors by default
(the cross-tool ``pinned-versions`` rule -- relax via ``.dependably``), and --
mirroring the pip.conf validator -- treats credentials embedded in an index URL
and ``--trusted-host`` as ALWAYS errors (see :data:`SECURITY_CODES`).
"""

from __future__ import annotations

import re
from typing import Any, Iterator, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from ._pep508 import is_pinned_spec, is_valid_pep508
from .pip_conf_validator import PUBLIC_INDEX_HOSTS, _is_env_ref, _redact
from .result import ValidationResult

SECURITY_CODES: frozenset = frozenset({"REQ_PLAINTEXT_SECRET", "REQ_TRUSTED_HOST", "REQ_UNTRUSTED_INDEX"})

# Lines that are URLs / VCS / editable installs rather than name specifiers.
_URL_REQUIREMENT_RE = re.compile(r"^\s*(-e\s|--editable\s|git\+|hg\+|svn\+|bzr\+|https?://|file:)")
# An option line, e.g. ``--index-url https://...`` or ``-i https://...``.
_OPTION_RE = re.compile(r"^\s*(--?[A-Za-z][\w-]*)(?:[=\s]+(.*))?$")
# An inline comment: whitespace + ``#`` (a URL ``#egg=`` fragment has no
# preceding whitespace and is preserved).
_INLINE_COMMENT_RE = re.compile(r"\s#.*$")

_INDEX_OPTS = frozenset({"-i", "--index-url", "--extra-index-url"})
_INCLUDE_OPTS = frozenset({"-r", "--requirement", "-c", "--constraint"})


def _strip_inline_comment(raw: str) -> str:
    """Drop a pip inline comment (whitespace + ``#``), keeping URL fragments."""
    return _INLINE_COMMENT_RE.sub("", raw)


def _logical_lines(content: str) -> Iterator[Tuple[int, str]]:
    """Yield ``(lineno, text)`` joining backslash-continued physical lines.

    ``lineno`` is the 1-based number of the logical line's FIRST physical line,
    so findings keep pointing at where the requirement starts. Inline comments
    are stripped per physical line before continuations are joined.
    """
    buf = ""
    start: Optional[int] = None
    for i, raw in enumerate(content.splitlines(), start=1):
        text = _strip_inline_comment(raw)
        if start is None:
            start = i
        if text.rstrip().endswith("\\"):
            buf += text.rstrip()[:-1] + " "
            continue
        buf += text
        yield start, buf
        buf, start = "", None
    if start is not None:  # dangling backslash at EOF
        yield start, buf


def _requirement_spec(line: str) -> str:
    """Return the requirement portion, dropping trailing pip options.

    A requirement line may carry per-requirement options (``--hash``,
    ``--config-settings``, ``--global-option`` ...) that are not part of the
    PEP 508 spec. Everything from the first ``-``-prefixed token on is dropped.
    """
    kept: list[str] = []
    for token in line.split():
        if token.startswith("-"):
            break
        kept.append(token)
    return " ".join(kept)


def extract_includes(content: str) -> list[str]:
    """Return the ``-r``/``-c`` include targets referenced in ``content``.

    Used by the runner to follow ``-r base.txt`` / ``-c constraints.txt`` to
    files that name-glob discovery would miss, so their dependency surface
    (credentials, trusted-host, untrusted indexes) is not left unvalidated.
    """
    includes: list[str] = []
    for _lineno, raw in _logical_lines(content):
        line = raw.strip()
        if not line.startswith("-"):
            continue
        m = _OPTION_RE.match(line)
        if m and m.group(1) in _INCLUDE_OPTS:
            value = (m.group(2) or "").strip()
            if value:
                includes.append(value)
    return includes


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

    for lineno, raw in _logical_lines(content):
        line = raw.strip()
        if line and not line.startswith("#"):
            _check_requirement_line(line, lineno, includes, r, trusted)

    if includes:
        r.info["includes"] = includes
    return r


def _check_requirement_line(
    line: str, lineno: int, includes: list[str], r: ValidationResult, trusted: frozenset
) -> None:
    """Classify and validate a single non-blank, non-comment requirements line."""
    # URL / VCS / editable installs first, so `-e`/`--editable` lines are
    # credential-scanned rather than swallowed by the generic option branch.
    if _URL_REQUIREMENT_RE.match(line):
        _check_url_requirement(line, lineno, r)
        return

    if line.startswith("-"):
        _check_option(line, lineno, includes, r, trusted)
        return

    r.info["requirements"] += 1
    # Validate the requirement spec only -- drop trailing per-requirement
    # options (`--hash` etc.), which are not part of the PEP 508 grammar.
    spec = _requirement_spec(line)
    if not is_valid_pep508(spec):
        r.add_error(f"invalid requirement: {line!r}", "REQ_INVALID", line=lineno)
        return
    # Unpinned ranges are errors by default (cross-tool `pinned-versions` rule;
    # a `==` inside an environment marker after `;` is not a pin).
    if not is_pinned_spec(spec):
        r.add_error(
            f"unpinned dependency {line!r} (no == pin) -- pin the version, or set "
            'pycheck.rules["pinned-versions"] to "warn"/"off" in .dependably',
            "REQ_UNPINNED",
            line=lineno,
        )


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


def _check_url_credentials(parts: Any, url: str, opt: str, lineno: int, r: ValidationResult) -> None:
    """Flag a plaintext credential embedded in a URL's userinfo component."""
    if not (parts.username or parts.password):
        return
    scheme = parts.scheme.lower()
    ssh_like = scheme == "ssh" or scheme.endswith("+ssh")
    if ssh_like and parts.username and parts.password is None:
        # `git@host` in an SSH VCS URL is the standard, secret-free convention --
        # a username with no password, not a credential.
        return
    userinfo_ok = _is_env_ref(parts.username) and (parts.password is None or _is_env_ref(parts.password))
    if not userinfo_ok:
        r.add_error(
            f"plaintext credential in {opt} ({_redact(url)}) -- use an env var reference",
            "REQ_PLAINTEXT_SECRET",
            line=lineno,
        )


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
    _check_url_credentials(parts, url, opt, lineno, r)
    if scheme_check and parts.scheme.lower() == "http":
        r.add_warning(f"{opt} over http:// ({url}) -- prefer https://", "REQ_INSECURE_INDEX", line=lineno)

    # Index-trust applies only to actual index options, not editable/url
    # requirements (scheme_check=False marks those).
    if scheme_check and trusted is not None and parts.scheme.lower() in ("http", "https") and parts.hostname:
        host = parts.hostname.lower()
        if host not in trusted:
            r.add_error(
                f"{opt} host {host!r} is not a public index and is not allowlisted "
                f"(add it to .dependably allowedRegistryHosts)",
                "REQ_UNTRUSTED_INDEX",
                line=lineno,
            )
