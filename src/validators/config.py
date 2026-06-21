"""Load the shared ``.dependably-check`` repo-root config.

The Dependably toolchain (npm/PyPI/NuGet checkers) reads a single committed
``.dependably-check`` JSON file so an organisation declares its trusted private
registries once. This module returns the data relevant to *this* tool -- the
union of ``common.allowedRegistryHosts`` and ``python.allowedRegistryHosts``
(bare hostnames). Other sections and unknown keys are ignored.

Discovery walks UP from the validate target directory (or cwd) to the
filesystem root, stopping at the first ``.dependably-check`` found or at a
directory that contains a ``.git`` marker (the repo root). An explicit
``--config`` path skips discovery entirely.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Set

# Import the project's base exception. Flat layout (tests put ``src/`` on
# sys.path) exposes it as ``checker``; the installed wheel as ``src.checker``.
try:  # pragma: no cover - import shim
    from checker import ImportCheckerError
except ImportError:  # pragma: no cover - import shim
    from ..checker import ImportCheckerError

CONFIG_FILENAME = ".dependably-check"


def resolve_allowed_hosts(target: Optional[Path] = None, config_path: Optional[Path] = None) -> List[str]:
    """Return the union of trusted registry hosts for the Python tool.

    ``config_path`` -- an explicit ``--config`` path; read directly (no
    discovery). ``target`` -- the validate target, whose directory seeds the
    walk-up discovery when no explicit path is given. Returns an empty list when
    no config file is found.
    """
    path = _locate_config(target, config_path)
    if path is None:
        return []
    return _parse_allowed_hosts(path)


def _locate_config(target: Optional[Path], config_path: Optional[Path]) -> Optional[Path]:
    if config_path is not None:
        path = Path(config_path)
        if not path.is_file():
            raise ImportCheckerError(f"config file not found: {path}")
        return path
    return _discover_config(target)


def _discover_config(target: Optional[Path]) -> Optional[Path]:
    """Walk up from ``target``'s directory to the filesystem root.

    Stops at the first ``.dependably-check`` found. A directory holding a
    ``.git`` marker is treated as the repo root: its config is honoured but the
    walk does not continue past it.
    """
    start = Path(target) if target is not None else Path.cwd()
    start = start.resolve()
    directory = start if start.is_dir() else start.parent

    for current in [directory, *directory.parents]:
        candidate = current / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        if (current / ".git").exists():
            break
    return None


def _parse_allowed_hosts(path: Path) -> List[str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ImportCheckerError(f"could not read config file {path}: {e}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ImportCheckerError(f"malformed config file {path}: {e}")

    if not isinstance(data, dict):
        raise ImportCheckerError(f"malformed config file {path}: top-level value must be a JSON object")

    hosts: List[str] = []
    seen: Set[str] = set()
    for section in ("common", "python"):
        hosts.extend(_section_hosts(data.get(section), path, section, seen))
    return hosts


def _section_hosts(section: object, path: Path, name: str, seen: Set[str]) -> List[str]:
    if section is None:
        return []
    if not isinstance(section, dict):
        raise ImportCheckerError(f"malformed config file {path}: '{name}' must be a JSON object")

    raw_hosts = section.get("allowedRegistryHosts")
    if raw_hosts is None:
        return []
    if not isinstance(raw_hosts, list):
        raise ImportCheckerError(f"malformed config file {path}: '{name}.allowedRegistryHosts' must be a JSON array")

    out: List[str] = []
    for host in raw_hosts:
        if not isinstance(host, str):
            raise ImportCheckerError(
                f"malformed config file {path}: '{name}.allowedRegistryHosts' entries must be strings"
            )
        normalized = host.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out
