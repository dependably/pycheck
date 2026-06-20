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
