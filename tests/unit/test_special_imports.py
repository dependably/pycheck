"""Unit tests for special-case import handling: __future__ and __all__ re-exports."""

import ast
import os
import sys

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from checker import ImportChecker  # noqa: E402


def _analyze(source):
    checker = ImportChecker(check_mode=True)
    tree = ast.parse(source)
    imports = checker.extract_imports_from_ast(tree)
    references = checker.extract_name_references(tree)
    return checker.analyze_imports(imports, references)


class TestFutureImports:
    def test_future_import_never_flagged(self):
        used, unused = _analyze("from __future__ import annotations\n\nx: int = 1\n")
        assert unused == []
        # __future__ is excluded from the import list entirely.
        assert all(i.module != "__future__" for i in used)

    def test_future_import_excluded_from_extraction(self):
        checker = ImportChecker()
        imports = checker.extract_imports_from_ast(ast.parse("from __future__ import annotations\n"))
        assert imports == []


class TestAllReExports:
    def test_names_in_all_count_as_used(self):
        used, unused = _analyze("from mod import foo, bar\n\n__all__ = ['foo', 'bar']\n")
        assert unused == []
        assert {i.names[0] for i in used} == {"foo", "bar"}

    def test_name_absent_from_all_still_unused(self):
        used, unused = _analyze("from mod import foo, bar\n\n__all__ = ['foo']\n")
        assert {i.names[0] for i in used} == {"foo"}
        assert {i.names[0] for i in unused} == {"bar"}

    def test_all_augmented_assignment(self):
        used, unused = _analyze("from mod import foo\n\n__all__ = []\n__all__ += ['foo']\n")
        assert unused == []

    def test_all_tuple_form(self):
        used, unused = _analyze("from mod import foo\n\n__all__ = ('foo',)\n")
        assert unused == []


def _unused_names(source):
    """Full pipeline (flat analyze + scope refinement) -> sorted unused bound names."""
    checker = ImportChecker(check_mode=True)
    tree = ast.parse(source)
    imports = checker.extract_imports_from_ast(tree)
    references = checker.extract_name_references(tree)
    used, unused = checker.analyze_imports(imports, references)
    used, unused = checker._refine_with_scopes(tree, used, unused)
    return sorted(checker._bound_name(i) for i in unused)


class TestRedundantAliasReExports:
    """PEP 484 redundant alias (`from m import X as X`) = intentional re-export."""

    def test_from_import_redundant_alias_kept(self):
        assert _unused_names("from .ls import Server as Server\n") == []

    def test_plain_import_redundant_alias_kept(self):
        assert _unused_names("import os as os\n") == []

    def test_multiple_redundant_aliases_kept(self):
        assert _unused_names("from mod import a as a, b as b\n") == []

    def test_redundant_alias_survives_scope_refinement(self):
        # A re-export in an __init__-style module is referenced nowhere locally;
        # the scope pass must not downgrade it.
        assert _unused_names("from .core import Thing as Thing\ndef f(x):\n    return x\n") == []

    def test_non_redundant_alias_still_flagged_when_unused(self):
        # `X as Y` (Y != X) is a normal alias, not a re-export marker.
        assert _unused_names("from mod import Thing as T\n") == ["T"]
        assert _unused_names("import os as o\n") == ["o"]

    def test_plain_reexport_without_marker_still_flagged(self):
        # No __all__, no redundant alias -> flagged (documented, matches pyflakes).
        assert _unused_names("from .ls import Server\n") == ["Server"]
