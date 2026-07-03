#!/usr/bin/env python3
"""
Python Import Checker CLI Tool

A command-line tool to analyze and clean up unused imports in Python files.
Supports both read-only analysis and automatic cleanup of unused imports.
"""

import argparse
import ast
import io
import json
import shutil
import sys
import tokenize
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

__version__ = "1.2.0"

# Process exit codes, aligned with the Dependably suite convention:
#   0 clean · 1 findings (block) · 2 usage error / operational-internal error.
EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


class ImportCheckerError(Exception):
    """Custom exception for import checker errors."""

    pass


# Identity reported in the shared Dependably finding JSON envelope (schema v1).
TOOL_NAME = "Dependably.pycheck"
SCHEMA_VERSION = "1.0"

# python-check's internal severities map onto the single shared ladder
# (critical > high > moderate > low > info). error->high, warning->low.
_SEVERITY_LADDER: Dict[str, str] = {"error": "high", "warning": "low"}

# Numeric rank for the shared severity ladder (higher == more severe). Used by
# the unified ``--fail-on`` gate to compare a finding's severity to a threshold.
_SEVERITY_RANK: Dict[str, int] = {"info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}


def parse_fail_on(rules: List[str]) -> List[Tuple[str, str]]:
    """Validate the suite-canonical ``--fail-on KEY=VALUE`` rules.

    Two keys are accepted across the Dependably suite:
      * ``severity=<critical|high|moderate|low|info>`` -- trip if any finding is
        at or above that level on the shared ladder.
      * ``count=<N>`` -- trip if the total number of findings exceeds ``N``.

    Returns the parsed ``(key, value)`` pairs. Raises ``ValueError`` (with a
    usage-style message) on any malformed rule so the caller can surface it as
    an argparse error (exit 2).
    """
    parsed: List[Tuple[str, str]] = []
    for rule in rules:
        if "=" not in rule:
            raise ValueError(f"invalid --fail-on value '{rule}': expected KEY=VALUE")
        key, _, value = rule.partition("=")
        key = key.strip().lower()
        value = value.strip().lower()
        _validate_fail_on_rule(key, value)
        parsed.append((key, value))
    return parsed


def _validate_fail_on_rule(key: str, value: str) -> None:
    """Validate a single parsed ``--fail-on`` ``key``/``value`` pair.

    Raises ``ValueError`` (with a usage-style message) when the key is unknown or
    the value is invalid for its key. See :func:`parse_fail_on` for the rules.
    """
    if key == "severity":
        if value not in _SEVERITY_RANK:
            raise ValueError(
                f"invalid --fail-on severity '{value}': " "choose from critical, high, moderate, low, info"
            )
    elif key == "count":
        try:
            n = int(value)
        except ValueError:
            n = -1
        if n < 0:
            raise ValueError(f"invalid --fail-on count '{value}': expected a non-negative integer")
    else:
        raise ValueError(f"invalid --fail-on key '{key}': expected 'severity' or 'count'")


def gate_trips(raw_findings: List[Dict[str, Any]], rules: List[Tuple[str, str]]) -> bool:
    """Return True if any ``--fail-on`` rule trips against the raw findings.

    ``raw_findings`` carry the internal ``severity`` (``error``|``warning``);
    they are mapped onto the shared ladder before comparison so the gate speaks
    the same vocabulary as every other Dependably tool.
    """
    if not rules:
        return False
    ranks = [_SEVERITY_RANK[_SEVERITY_LADDER.get(str(f.get("severity")), "info")] for f in raw_findings]
    for key, value in rules:
        if key == "severity":
            if any(rank >= _SEVERITY_RANK[value] for rank in ranks):
                return True
        elif key == "count" and len(raw_findings) > int(value):
            return True
    return False


# Short, optional remediation hints keyed by ruleId. Anything absent -> null.
_REMEDIATION: Dict[str, str] = {
    "unused-import": "Remove the unused import.",
}


def _to_finding(raw: Dict[str, Any], category: str) -> Dict[str, Any]:
    """Map an internal finding dict to the shared schema-v1 ``Finding`` shape.

    Internal findings carry ``code`` / ``file`` / ``line`` / ``message`` /
    ``severity`` (``error``|``warning``); the shared shape uses ``ruleId``,
    ``category``, a ``location`` object, a ladder ``severity`` string and an
    optional ``remediation``.
    """
    rule_id = raw.get("code")
    return {
        "severity": _SEVERITY_LADDER.get(str(raw.get("severity")), "info"),
        "ruleId": rule_id,
        "category": category,
        "message": raw.get("message", ""),
        "location": {
            "file": raw.get("file"),
            "line": raw.get("line"),
            "column": None,
        },
        "remediation": _REMEDIATION.get(str(rule_id)),
    }


def build_json_report(
    target: Any,
    scanned: int,
    raw_findings: List[Dict[str, Any]],
    category: str,
    exit_code: int,
) -> Dict[str, Any]:
    """Assemble the shared Dependably finding JSON envelope (schema v1).

    Every Dependably tool emits this exact envelope so a single consumer parses
    all of them the same way: ``tool`` / ``toolVersion`` / ``schemaVersion`` /
    ``target`` / ``summary`` / ``findings``. ``raw_findings`` (internal shape)
    are mapped to the shared ``Finding`` shape under ``category`` (``lint`` for
    import findings, ``config`` for config-validation findings).

    ``summary.scanned`` is the number of files/artifacts examined,
    ``summary.findings`` always equals ``len(findings)`` (never truncated), and
    ``summary.exitCode`` equals the real process exit code.
    """
    findings = [_to_finding(raw, category) for raw in raw_findings]
    by_severity = {"critical": 0, "high": 0, "moderate": 0, "low": 0, "info": 0}
    for finding in findings:
        by_severity[finding["severity"]] += 1
    return {
        "tool": TOOL_NAME,
        "toolVersion": __version__,
        "schemaVersion": SCHEMA_VERSION,
        "target": str(target),
        "summary": {
            "scanned": scanned,
            "findings": len(findings),
            "bySeverity": by_severity,
            "exitCode": exit_code,
        },
        "findings": findings,
    }


def emit_json(report: Dict[str, Any]) -> None:
    """Write a single JSON document to stdout (kept clean: no text mixed in)."""
    json.dump(report, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")


class ImportInfo:
    """Class to store information about an import statement."""

    def __init__(
        self,
        module: str,
        names: List[str],
        alias: Optional[str] = None,
        line_number: int = 0,
        is_from_import: bool = False,
    ):
        self.module = module  # The module being imported
        self.names = names  # List of names being imported (empty for 'import module')
        self.alias = alias  # Alias if used (as clause)
        self.line_number = line_number
        self.is_from_import = is_from_import  # True for 'from X import Y'
        self.used = False  # Track if this import is used
        # Every name/alias sharing this physical line (for partial rewrites).
        self.all_names_on_line: List[str] = []
        self.all_aliases_on_line: List[Optional[str]] = []
        # True when another statement shares this line (e.g. `import os; f()`);
        # such imports are never auto-removed to avoid deleting the neighbour.
        self.shares_line = False
        # True when this import is the only statement in its (non-module) block;
        # removing it would leave an empty block that no longer parses.
        self.sole_in_block = False

    @property
    def safe_to_remove(self) -> bool:
        """False when auto-removal would corrupt surrounding code."""
        return not self.shares_line and not self.sole_in_block

    def __repr__(self) -> str:
        return f"ImportInfo(module='{self.module}', names={self.names}, alias='{self.alias}', line={self.line_number})"


class _NameReferenceVisitor(ast.NodeVisitor):
    """Collect names referenced (loaded) in a module, plus `__all__` exports.

    Names listed in `__all__` are re-exported public API, so an import of such a
    name counts as "used" even when it is not otherwise referenced.
    """

    def __init__(self, references: Set[str]) -> None:
        self._references = references

    def visit_Name(self, node: ast.Name) -> None:
        # Only count names that are being loaded (not stored).
        if isinstance(node.ctx, ast.Load):
            self._references.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Handle attribute access like 'module.function'.
        if isinstance(node.value, ast.Name) and isinstance(node.value.ctx, ast.Load):
            self._references.add(node.value.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        # `x: "Decimal"` — the annotation may be a string forward reference.
        self._collect_string_annotations(node.annotation)
        # `__all__: list = [...]` — an annotated assignment re-exports too.
        if isinstance(node.target, ast.Name) and node.target.id == "__all__" and node.value is not None:
            self._collect_all_exports(node.value)
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        # `def f(x: "Decimal")` — argument annotations may be forward references.
        if node.annotation is not None:
            self._collect_string_annotations(node.annotation)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # `def f(...) -> "Decimal"` — return annotations may be forward references.
        if node.returns is not None:
            self._collect_string_annotations(node.returns)
        self.generic_visit(node)

    # Async defs carry the same annotation surface.
    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Call(self, node: ast.Call) -> None:
        # `cast("Decimal", x)` / `typing.cast(...)` — first arg is a forward ref.
        func = node.func
        is_cast = (isinstance(func, ast.Name) and func.id == "cast") or (
            isinstance(func, ast.Attribute) and func.attr == "cast"
        )
        if is_cast and node.args:
            self._collect_string_annotations(node.args[0])
        self.generic_visit(node)

    def _collect_string_annotations(self, annotation: ast.expr) -> None:
        """Register names used inside string (forward-reference) annotations.

        A forward reference such as ``x: "Decimal"`` or ``Optional["Decimal"]``
        stores the referenced name as a string constant, so it is never seen as
        a normal load. Without this, imports used only in string annotations
        (commonly ``TYPE_CHECKING`` imports) are reported unused — and cleanup
        would delete them, sometimes leaving an empty ``if TYPE_CHECKING:`` block
        that no longer parses.
        """
        for sub in ast.walk(annotation):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                self._collect_forward_ref(sub.value)

    def _collect_forward_ref(self, text: str) -> None:
        try:
            expr = ast.parse(text.strip(), mode="eval")
        except (SyntaxError, ValueError):
            return
        for sub in ast.walk(expr):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                self._references.add(sub.id)
            elif isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
                self._references.add(sub.value.id)

    def visit_Import(self, node: ast.Import) -> None:
        # Skip import statements themselves.
        pass

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # Skip import statements themselves.
        pass

    def visit_Assign(self, node: ast.Assign) -> None:
        if any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            self._collect_all_exports(node.value)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        # Handle `__all__ += [...]`.
        if isinstance(node.target, ast.Name) and node.target.id == "__all__":
            self._collect_all_exports(node.value)
        self.generic_visit(node)

    def _collect_all_exports(self, value: ast.expr) -> None:
        if isinstance(value, (ast.List, ast.Tuple)):
            for elt in value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    self._references.add(elt.value)


class _Scope:
    """One lexical scope in the scope tree built by :func:`scoped_import_usage`."""

    __slots__ = ("kind", "parent", "bound", "globals", "nonlocals", "loads", "import_lines")

    def __init__(self, kind: str, parent: Optional["_Scope"]) -> None:
        self.kind = kind  # "module" | "function" | "class" | "comprehension"
        self.parent = parent
        self.bound: Set[str] = set()  # names bound in this scope
        self.globals: Set[str] = set()
        self.nonlocals: Set[str] = set()
        self.loads: List[str] = []  # names loaded (read) in this scope
        # name -> line numbers of import statements binding it in this scope
        self.import_lines: Dict[str, Set[int]] = {}


def _resolve_scope(scope: _Scope, name: str) -> Optional[_Scope]:
    """Resolve a load of ``name`` in ``scope`` to the scope that binds it (LEGB).

    Applies Python's rules: ``global`` jumps to module scope, ``nonlocal`` to the
    nearest enclosing function binding, and ordinary lookup skips class scopes
    for anything other than the scope the load occurs in.
    """
    if name in scope.globals:
        module = scope
        while module.parent is not None:
            module = module.parent
        return module if name in module.bound else None
    if name in scope.nonlocals:
        outer = scope.parent
        while outer is not None:
            if outer.kind == "function" and name in outer.bound:
                return outer
            outer = outer.parent
        return None
    if name in scope.bound:
        return scope
    outer = scope.parent
    while outer is not None:
        if outer.kind != "class" and name in outer.bound:
            return outer
        outer = outer.parent
    return None


class _ScopeModelBuilder:
    """Walk an AST building the scope tree used to resolve import usage.

    Deliberately conservative: constructs evaluated in the *enclosing* scope
    (decorators, default argument values, annotations, class bases, the outermost
    comprehension iterable) are attributed there, not to the nested scope, so a
    name shadowed inside the nested scope is never mistaken for the import's use
    (and vice-versa). Anything not explicitly modelled is treated as a plain load
    in the current scope, which can only keep an import *used*.
    """

    def __init__(self) -> None:
        self.module = _Scope("module", None)
        self.scopes: List[_Scope] = [self.module]
        # Names that must always count as used: __all__ exports, string
        # forward references, and any global/nonlocal-declared name.
        self.protected: Set[str] = set()

    def build(self, tree: ast.AST) -> None:
        for stmt in getattr(tree, "body", []):
            self._walk(stmt, self.module)

    def _new_scope(self, kind: str, parent: _Scope) -> _Scope:
        scope = _Scope(kind, parent)
        self.scopes.append(scope)
        return scope

    def _bind(self, scope: _Scope, name: str) -> None:
        scope.bound.add(name)

    def _bind_target(self, node: ast.AST, scope: _Scope) -> None:
        """Record assignment targets as bindings (loading any attribute bases)."""
        if isinstance(node, ast.Name):
            self._bind(scope, node.id)
        elif isinstance(node, (ast.Tuple, ast.List)):
            for elt in node.elts:
                self._bind_target(elt, scope)
        elif isinstance(node, ast.Starred):
            self._bind_target(node.value, scope)
        elif isinstance(node, (ast.Attribute, ast.Subscript)):
            self._walk(node, scope)  # `a.b = x` / `a[b] = x` reads `a`

    def _annotation(self, node: Optional[ast.expr], scope: _Scope) -> None:
        """Process an annotation: real names load in ``scope``; string forward
        references contribute protected names."""
        if node is None:
            return
        self._walk(node, scope)
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                self.protected.update(_forward_ref_names(sub.value))

    def _walk(self, node: ast.AST, scope: _Scope) -> None:
        handler = getattr(self, f"_walk_{type(node).__name__}", None)
        if handler is not None:
            handler(node, scope)
        else:
            for child in ast.iter_child_nodes(node):
                self._walk(child, scope)

    # --- leaf references -----------------------------------------------------

    def _walk_Name(self, node: ast.Name, scope: _Scope) -> None:
        if isinstance(node.ctx, ast.Load):
            scope.loads.append(node.id)
        elif isinstance(node.ctx, (ast.Store, ast.Del)):
            self._bind(scope, node.id)

    def _walk_Attribute(self, node: ast.Attribute, scope: _Scope) -> None:
        self._walk(node.value, scope)

    # --- imports -------------------------------------------------------------

    def _walk_Import(self, node: ast.Import, scope: _Scope) -> None:
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            self._bind(scope, name)
            scope.import_lines.setdefault(name, set()).add(node.lineno)

    def _walk_ImportFrom(self, node: ast.ImportFrom, scope: _Scope) -> None:
        if node.module == "__future__":
            return
        for alias in node.names:
            if alias.name == "*":
                continue
            name = alias.asname or alias.name
            self._bind(scope, name)
            scope.import_lines.setdefault(name, set()).add(node.lineno)

    # --- assignments / augmented / annotated ---------------------------------

    def _walk_Assign(self, node: ast.Assign, scope: _Scope) -> None:
        self._walk(node.value, scope)
        for target in node.targets:
            self._bind_target(target, scope)
        self._maybe_all_exports(node.targets, node.value)

    def _walk_AugAssign(self, node: ast.AugAssign, scope: _Scope) -> None:
        if isinstance(node.target, ast.Name):
            scope.loads.append(node.target.id)  # augmented assignment reads first
            self._bind(scope, node.target.id)
        else:
            self._walk(node.target, scope)
        self._walk(node.value, scope)
        self._maybe_all_exports([node.target], node.value)

    def _walk_AnnAssign(self, node: ast.AnnAssign, scope: _Scope) -> None:
        self._annotation(node.annotation, scope)
        if node.value is not None:
            self._walk(node.value, scope)
        self._bind_target(node.target, scope)
        if node.value is not None:
            self._maybe_all_exports([node.target], node.value)

    def _maybe_all_exports(self, targets: List[ast.expr], value: ast.expr) -> None:
        if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            if isinstance(value, (ast.List, ast.Tuple)):
                for elt in value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        self.protected.add(elt.value)

    # --- comprehensions / loops / with / try ---------------------------------

    def _walk_comprehension_expr(self, node: ast.AST, scope: _Scope, elements: List[ast.expr]) -> None:
        generators = getattr(node, "generators", [])
        comp = self._new_scope("comprehension", scope)
        for i, gen in enumerate(generators):
            # The outermost iterable is evaluated in the enclosing scope.
            self._walk(gen.iter, scope if i == 0 else comp)
            self._bind_target(gen.target, comp)
            for cond in gen.ifs:
                self._walk(cond, comp)
        for element in elements:
            self._walk(element, comp)

    def _walk_ListComp(self, node: ast.ListComp, scope: _Scope) -> None:
        self._walk_comprehension_expr(node, scope, [node.elt])

    def _walk_SetComp(self, node: ast.SetComp, scope: _Scope) -> None:
        self._walk_comprehension_expr(node, scope, [node.elt])

    def _walk_GeneratorExp(self, node: ast.GeneratorExp, scope: _Scope) -> None:
        self._walk_comprehension_expr(node, scope, [node.elt])

    def _walk_DictComp(self, node: ast.DictComp, scope: _Scope) -> None:
        self._walk_comprehension_expr(node, scope, [node.key, node.value])

    def _walk_For(self, node: ast.AST, scope: _Scope) -> None:
        self._walk(node.iter, scope)  # type: ignore[attr-defined]
        self._bind_target(node.target, scope)  # type: ignore[attr-defined]
        for child in node.body + node.orelse:  # type: ignore[attr-defined]
            self._walk(child, scope)

    _walk_AsyncFor = _walk_For

    def _walk_With(self, node: ast.AST, scope: _Scope) -> None:
        for item in node.items:  # type: ignore[attr-defined]
            self._walk(item.context_expr, scope)
            if item.optional_vars is not None:
                self._bind_target(item.optional_vars, scope)
        for child in node.body:  # type: ignore[attr-defined]
            self._walk(child, scope)

    _walk_AsyncWith = _walk_With

    def _walk_ExceptHandler(self, node: ast.ExceptHandler, scope: _Scope) -> None:
        if node.type is not None:
            self._walk(node.type, scope)
        if node.name:
            self._bind(scope, node.name)
        for child in node.body:
            self._walk(child, scope)

    def _walk_Global(self, node: ast.Global, scope: _Scope) -> None:
        scope.globals.update(node.names)
        self.protected.update(node.names)

    def _walk_Nonlocal(self, node: ast.Nonlocal, scope: _Scope) -> None:
        scope.nonlocals.update(node.names)
        self.protected.update(node.names)

    def _walk_NamedExpr(self, node: ast.AST, scope: _Scope) -> None:
        self._walk(node.value, scope)  # type: ignore[attr-defined]
        self._bind_target(node.target, scope)  # type: ignore[attr-defined]

    # --- functions / classes (new scopes) ------------------------------------

    def _walk_function(self, node: ast.AST, scope: _Scope) -> None:
        args = node.args  # type: ignore[attr-defined]
        for decorator in node.decorator_list:  # type: ignore[attr-defined]
            self._walk(decorator, scope)
        for default in list(args.defaults) + [d for d in args.kw_defaults if d is not None]:
            self._walk(default, scope)
        all_args = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
        if args.vararg:
            all_args.append(args.vararg)
        if args.kwarg:
            all_args.append(args.kwarg)
        for arg in all_args:
            self._annotation(arg.annotation, scope)
        self._annotation(getattr(node, "returns", None), scope)
        self._bind(scope, node.name)  # type: ignore[attr-defined]

        fscope = self._new_scope("function", scope)
        for arg in all_args:
            self._bind(fscope, arg.arg)
        for child in node.body:  # type: ignore[attr-defined]
            self._walk(child, fscope)

    _walk_FunctionDef = _walk_function
    _walk_AsyncFunctionDef = _walk_function

    def _walk_Lambda(self, node: ast.Lambda, scope: _Scope) -> None:
        args = node.args
        for default in list(args.defaults) + [d for d in args.kw_defaults if d is not None]:
            self._walk(default, scope)
        lscope = self._new_scope("function", scope)
        all_args = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
        if args.vararg:
            all_args.append(args.vararg)
        if args.kwarg:
            all_args.append(args.kwarg)
        for arg in all_args:
            self._bind(lscope, arg.arg)
        self._walk(node.body, lscope)

    def _walk_ClassDef(self, node: ast.ClassDef, scope: _Scope) -> None:
        for decorator in node.decorator_list:
            self._walk(decorator, scope)
        for base in node.bases:
            self._walk(base, scope)
        for keyword in node.keywords:
            self._walk(keyword.value, scope)
        self._bind(scope, node.name)

        cscope = self._new_scope("class", scope)
        for child in node.body:
            self._walk(child, cscope)


def _forward_ref_names(text: str) -> Set[str]:
    """Names referenced by a string forward-reference annotation (best effort)."""
    names: Set[str] = set()
    try:
        expr = ast.parse(text.strip(), mode="eval")
    except (SyntaxError, ValueError):
        return names
    for sub in ast.walk(expr):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
            names.add(sub.id)
        elif isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
            names.add(sub.value.id)
    return names


def scoped_import_usage(tree: ast.AST) -> Tuple[Set[Tuple[int, str]], Set[str]]:
    """Return ``(used_keys, protected)`` for scope-aware import-usage refinement.

    ``used_keys`` holds ``(lineno, bound_name)`` for every import binding that at
    least one load resolves to under Python's scoping rules. ``protected`` holds
    names that must always count as used (``__all__`` exports, string forward
    references, ``global``/``nonlocal`` names). The caller keeps its flat "used"
    set as the safety floor and only downgrades an import to unused when it is
    absent from both — so an incomplete model can never fabricate a use it should
    have kept... it can only fail to *downgrade*, never wrongly downgrade.
    """
    builder = _ScopeModelBuilder()
    builder.build(tree)
    used_keys: Set[Tuple[int, str]] = set()
    for scope in builder.scopes:
        for name in scope.loads:
            resolved = _resolve_scope(scope, name)
            if resolved is not None and name in resolved.import_lines:
                for lineno in resolved.import_lines[name]:
                    used_keys.add((lineno, name))
    return used_keys, builder.protected


class ImportChecker:
    """Main class for handling Python import checking and cleanup."""

    def __init__(self, check_mode: bool = True, verbose: bool = False, quiet: bool = False):
        """
        Initialize the ImportChecker.

        Args:
            check_mode: If True, perform read-only analysis. If False, cleanup unused imports.
            verbose: Enable verbose output
            quiet: Suppress all human-readable stdout (used by ``--format json`` so
                stdout carries only the JSON document). Findings are still
                collected in ``self.findings``.
        """
        self.check_mode = check_mode
        self.verbose = verbose
        self.quiet = quiet
        self.processed_files = 0
        self.total_issues = 0
        # Machine-readable findings, collected regardless of output format.
        self.findings: List[Dict[str, Any]] = []

    def log_verbose(self, message: str) -> None:
        """Print verbose message if verbose mode is enabled (and not quiet)."""
        if self.verbose and not self.quiet:
            print(f"[VERBOSE] {message}")

    def _record_findings(self, file_path: Path, unused_imports: List[ImportInfo]) -> None:
        """Append one finding per unused import to the machine-readable list."""
        for import_info in unused_imports:
            self.findings.append(
                {
                    "code": "unused-import",
                    "file": str(file_path),
                    "line": import_info.line_number,
                    "message": f"unused import: {self._format_import(import_info)}",
                    # Unused imports block the gate (exit 1) in check mode, so they
                    # are reported as errors, mirroring the validator severity model.
                    "severity": "error",
                }
            )

    def extract_imports_from_ast(self, tree: ast.AST) -> List[ImportInfo]:
        """
        Extract all import statements from an AST.

        Args:
            tree: The AST tree to analyze

        Returns:
            List of ImportInfo objects containing import details
        """
        imports = []
        shared_lines = self._shared_statement_lines(tree)
        sole_block_lines = self._sole_block_import_lines(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                # Handle 'import module' statements (may list several modules).
                all_names = [alias.name for alias in node.names]
                all_aliases = [alias.asname for alias in node.names]
                for alias in node.names:
                    import_info = ImportInfo(
                        module=alias.name,
                        names=[],  # Empty for regular imports
                        alias=alias.asname,
                        line_number=node.lineno,
                        is_from_import=False,
                    )
                    # Record the modules/aliases sharing this line so cleanup can
                    # partially rewrite `import a, b` instead of dropping the line.
                    import_info.all_names_on_line = all_names
                    import_info.all_aliases_on_line = all_aliases
                    import_info.shares_line = node.lineno in shared_lines
                    import_info.sole_in_block = node.lineno in sole_block_lines
                    imports.append(import_info)

            elif isinstance(node, ast.ImportFrom):
                # Handle 'from module import name' statements. Preserve the
                # relative-import level (leading dots) so the module round-trips:
                # dropping node.level turns `from .pkg import x` into the wrong
                # absolute module (or an unparseable `from  import x`) on cleanup.
                module_name = "." * node.level + (node.module or "")

                # `from __future__ import ...` are compiler directives, not real
                # imports — they're never referenced by name, so never "unused".
                if module_name == "__future__":
                    continue

                # Store all names from this import in a single ImportInfo object
                all_names = [alias.name for alias in node.names]
                all_aliases = [alias.asname for alias in node.names]

                # Create individual ImportInfo objects for analysis
                for alias in node.names:
                    import_info = ImportInfo(
                        module=module_name,
                        names=[alias.name],
                        alias=alias.asname,
                        line_number=node.lineno,
                        is_from_import=True,
                    )
                    # Store reference to all names on the same line for cleanup
                    import_info.all_names_on_line = all_names
                    import_info.all_aliases_on_line = all_aliases
                    import_info.shares_line = node.lineno in shared_lines
                    import_info.sole_in_block = node.lineno in sole_block_lines
                    imports.append(import_info)

        return imports

    @staticmethod
    def _sole_block_import_lines(tree: ast.AST) -> Set[int]:
        """Line numbers of imports that are the only statement in a nested block.

        Removing such an import would leave an empty block body (e.g. an
        ``if TYPE_CHECKING:`` guard or a function body) that no longer parses.
        The module body is exempt — an empty module is valid Python.
        """
        lines: Set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Module):
                continue
            for field in ("body", "orelse", "finalbody"):
                block = getattr(node, field, None)
                if isinstance(block, list) and len(block) == 1:
                    stmt = block[0]
                    if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                        lines.add(stmt.lineno)
        return lines

    @staticmethod
    def _shared_statement_lines(tree: ast.AST) -> Set[int]:
        """Line numbers that begin more than one statement (e.g. ``import os; f()``).

        An import sharing its line with another statement cannot be removed or
        rewritten safely — dropping the physical line would delete the neighbour
        too — so cleanup leaves these imports in place.
        """
        counts: Dict[int, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.stmt):
                counts[node.lineno] = counts.get(node.lineno, 0) + 1
        return {line for line, count in counts.items() if count > 1}

    def extract_name_references(self, tree: ast.AST) -> Set[str]:
        """
        Extract all name references from an AST (excluding imports).

        Args:
            tree: The AST tree to analyze

        Returns:
            Set of referenced names
        """
        references: Set[str] = set()
        _NameReferenceVisitor(references).visit(tree)
        return references

    def analyze_imports(
        self, imports: List[ImportInfo], references: Set[str]
    ) -> Tuple[List[ImportInfo], List[ImportInfo]]:
        """
        Analyze imports to determine which are used and which are unused.

        Args:
            imports: List of ImportInfo objects
            references: Set of names referenced in the code

        Returns:
            Tuple of (used_imports, unused_imports)
        """
        used_imports: List[ImportInfo] = []
        unused_imports: List[ImportInfo] = []

        for import_info in imports:
            import_info.used = self._import_is_used(import_info, references)
            (used_imports if import_info.used else unused_imports).append(import_info)

        return used_imports, unused_imports

    @staticmethod
    def _import_is_used(import_info: ImportInfo, references: Set[str]) -> bool:
        """Return True if an import (or its alias) is referenced in the code."""
        if import_info.is_from_import:
            # `from module import *` exposes an unknowable set of names, so it can
            # never be proven unused — treat it as always used (pyflakes does the
            # same). Otherwise cleanup would delete a live wildcard import.
            if "*" in import_info.names:
                return True
            # 'from module import name' — any imported name (or its alias) used.
            return any((import_info.alias or name) in references for name in import_info.names)

        # 'import module' — match the alias/module, including dotted access.
        check_name = import_info.alias if import_info.alias else import_info.module
        module_base = check_name.split(".")[0]
        return module_base in references or check_name in references

    @staticmethod
    def _bound_name(import_info: ImportInfo) -> str:
        """The local name an import binds (what a reference must use to reach it)."""
        if import_info.is_from_import:
            return import_info.alias or (import_info.names[0] if import_info.names else "")
        return import_info.alias or import_info.module.split(".")[0]

    def _refine_with_scopes(
        self,
        tree: ast.AST,
        used_imports: List[ImportInfo],
        unused_imports: List[ImportInfo],
    ) -> Tuple[List[ImportInfo], List[ImportInfo]]:
        """Downgrade flat-"used" imports that scope analysis proves are unused.

        The flat pass (:meth:`analyze_imports`) treats a name loaded *anywhere* as
        a use, so it can miss an import shadowed by a parameter or one used only in
        an unrelated scope. This applies Python's scoping rules to move such
        provably-unused imports to the unused list. It is strictly one-directional
        (only used -> unused) and never touches a name that is protected
        (``__all__`` / forward reference / ``global`` / ``nonlocal``) or a star
        import, so it cannot turn a genuine use into a removal. Any failure in the
        analysis leaves the safe flat result untouched.
        """
        try:
            used_keys, protected = scoped_import_usage(tree)
        except Exception:  # pragma: no cover - defensive: never worse than flat
            return used_imports, unused_imports

        still_used: List[ImportInfo] = []
        newly_unused: List[ImportInfo] = []
        for import_info in used_imports:
            bound = self._bound_name(import_info)
            resolves = (import_info.line_number, bound) in used_keys
            if bound == "*" or not bound or bound in protected or resolves:
                still_used.append(import_info)
            else:
                import_info.used = False
                newly_unused.append(import_info)
        return still_used, unused_imports + newly_unused

    def remove_unused_imports(self, content: str, unused_imports: List[ImportInfo]) -> str:
        """
        Remove unused import lines from file content while preserving formatting.
        Handles partial removal for multi-name imports.

        Args:
            content: Original file content as string
            unused_imports: List of ImportInfo objects for unused imports

        Returns:
            Modified content with unused imports removed
        """
        # Never touch an import whose removal would corrupt surrounding code
        # (shares its line with another statement, or is a block's sole body).
        removable = [imp for imp in unused_imports if imp.safe_to_remove]
        if not removable:
            return content

        lines = content.splitlines(keepends=True)
        from_by_line, plain_by_line = self._partition_unused(removable)
        lines_to_remove: Set[int] = set()

        # Rewrite each statement that needs partial removal, keeping used names.
        for line_number, unused_from_line in from_by_line.items():
            self._rewrite_from_import(lines, line_number, unused_from_line, lines_to_remove)
        for line_number, unused_plain_line in plain_by_line.items():
            self._rewrite_plain_import(lines, line_number, unused_plain_line, lines_to_remove)

        string_lines = self._multiline_string_lines(content)
        return self._finalize_lines(lines, lines_to_remove, string_lines)

    @staticmethod
    def _partition_unused(
        unused_imports: List[ImportInfo],
    ) -> Tuple[Dict[int, List[ImportInfo]], Dict[int, List[ImportInfo]]]:
        """Group unused imports by 1-based line number, split by statement kind.

        Returns ``(from_by_line, plain_by_line)``. Both ``from module import ...``
        and plain ``import a, b`` statements can list several names and span
        multiple physical lines, so each is rewritten in place rather than having
        its line dropped wholesale (which would delete a used name sharing it).
        """
        from_by_line: Dict[int, List[ImportInfo]] = {}
        plain_by_line: Dict[int, List[ImportInfo]] = {}
        for import_info in unused_imports:
            bucket = from_by_line if import_info.is_from_import else plain_by_line
            bucket.setdefault(import_info.line_number, []).append(import_info)
        return from_by_line, plain_by_line

    def _rewrite_from_import(
        self,
        lines: List[str],
        line_number: int,
        unused_from_line: List[ImportInfo],
        lines_to_remove: Set[int],
    ) -> None:
        """Rewrite a single from-import statement in place, dropping unused names.

        A from-import may span several physical lines (parenthesized or
        backslash-continued); continuation lines are removed and the statement is
        rewritten on its first line, or removed entirely if nothing remains.
        """
        start_idx = line_number - 1  # 0-based
        if not (0 <= start_idx < len(lines)):
            return

        end_idx = self._find_statement_span(lines, start_idx)
        original_line = lines[start_idx]
        all_names = unused_from_line[0].all_names_on_line
        all_aliases = unused_from_line[0].all_aliases_on_line
        # Match on the (name, alias) pair so `path as p1, path as p2` — which
        # share a name but are distinct imports — drop only the unused alias.
        unused_pairs = {(imp.names[0], imp.alias) for imp in unused_from_line}

        remaining_names = [
            f"{name} as {all_aliases[i]}" if all_aliases[i] else name
            for i, name in enumerate(all_names)
            if (name, all_aliases[i]) not in unused_pairs
        ]

        # Drop every continuation line of the statement.
        for idx in range(start_idx + 1, end_idx + 1):
            lines_to_remove.add(idx)

        if not remaining_names:
            # All names were unused — remove the entire statement.
            lines_to_remove.add(start_idx)
            return

        # Preserve the parenthesized multi-line layout when a kept name carries
        # an inline comment, so the comment survives (the single-line collapse
        # below would otherwise drop every continuation-line comment).
        if end_idx > start_idx and self._preserve_multiline_from_import(
            lines, start_idx, end_idx, unused_pairs, lines_to_remove
        ):
            return

        module_name = unused_from_line[0].module
        new_import_line = f"from {module_name} import {', '.join(remaining_names)}"
        indent = original_line[: len(original_line) - len(original_line.lstrip())]
        newline = "\r\n" if original_line.endswith("\r\n") else "\n"

        # Preserve an inline comment only for single-line statements.
        comment = ""
        if end_idx == start_idx and "#" in original_line:
            comment = original_line[original_line.find("#") :].rstrip("\r\n")

        if comment:
            lines[start_idx] = f"{indent}{new_import_line}  {comment}{newline}"
        else:
            lines[start_idx] = f"{indent}{new_import_line}{newline}"

    @staticmethod
    def _from_entry_pair(code: str) -> Optional[Tuple[str, Optional[str]]]:
        """Parse a single ``name``/``name as alias`` entry into a (name, alias) pair."""
        entry = code.split("#", 1)[0].strip().rstrip(",").strip()
        if not entry:
            return None
        if " as " in entry:
            name, _, alias = entry.partition(" as ")
            return name.strip(), alias.strip() or None
        parts = entry.split()
        return (parts[0], None) if len(parts) == 1 else None

    def _preserve_multiline_from_import(
        self,
        lines: List[str],
        start_idx: int,
        end_idx: int,
        unused_pairs: Set[Tuple[str, Optional[str]]],
        lines_to_remove: Set[int],
    ) -> bool:
        """Drop only the unused-name lines of a parenthesized multi-line import.

        Handles the common one-name-per-line layout where the opening line ends
        with ``(``, the closing line is just ``)``, and each middle line holds a
        single name. Returns True (and keeps the layout, comments intact) only
        when a kept name carries an inline comment; otherwise returns False so
        the caller falls back to the single-line collapse.
        """
        opening = lines[start_idx].split("#", 1)[0].rstrip()
        closing = lines[end_idx].split("#", 1)[0].strip()
        if not opening.endswith("(") or not closing.startswith(")"):
            return False

        keep_indices: Set[int] = set()
        remove_indices: Set[int] = set()
        for idx in range(start_idx + 1, end_idx):
            pair = self._from_entry_pair(lines[idx])
            if pair is None:
                return False  # unclassifiable line — bail to the safe collapse
            (remove_indices if pair in unused_pairs else keep_indices).add(idx)

        # Only worth preserving the layout when a kept line has a comment to save.
        if not keep_indices or not any("#" in lines[idx] for idx in keep_indices):
            return False

        lines_to_remove.discard(start_idx)
        lines_to_remove.discard(end_idx)
        for idx in keep_indices:
            lines_to_remove.discard(idx)
        for idx in remove_indices:
            lines_to_remove.add(idx)
        return True

    def _rewrite_plain_import(
        self,
        lines: List[str],
        line_number: int,
        unused_on_line: List[ImportInfo],
        lines_to_remove: Set[int],
    ) -> None:
        """Rewrite a plain ``import a, b`` statement in place, dropping unused modules.

        The plain-import analogue of :meth:`_rewrite_from_import`. A single
        ``import`` statement may list several comma-separated modules and be
        backslash-continued across physical lines; only when every module on it
        is unused is the whole statement removed, otherwise the used modules are
        kept. This avoids deleting a used module (or an orphaned continuation
        line) when just one name on the statement is unused.
        """
        start_idx = line_number - 1  # 0-based
        if not (0 <= start_idx < len(lines)):
            return

        end_idx = self._find_statement_span(lines, start_idx)
        original_line = lines[start_idx]
        all_names = unused_on_line[0].all_names_on_line
        all_aliases = unused_on_line[0].all_aliases_on_line
        # Match on the (module, alias) pair so `import os as a, os as b` drops
        # only the unused alias rather than every occurrence of the module.
        unused_pairs = {(imp.module, imp.alias) for imp in unused_on_line}

        remaining = [
            f"{name} as {all_aliases[i]}" if all_aliases[i] else name
            for i, name in enumerate(all_names)
            if (name, all_aliases[i]) not in unused_pairs
        ]

        # Drop every continuation line of the statement.
        for idx in range(start_idx + 1, end_idx + 1):
            lines_to_remove.add(idx)

        if not remaining:
            # Every module on the statement was unused — remove it entirely.
            lines_to_remove.add(start_idx)
            return

        indent = original_line[: len(original_line) - len(original_line.lstrip())]
        newline = "\r\n" if original_line.endswith("\r\n") else "\n"
        new_import_line = f"import {', '.join(remaining)}"

        # Preserve an inline comment only for single-line statements.
        comment = ""
        if end_idx == start_idx and "#" in original_line:
            comment = original_line[original_line.find("#") :].rstrip("\r\n")

        if comment:
            lines[start_idx] = f"{indent}{new_import_line}  {comment}{newline}"
        else:
            lines[start_idx] = f"{indent}{new_import_line}{newline}"

    @staticmethod
    def _multiline_string_lines(content: str) -> Set[int]:
        """0-based indices of physical lines that lie inside a multi-line string.

        Blank lines inside triple-quoted strings must never be collapsed, or the
        string's value would change. Only strings spanning more than one physical
        line can contain a blank line, so single-line strings are ignored.
        """
        string_lines: Set[int] = set()
        try:
            for tok in tokenize.generate_tokens(io.StringIO(content).readline):
                if tok.type == tokenize.STRING and tok.end[0] > tok.start[0]:
                    for lineno in range(tok.start[0], tok.end[0] + 1):
                        string_lines.add(lineno - 1)  # 0-based
        except (tokenize.TokenError, IndentationError, SyntaxError):
            # Tokenizing failed (already-odd source); collapse nothing to be safe.
            pass
        return string_lines

    @staticmethod
    def _finalize_lines(lines: List[str], lines_to_remove: Set[int], string_lines: Set[int]) -> str:
        """Drop removed lines and collapse only removal-seam blank runs to <=2.

        A run of blank lines is collapsed only when it borders (or spans) a
        removed line, so blank runs in untouched code keep their original
        spacing; blank lines inside multi-line strings are never collapsed.
        """
        kept = [(i, line) for i, line in enumerate(lines) if i not in lines_to_remove]
        result: List[str] = []
        run: List[Tuple[int, str]] = []

        def flush() -> None:
            if not run:
                return
            lo, hi = run[0][0], run[-1][0]
            # A seam is a removed line adjacent to, or interspersed within, the run.
            seam = any(idx in lines_to_remove for idx in range(lo - 1, hi + 2))
            if seam and len(run) > 2:
                result.extend(line for _, line in run[:2])
            else:
                result.extend(line for _, line in run)

        for idx, line in kept:
            if line.strip() == "" and idx not in string_lines:
                run.append((idx, line))
            else:
                flush()
                run = []
                result.append(line)
        flush()
        return "".join(result)

    def _find_statement_span(self, lines: List[str], start_idx: int) -> int:
        """
        Find the index of the last physical line of an import statement that
        begins at ``start_idx``.

        Handles parenthesized (``from x import (a, b)``) and backslash-continued
        statements that span multiple physical lines.

        Args:
            lines: List of file lines
            start_idx: Index of the statement's first line

        Returns:
            Index of the statement's final line
        """
        depth = 0
        idx = start_idx
        while idx < len(lines):
            code = lines[idx].split("#", 1)[0]
            depth += code.count("(") - code.count(")")
            continues = code.rstrip().endswith("\\")
            if depth <= 0 and not continues:
                return idx
            idx += 1
        return len(lines) - 1

    @staticmethod
    def _format_import(import_info: ImportInfo) -> str:
        """Render an ImportInfo back to its source-like statement string."""
        if import_info.is_from_import:
            import_str = f"from {import_info.module} import {', '.join(import_info.names)}"
        else:
            import_str = f"import {import_info.module}"
        if import_info.alias:
            import_str += f" as {import_info.alias}"
        return import_str

    def _read_and_parse(self, file_path: Path) -> Tuple[str, ast.AST, str]:
        """Read a file and parse it into an AST.

        Reads UTF-8 with a latin-1 fallback, and returns the encoding that
        succeeded so cleanup can write the file back the same way instead of
        re-encoding it as UTF-8. ``newline=""`` preserves the original line
        endings (CRLF is not silently rewritten to LF).
        """
        encoding = "utf-8"
        try:
            with open(file_path, "r", encoding="utf-8", newline="") as file:
                content = file.read()
        except UnicodeDecodeError:
            # Retry with a permissive encoding if UTF-8 fails.
            encoding = "latin-1"
            with open(file_path, "r", encoding="latin-1", newline="") as file:
                content = file.read()
        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError as e:
            raise ImportCheckerError(f"Syntax error in {file_path}: {e}")
        return content, tree, encoding

    def _report_check(self, file_path: Path, used_imports: List[ImportInfo], unused_imports: List[ImportInfo]) -> None:
        """Print read-only analysis results for one file."""
        if self.quiet:
            return
        print(f"Analyzing: {file_path}")
        if unused_imports:
            print(f"  Found {len(unused_imports)} unused import(s):")
            for import_info in unused_imports:
                print(f"    Line {import_info.line_number}: {self._format_import(import_info)}")
        else:
            print("  No unused imports found")

        if self.verbose:
            print(f"  Used imports: {len(used_imports)}")
            for import_info in used_imports:
                print(f"    Line {import_info.line_number}: {self._format_import(import_info)}")

    def _report_cleanup(
        self,
        file_path: Path,
        content: str,
        unused_imports: List[ImportInfo],
        encoding: str = "utf-8",
    ) -> None:
        """Remove unused imports from a file (with backup) and print results."""
        if not self.quiet:
            print(f"Cleaning: {file_path}")
        if not unused_imports:
            if not self.quiet:
                print("  No unused imports to remove")
            return

        # Imports whose removal would corrupt code are reported but left untouched.
        removable = [imp for imp in unused_imports if imp.safe_to_remove]
        skipped = [imp for imp in unused_imports if not imp.safe_to_remove]

        if removable:
            if not self.quiet:
                print(f"  Removing {len(removable)} unused import(s)")

            # Create a backup before modifying.
            backup_path = file_path.with_suffix(file_path.suffix + ".backup")
            self.log_verbose(f"Creating backup: {backup_path}")
            shutil.copy2(file_path, backup_path)

            modified_content = self.remove_unused_imports(content, removable)
            # Write back with the encoding we read and without newline
            # translation, so line endings and non-UTF-8 bytes are preserved.
            with open(file_path, "w", encoding=encoding, newline="") as file:
                file.write(modified_content)

            if not self.quiet:
                print("  Removed imports:")
                for import_info in removable:
                    print(f"    Line {import_info.line_number}: {self._format_import(import_info)}")
                print(f"  Backup saved as: {backup_path}")

        if skipped and not self.quiet:
            print("  Left in place (unsafe to auto-remove):")
            for import_info in skipped:
                print(f"    Line {import_info.line_number}: {self._format_import(import_info)}")

    def process_file(self, file_path: Path) -> None:
        """
        Process a single Python file for import analysis.

        Args:
            file_path: Path to the Python file to process

        Raises:
            ImportCheckerError: If file processing fails
        """
        try:
            self.log_verbose(f"Processing file: {file_path}")

            # Validate file exists and is readable
            if not file_path.exists():
                raise ImportCheckerError(f"File not found: {file_path}")

            if not file_path.is_file():
                raise ImportCheckerError(f"Path is not a file: {file_path}")

            # Check if file is a Python file
            if file_path.suffix not in [".py", ".pyw"]:
                self.log_verbose(f"Skipping non-Python file: {file_path}")
                return

            content, tree, encoding = self._read_and_parse(file_path)

            imports = self.extract_imports_from_ast(tree)
            references = self.extract_name_references(tree)
            self.log_verbose(f"Found {len(imports)} imports and {len(references)} name references")

            used_imports, unused_imports = self.analyze_imports(imports, references)
            used_imports, unused_imports = self._refine_with_scopes(tree, used_imports, unused_imports)

            self.processed_files += 1
            self.total_issues += len(unused_imports)
            self._record_findings(file_path, unused_imports)

            if self.check_mode:
                self._report_check(file_path, used_imports, unused_imports)
            else:
                self._report_cleanup(file_path, content, unused_imports, encoding)

        except PermissionError as e:
            raise ImportCheckerError(f"Permission denied accessing file {file_path}: {e}")
        except Exception as e:
            raise ImportCheckerError(f"Error processing file {file_path}: {e}")

    # Directory names never scanned during a recursive walk (in addition to any
    # dot-prefixed / hidden directory).
    _EXCLUDED_DIRS = frozenset({"venv", "node_modules", "site-packages", "__pycache__"})

    @staticmethod
    def _is_excluded_path(file_path: Path, root: Path) -> bool:
        """True if ``file_path`` lies under a hidden or vendored directory of ``root``.

        Only directory components *below* the target are considered, so pointing
        the tool at a path that happens to sit under a dot-directory still works.
        """
        try:
            rel = file_path.relative_to(root)
        except ValueError:
            return False
        for part in rel.parts[:-1]:  # directory components, excluding the filename
            if part.startswith(".") or part in ImportChecker._EXCLUDED_DIRS:
                return True
        return False

    def process_directory(self, directory_path: Path, recursive: bool = True) -> None:
        """
        Process all Python files in a directory.

        Args:
            directory_path: Path to the directory to process
            recursive: If True, process subdirectories recursively

        Raises:
            ImportCheckerError: If directory processing fails
        """
        try:
            self.log_verbose(f"Processing directory: {directory_path}")

            if not directory_path.exists():
                raise ImportCheckerError(f"Directory not found: {directory_path}")

            if not directory_path.is_dir():
                raise ImportCheckerError(f"Path is not a directory: {directory_path}")

            python_files = self._discover_python_files(directory_path, recursive)
            if not python_files:
                if not self.quiet:
                    print(f"No Python files found in: {directory_path}")
                return

            self.log_verbose(f"Found {len(python_files)} Python files")
            self._process_files(python_files)

        except PermissionError as e:
            raise ImportCheckerError(f"Permission denied accessing directory {directory_path}: {e}")
        except Exception as e:
            raise ImportCheckerError(f"Error processing directory {directory_path}: {e}")

    def _discover_python_files(self, directory_path: Path, recursive: bool) -> List[Path]:
        """Return sorted .py/.pyw files under a directory, skipping vendored dirs."""
        patterns = ("**/*.py", "**/*.pyw") if recursive else ("*.py", "*.pyw")
        return sorted(
            f
            for pattern in patterns
            for f in directory_path.glob(pattern)
            if not self._is_excluded_path(f, directory_path)
        )

    def _process_files(self, python_files: List[Path]) -> None:
        """Process every file, surfacing per-file failures together at the end.

        One unreadable / syntax-error file must not abort the run and leave the
        rest unprocessed, so failures are collected and raised as a single
        operational error (exit 2) only after every file has been attempted.
        """
        failures: List[str] = []
        for file_path in python_files:
            try:
                self.process_file(file_path)
            except ImportCheckerError as e:
                failures.append(str(e))
                if not self.quiet:
                    print(f"  Skipping {file_path}: {e}")

        if failures:
            raise ImportCheckerError(f"{len(failures)} file(s) could not be processed: " + "; ".join(failures))

    def run(self, target_path: Path, recursive: bool = True) -> None:
        """
        Run the import checker on the specified target.

        Args:
            target_path: Path to file or directory to process
            recursive: If True and target is directory, process recursively

        Raises:
            ImportCheckerError: If processing fails
        """
        try:
            # Resolve the path to handle relative paths and symlinks
            resolved_path = target_path.resolve()

            if resolved_path.is_file():
                self.process_file(resolved_path)
            elif resolved_path.is_dir():
                self.process_directory(resolved_path, recursive)
            else:
                raise ImportCheckerError(f"Target path does not exist: {target_path}")

            # Print summary
            if not self.quiet:
                mode_str = "Analysis" if self.check_mode else "Cleanup"
                print(f"\n{mode_str} complete:")
                print(f"  Files processed: {self.processed_files}")
                print(f"  Issues found: {self.total_issues}")

        except ImportCheckerError:
            raise
        except Exception as e:
            raise ImportCheckerError(f"Unexpected error during processing: {e}")


def validate_target_path(path_str: str) -> Path:
    """
    Validate and convert target path string to Path object.

    Args:
        path_str: String representation of the target path

    Returns:
        Path object for the target

    Raises:
        argparse.ArgumentTypeError: If path is invalid
    """
    try:
        path = Path(path_str)

        # Basic validation - detailed validation happens in ImportChecker
        if not path.exists():
            raise argparse.ArgumentTypeError(f"Path does not exist: {path_str}")

        return path

    except Exception as e:
        raise argparse.ArgumentTypeError(f"Invalid path '{path_str}': {e}")


def setup_argument_parser() -> argparse.ArgumentParser:
    """
    Set up and configure the command-line argument parser.

    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        prog="python-import-checker",
        description="Analyze and clean up unused imports in Python files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --check myfile.py                    # Analyze single file
  %(prog)s --check src/                         # Analyze directory recursively
  %(prog)s --cleanup --no-recursive src/       # Clean directory non-recursively
  %(prog)s --cleanup myfile.py --verbose       # Clean file with verbose output
  %(prog)s --validate .                        # Validate config artifacts in this directory
        """,
    )

    # Mode selection (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--check", action="store_true", help="Perform read-only analysis of imports (no changes made)"
    )
    mode_group.add_argument("--cleanup", action="store_true", help="Remove unused imports from files (modifies files)")
    mode_group.add_argument(
        "--validate",
        action="store_true",
        help="Validate committed config artifacts (pyproject.toml, pip.conf, requirements.txt)",
    )

    # Target path (required)
    parser.add_argument("target", type=validate_target_path, help="Path to Python file or directory to process")

    # Optional arguments. Directory scans recurse by default; pass --no-recursive
    # to scan only the top level (``recursive`` defaults to True via store_false).
    parser.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        help="Scan only the top directory level (default: recurse into subdirectories)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        help=(
            "Output format (default: human). 'json' emits a single machine-readable "
            "JSON document to stdout with the full set of findings; stdout is kept "
            "clean (status/progress is routed to stderr)."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to a .dependably-check config (default: discovered by walking up from the target)",
    )
    parser.add_argument(
        "--fail-on",
        action="append",
        metavar="KEY=VALUE",
        default=None,
        help=(
            "CI gate (repeatable): exit 1 if a rule trips. "
            "severity=<critical|high|moderate|low|info> trips when any finding is "
            "at or above that level on the shared severity ladder; count=<N> trips "
            "when the total number of findings exceeds N. Additive to the default "
            "gate (unused imports / validation errors still gate on their own)."
        ),
    )
    parser.add_argument("--version", action="version", version=f"python-import-checker {__version__}")

    return parser


