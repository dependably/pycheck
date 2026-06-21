"""Validate a ``pip.conf`` / ``pip.ini`` config -- the analog of checker-npm's
``npmrc-validator.js`` and the security-critical validator of the three.

pip config is INI, parsed with stdlib :mod:`configparser`. Security findings
(plaintext credentials embedded in an index URL, ``trusted-host`` which
disables TLS verification) are ALWAYS errors regardless of any future
strict/relaxed flag -- exposed via :data:`SECURITY_CODES`, mirroring npm's
``NPMRC_SECURITY_CODES``.

We only ever inspect the *committed* project-level pip config, never a
machine's global ``~/.config/pip/pip.conf``, so results match between local and
CI.
"""

from __future__ import annotations

import configparser
import re
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from .result import ValidationResult

# Hosts that are always trusted without an allowlist entry -- the public PyPI
# index and its file-serving CDN.
PUBLIC_INDEX_HOSTS: frozenset = frozenset({"pypi.org", "files.pythonhosted.org"})

# A userinfo component that is *entirely* an env reference is safe; a partial
# one (``real:secret${X}``) must NOT exempt the line, or a plaintext secret
# slips by. Supports ${VAR}, $VAR and %(VAR)s style references.
ENV_REF_ONLY_RE = re.compile(r"^(\$\{[^}]+\}|%\([^)]+\)s|\$[A-Za-z_]\w*)$")

# Codes that fail a run no matter how severity is configured.
SECURITY_CODES: frozenset = frozenset({"PIP_PLAINTEXT_SECRET", "PIP_TRUSTED_HOST", "PIP_UNTRUSTED_INDEX"})

# Recognized pip config keys -- intentionally a generous subset; unknowns only
# warn.
KNOWN_KEYS = frozenset(
    {
        "index-url",
        "extra-index-url",
        "trusted-host",
        "no-index",
        "find-links",
        "cert",
        "client-cert",
        "timeout",
        "default-timeout",
        "retries",
        "proxy",
        "cache-dir",
        "no-cache-dir",
        "require-hashes",
        "no-deps",
        "pre",
        "user",
        "upgrade",
        "quiet",
        "verbose",
        "disable-pip-version-check",
        "progress-bar",
        "require-virtualenv",
        "prefer-binary",
        "only-binary",
        "no-binary",
        "use-feature",
        "src",
        "log",
        "no-warn-script-location",
        "no-build-isolation",
        "check-build-dependencies",
    }
)

_INDEX_KEYS = frozenset({"index-url", "extra-index-url"})


def validate_pip_conf(
    content: str, *, source: str = "pip.conf", allowed_hosts: Optional[Sequence[str]] = None
) -> ValidationResult:
    """Validate pip config INI content.

    ``allowed_hosts`` -- bare hostnames trusted in addition to the public
    defaults (:data:`PUBLIC_INDEX_HOSTS`); any index host outside that union is
    flagged ``PIP_UNTRUSTED_INDEX``. Defaults to empty.
    """
    trusted = _trusted_hosts(allowed_hosts)
    r = ValidationResult()
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        parser.read_string(content, source=source)
    except configparser.Error as e:
        r.add_error(f"malformed pip config: {e}", "PIP_SYNTAX", line=getattr(e, "lineno", None))
        return r

    line_index = _build_line_index(content)
    r.info["sections"] = parser.sections()
    for section in parser.sections():
        for key, value in parser.items(section):
            key_l = key.strip().lower()
            ln = line_index.get((section, key_l))
            _check_key(key_l, value, ln, r, trusted)
    return r


def _trusted_hosts(allowed_hosts: Optional[Sequence[str]]) -> frozenset:
    extra = {h.strip().lower() for h in (allowed_hosts or []) if h and h.strip()}
    return PUBLIC_INDEX_HOSTS | extra


def _check_key(key: str, value: str, line: Optional[int], r: ValidationResult, trusted: frozenset) -> None:
    if key in _INDEX_KEYS:
        # extra-index-url may carry several whitespace/newline separated URLs.
        for url in value.split():
            _check_index_url(url, key, line, r, trusted)
        return

    if key == "trusted-host":
        for host in value.split():
            r.add_error(f"trusted-host {host!r} disables TLS certificate verification", "PIP_TRUSTED_HOST", line)
        return

    if key in ("cert", "client-cert"):
        if not value.strip():
            r.add_error(f"{key} must be a non-empty path", "PIP_FIELD_TYPE", line)
        elif not Path(value.strip()).exists():
            r.add_warning(f"{key} path does not exist: {value.strip()!r}", "PIP_CERT_MISSING", line)
        return

    if key not in KNOWN_KEYS:
        r.add_warning(f"unrecognized pip config key {key!r}", "PIP_UNKNOWN_KEY", line)


def _check_index_url(url: str, key: str, line: Optional[int], r: ValidationResult, trusted: frozenset) -> None:
    try:
        parts = urlsplit(url)
    except ValueError:
        r.add_error(f"invalid {key} URL: {url!r}", "PIP_INVALID_INDEX", line)
        return

    # --- credentials embedded in the URL ---
    if parts.username or parts.password:
        userinfo_ok = _is_env_ref(parts.username) and (parts.password is None or _is_env_ref(parts.password))
        if not userinfo_ok:
            r.add_error(
                f"plaintext credential in {key} ({_redact(url)}) -- use an env var reference",
                "PIP_PLAINTEXT_SECRET",
                line,
            )

    scheme = parts.scheme.lower()
    if scheme == "http":
        r.add_warning(f"{key} over http:// ({url}) -- prefer https://", "PIP_INSECURE_INDEX", line)
    elif scheme not in ("https", "file"):
        r.add_error(f"unsupported {key} scheme {scheme!r} in {url!r}", "PIP_INVALID_INDEX_SCHEME", line)
    elif scheme in ("http", "https") and not parts.hostname:
        r.add_error(f"invalid {key} URL (no host): {url!r}", "PIP_INVALID_INDEX", line)

    # --- index host must be public or explicitly allowlisted ---
    if scheme in ("http", "https") and parts.hostname:
        host = parts.hostname.lower()
        if host not in trusted:
            r.add_error(
                f"{key} host {host!r} is not a public index and is not allowlisted "
                f"(add it to .dependably-check allowedRegistryHosts)",
                "PIP_UNTRUSTED_INDEX",
                line,
            )


def _is_env_ref(value: Optional[str]) -> bool:
    return value is not None and bool(ENV_REF_ONLY_RE.match(value))


def _redact(url: str) -> str:
    """Redact a userinfo component so secrets are never echoed in output."""
    return re.sub(r"://[^/@\s]+@", "://***@", url)


def _build_line_index(content: str) -> Dict[Tuple[str, str], int]:
    """Map ``(section, key)`` to a 1-based line number.

    configparser does not expose source line numbers, so scan the raw text
    tracking ``[section]`` headers and ``key = value`` / ``key : value`` starts.
    """
    index: Dict[Tuple[str, str], int] = {}
    section = ""
    for i, raw in enumerate(content.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped[0] in "#;":
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip()
            continue
        m = re.match(r"^\s*([^=:\s][^=:]*?)\s*[=:]", raw)
        if m:
            key = m.group(1).strip().lower()
            index.setdefault((section, key), i)
    return index
