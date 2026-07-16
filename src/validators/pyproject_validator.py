"""Validate a ``pyproject.toml`` manifest -- the analog of checker-npm's
``package-json-validator.js``.

Checks ``[project]`` (name, version, dependencies, optional-dependencies,
requires-python, license, common field types) and ``[build-system]``. Returns
the uniform :class:`ValidationResult` contract.

TOML parsing uses stdlib ``tomllib`` (Python 3.11+), falling back to ``tomli``
if installed, and otherwise degrades gracefully: the result is marked valid
with ``info["skipped"]=True`` so the tool stays runnable on 3.9/3.10 without a
new runtime dependency.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, Union

from ._pep508 import is_pinned_spec, is_valid_name, is_valid_pep508, is_valid_requires_python, is_valid_version
from .result import ValidationResult

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised only on <3.11
    try:
        import tomli as tomllib
    except ImportError:  # pragma: no cover - exercised only without tomli
        tomllib = None

# The manifest has no always-error security codes (no secrets live here), but we
# expose the frozenset for parity with the other validators.
SECURITY_CODES: frozenset = frozenset()

# Fields whose value must be a list (of strings, loosely).
_LIST_FIELDS = ("keywords", "classifiers", "authors", "maintainers", "dynamic")
# Fields whose value must be a table.
_TABLE_FIELDS = ("scripts", "gui-scripts", "entry-points", "urls")


def validate_pyproject(content: Union[str, bytes, Dict[str, Any]]) -> ValidationResult:
    """Validate pyproject.toml content (TOML text/bytes or a parsed dict)."""
    r = ValidationResult()

    if isinstance(content, dict):
        data: Dict[str, Any] = content
    else:
        if tomllib is None:
            r.info["skipped"] = True
            r.info["reason"] = "tomllib/tomli unavailable (Python < 3.11 without tomli)"
            return r
        text = content.decode() if isinstance(content, bytes) else content
        try:
            data = tomllib.loads(text)
        except Exception as e:  # tomllib.TOMLDecodeError + decode errors
            r.add_error(f"pyproject.toml is not valid TOML: {e}", "PP_PARSE")
            return r

    r.info["keys"] = sorted(data.keys())

    project = data.get("project")
    if project is None:
        # A build-system-only file is legitimate for some tooling; warn rather
        # than error (mirrors npm's relaxed handling of unusual manifests).
        r.add_warning("no [project] table found", "PP_NOT_TABLE")
    elif not isinstance(project, dict):
        r.add_error("[project] is not a table", "PP_NOT_TABLE")
    else:
        _validate_project_table(project, r)

    _validate_build_system(data.get("build-system"), r)
    return r


def _validate_project_table(project: Dict[str, Any], r: ValidationResult) -> None:
    dynamic = project.get("dynamic", [])
    if not isinstance(dynamic, list):
        r.add_error("[project].dynamic must be a list", "PP_FIELD_TYPE")
        dynamic = []

    _validate_name_version(project, dynamic, r)
    _validate_dependencies(project, r)
    _validate_metadata(project, r)


def _validate_name_version(project: Dict[str, Any], dynamic: list, r: ValidationResult) -> None:
    name = project.get("name")
    # PEP 621: name is mandatory and MUST NOT be declared dynamic.
    if "name" in dynamic:
        r.add_error("[project].name must not be declared dynamic (PEP 621)", "PP_DYNAMIC_NAME")
    if name is None:
        r.add_error("missing [project].name", "PP_MISSING_NAME")
    elif not is_valid_name(name):
        r.add_error(f"invalid [project].name: {name!r}", "PP_INVALID_NAME")

    version = project.get("version")
    if version is None:
        if "version" not in dynamic:
            r.add_error("missing [project].version (and not declared dynamic)", "PP_MISSING_VERSION")
    elif not is_valid_version(version):
        r.add_error(f"version is not PEP 440: {version!r}", "PP_INVALID_VERSION")


def _validate_dependencies(project: Dict[str, Any], r: ValidationResult) -> None:
    deps = project.get("dependencies")
    if deps is not None:
        if not isinstance(deps, list):
            r.add_error("[project].dependencies must be a list", "PP_FIELD_TYPE")
        else:
            _validate_dep_list(deps, "dependencies", r)

    opt = project.get("optional-dependencies")
    if opt is not None:
        _validate_optional_dependencies(opt, r)

    rp = project.get("requires-python")
    if rp is not None and not is_valid_requires_python(rp):
        r.add_error(f"requires-python is not a valid specifier: {rp!r}", "PP_INVALID_REQUIRES_PYTHON")


def _validate_optional_dependencies(opt: Any, r: ValidationResult) -> None:
    if not isinstance(opt, dict):
        r.add_error("[project.optional-dependencies] must be a table", "PP_OPTDEPS_NOT_TABLE")
        return
    for group, group_deps in opt.items():
        if not isinstance(group_deps, list):
            r.add_error(f"optional-dependencies.{group} must be a list", "PP_OPTDEPS_NOT_TABLE")
            continue
        _validate_dep_list(group_deps, f"optional-dependencies.{group}", r)


def _validate_metadata(project: Dict[str, Any], r: ValidationResult) -> None:
    # --- license (warn when absent; accept str or PEP 621 table) ---
    lic = project.get("license")
    if lic is None:
        r.add_warning("no [project].license field", "PP_MISSING_LICENSE")
    elif not isinstance(lic, (str, dict)):
        r.add_error("[project].license must be a string or table", "PP_FIELD_TYPE")

    # --- readme: str or table ---
    readme = project.get("readme")
    if readme is not None and not isinstance(readme, (str, dict)):
        r.add_error("[project].readme must be a string or table", "PP_FIELD_TYPE")

    # --- list-typed fields ---
    for fld in _LIST_FIELDS:
        val = project.get(fld)
        if val is not None and not isinstance(val, list):
            r.add_error(f"[project].{fld} must be a list", "PP_FIELD_TYPE")

    # --- table-typed fields ---
    for fld in _TABLE_FIELDS:
        val = project.get(fld)
        if val is not None and not isinstance(val, dict):
            r.add_error(f"[project].{fld} must be a table", "PP_FIELD_TYPE")


def _validate_dep_list(deps: list, section: str, r: ValidationResult) -> None:
    """Validate ``[project]`` dependency entries (PEP 508 + exact pinning).

    Unpinned ranges are errors by default (cross-tool ``pinned-versions``
    rule). Only the install surface is pin-checked -- ``[build-system].requires``
    goes through :func:`_validate_build_requires` and stays loose by design.
    """
    for entry in deps:
        if not isinstance(entry, str):
            r.add_error(f"{section} entry is not a string: {entry!r}", "PP_DEP_NOT_STRING")
        elif not is_valid_pep508(entry):
            r.add_error(f"invalid PEP 508 specifier in {section}: {entry!r}", "PP_INVALID_DEP")
        elif not is_pinned_spec(entry):
            r.add_error(
                f"unpinned dependency in {section}: {entry!r} (no == pin) -- pin the version, "
                'or set pycheck.rules["pinned-versions"] to "warn"/"off" in .dependably',
                "PP_UNPINNED",
            )


def _validate_build_system(build_system: Any, r: ValidationResult) -> None:
    if build_system is None:
        return
    if not isinstance(build_system, dict):
        r.add_error("[build-system] is not a table", "PP_BUILD_SYSTEM_TYPE")
        return
    requires = build_system.get("requires")
    if requires is not None:
        _validate_build_requires(requires, r)
    backend = build_system.get("build-backend")
    if backend is not None and not isinstance(backend, str):
        r.add_error("[build-system].build-backend must be a string", "PP_BUILD_SYSTEM_TYPE")


def _validate_build_requires(requires: Any, r: ValidationResult) -> None:
    if not isinstance(requires, list) or not all(isinstance(x, str) for x in requires):
        r.add_error("[build-system].requires must be a list of strings", "PP_BUILD_SYSTEM_TYPE")
        return
    for entry in requires:
        if not is_valid_pep508(entry):
            r.add_error(
                f"invalid PEP 508 specifier in [build-system].requires: {entry!r}",
                "PP_INVALID_DEP",
            )