def _run_validate(
    target: Path,
    verbose: bool,
    config: Optional[Path] = None,
    output_format: str = "human",
    fail_on: Optional[List[Tuple[str, str]]] = None,
    recursive: bool = True,
) -> int:
    """Dispatch --validate to the validators package (lazy import)."""
    try:
        from validators.runner import run_validators
    except ImportError:  # installed wheel (src.validators)
        from .validators.runner import run_validators
    if verbose:
        # In json mode keep stdout clean; status goes to stderr.
        stream = sys.stderr if output_format == "json" else sys.stdout
        print(f"Validating config artifacts under: {target}", file=stream)
    exit_code: int = run_validators(
        target, recursive=recursive, config_path=config, output_format=output_format, fail_on=fail_on
    )
    return exit_code


def _run_import_check(args: argparse.Namespace, fail_on: Optional[List[Tuple[str, str]]] = None) -> int:
    """Run the AST import checker in --check or --cleanup mode."""
    check_mode = args.check
    json_mode = args.format == "json"
    if args.verbose:
        mode_str = "check" if check_mode else "cleanup"
        # Route status to stderr in json mode so stdout carries only the document.
        stream = sys.stderr if json_mode else sys.stdout
        print(f"Running in {mode_str} mode on: {args.target}", file=stream)
        print(f"Recursive: {args.recursive}", file=stream)

    checker = ImportChecker(check_mode=check_mode, verbose=args.verbose, quiet=json_mode)
    checker.run(target_path=args.target, recursive=args.recursive)

    # In check mode, exit non-zero when unused imports are found so the tool can
    # gate CI / git hooks (linter convention). Cleanup mode returns 0 — it has
    # already removed them.
    exit_code = EXIT_FINDINGS if (check_mode and checker.total_issues > 0) else EXIT_OK

    # The unified --fail-on gate is additive: it can only escalate a clean run to
    # a finding (exit 1); it never relaxes the default gate above.
    if exit_code == EXIT_OK and gate_trips(checker.findings, fail_on or []):
        exit_code = EXIT_FINDINGS

    if json_mode:
        emit_json(
            build_json_report(
                target=args.target,
                scanned=checker.processed_files,
                raw_findings=checker.findings,
                category="lint",
                exit_code=exit_code,
            )
        )

    return exit_code


def main() -> int:
    """
    Main entry point for the CLI application.

    Returns:
        Exit code: 0 clean, 1 findings (block), 2 usage/operational error.
    """
    try:
        parser = setup_argument_parser()
        args = parser.parse_args()

        # Validate the unified --fail-on gate up front; a bad rule is a usage
        # error (argparse-style exit 2), not an operational failure.
        try:
            fail_on_rules = parse_fail_on(args.fail_on or [])
        except ValueError as exc:
            parser.error(str(exc))

        if args.validate:
            return _run_validate(args.target, args.verbose, args.config, args.format, fail_on_rules, args.recursive)
        return _run_import_check(args, fail_on_rules)

    # Operational / internal errors are NOT findings: per the suite convention
    # exit 1 is reserved for findings (block), so these exit 2.
    except ImportCheckerError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return EXIT_ERROR
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
