"""Pragmatic PEP 508 / PEP 440 helpers used by the pyproject and requirements
validators.

We deliberately avoid a dependency on ``packaging`` to preserve the project's
zero-runtime-dependency policy, so these are *pragmatic* regex checks rather
than a full grammar implementation. They err toward accepting ambiguous but
plausible specifiers to avoid false positives (mirroring checker-npm's
pragmatic ``isValidRange``).
"""

from __future__ import annotations

import re

# PEP 503 normalized distribution name: letters/digits separated (not led or
# trailed) by ``.``, ``-`` or ``_``.
NAME_RE = re.compile(r"^([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9])$")

# PEP 440 version (pragmatic subset): optional epoch, release segments, optional
# pre/post/dev releases, optional local version. PEP 440 permits ``.``, ``-`` or
# ``_`` as the separator before pre/post/dev segments, several spellings of each
# (``alpha``/``a``, ``post``/``rev``/``r``), and ``.``/``-``/``_`` inside the
# local version -- accepting all of them avoids false ``invalid version`` errors.
PEP440_RE = re.compile(
    r"^v?(\d+!)?\d+(\.\d+)*"  # epoch + release
    r"([-._]?(a|b|c|rc|alpha|beta|pre|preview)[-._]?\d*)?"  # pre-release
    r"([-._]?(post|rev|r)[-._]?\d*|-\d+)?"  # post-release (incl. implicit ``-N``)
    r"([-._]?dev[-._]?\d*)?"  # dev-release
    r"(\+[A-Za-z0-9]+([-._][A-Za-z0-9]+)*)?$",  # local version
    re.IGNORECASE,
)

# A single version-specifier clause, e.g. ``>=1.2``, ``==1.0.*``, ``~=2.3``.
_SPEC_CLAUSE_RE = re.compile(r"^(===|==|!=|~=|>=|<=|>|<)\s*[A-Za-z0-9][\w.*+!-]*$")

# Pinned to an exact version (``==`` or ``===``).
_PINNED_RE = re.compile(r"(===|==)")

# Leading name (with optional extras) of a PEP 508 requirement string. The name
# may not start or end with a separator (matching :data:`NAME_RE`).
_REQ_HEAD_RE = re.compile(
    r"^([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)"  # name (no leading/trailing sep)
    r"(\s*\[[A-Za-z0-9,\s._-]+\])?"  # optional extras
)


def is_valid_name(name: object) -> bool:
    """Return True if ``name`` is a valid PEP 503/508 distribution name."""
    return isinstance(name, str) and bool(NAME_RE.match(name))


def is_valid_version(version: object) -> bool:
    """Return True if ``version`` is a valid (pragmatic) PEP 440 version."""
    return isinstance(version, str) and bool(PEP440_RE.match(version.strip()))


def is_valid_requires_python(value: object) -> bool:
    """Validate a ``requires-python`` style specifier set (comma-separated)."""
    if not isinstance(value, str) or not value.strip():
        return False
    for clause in value.split(","):
        if not _SPEC_CLAUSE_RE.match(clause.strip()):
            return False
    return True


def is_pinned_spec(spec: str) -> bool:
    """Return True when a requirement spec pins an exact version.

    Detects an ``==`` / ``===`` clause on the marker-free portion (a ``==``
    inside an environment marker after ``;`` is not a pin). Direct-URL
    references (``name @ url``) identify one exact artifact and count as
    pinned. Shared by the requirements and pyproject validators so both speak
    the same ``pinned-versions`` rule.
    """
    if "@" in spec:
        return True
    marker_free = spec.split(";", 1)[0]
    return bool(_PINNED_RE.search(marker_free))


def is_valid_pep508(requirement: object) -> bool:
    """Validate a PEP 508 dependency specifier (name[extras][specifiers][; marker]).

    Pragmatic: validates the name head and any version specifiers, and accepts
    a trailing environment marker without parsing it in full.
    """
    if not isinstance(requirement, str):
        return False
    req = requirement.strip()
    if not req:
        return False

    # Direct URL reference: ``name @ url`` -- accept the name, trust the URL.
    if "@" in req:
        head = req.split("@", 1)[0].strip()
        hm = _REQ_HEAD_RE.match(head)
        return hm is not None and hm.group(0).strip() == head

    # Strip an environment marker (``; python_version >= '3.9'``); not parsed.
    if ";" in req:
        req = req.split(";", 1)[0].strip()

    m = _REQ_HEAD_RE.match(req)
    if not m:
        return False
    head_end = m.end()
    rest = req[head_end:].strip()
    # PEP 508 allows the version specifiers to be wrapped in parentheses,
    # e.g. ``requests (>=2.0)``; unwrap them before validating the clauses.
    if rest.startswith("(") and rest.endswith(")"):
        rest = rest[1:-1].strip()
    if not rest:
        return True  # bare name (with optional extras)

    # Remaining text must be a comma-separated set of version specifier clauses.
    for clause in rest.split(","):
        if not _SPEC_CLAUSE_RE.match(clause.strip()):
            return False
    return True
