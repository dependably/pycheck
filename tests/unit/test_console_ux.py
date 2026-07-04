"""Console-output correctness fixes from a Fable UX review (moonlitlabs/pycheck#26).

Covers the two HIGH-severity correctness bugs plus the medium/low clarity fixes:

1. Real per-name line numbers -- a multi-line ``from x import (a, b, c)`` used
   to attribute every name to the opening ``(`` line; each name now reports its
   own physical line (``ImportInfo.name_line``), and the human/JSON report no
   longer synthesizes a fake ``from x import name`` statement for it.
2. Side-effect / re-export imports (``__init__.py``, a dotted whole-module
   import, or a bulk from-import that is entirely unused) are downgraded to a
   separate "possibly-intentional" category that ``--cleanup`` never removes
   without the ``--remove-possible-reexports`` opt-in -- following the old
   advice could delete a live registration import and break the program.
3. Clean files are quiet by default (reserved for --verbose); paths print
   relative to the cwd; a findings>0 run prints a "run --cleanup" hint; the
   unused-import count is pluralized correctly.
"""

import json
import os
import sys
from unittest.mock import patch

import pytest

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from checker import ImportChecker, main  # noqa: E402

MULTILINE_BULK_IMPORT = """from ancestry_mcp.tools import (
    auth,
    trees_read,
    trees_write,
)
"""


requires_per_alias_lineno = pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="ast.alias only carries its own lineno on 3.10+; 3.9 falls back " "to the statement line",
)


class TestRealPerNameLineNumbers:
    """HIGH #1: each unused name is reported at its own real line."""

    @requires_per_alias_lineno
    def test_json_location_line_is_the_names_own_line(self, tmp_path, capsys):
        f = tmp_path / "x.py"
        f.write_text(MULTILINE_BULK_IMPORT)

        with patch.object(sys, "argv", ["checker.py", "--check", "--format", "json", str(f)]):
            main()
        doc = json.loads(capsys.readouterr().out)

        by_line = {finding["location"]["line"]: finding["message"] for finding in doc["findings"]}
        assert 2 in by_line and "auth" in by_line[2]
        assert 3 in by_line and "trees_read" in by_line[3]
        assert 4 in by_line and "trees_write" in by_line[4]
        # None of the 3 findings are (wrongly) attributed to the opening line.
        assert 1 not in by_line

    @requires_per_alias_lineno
    def test_human_report_uses_real_line_not_opening_line(self, tmp_path, capsys):
        f = tmp_path / "x.py"
        f.write_text(MULTILINE_BULK_IMPORT)

        with patch.object(sys, "argv", ["checker.py", "--check", str(f)]):
            main()
        out = capsys.readouterr().out

        assert "Line 2: auth" in out
        assert "Line 3: trees_read" in out
        assert "Line 4: trees_write" in out
        # The old behaviour blamed every name on the opening paren's line.
        assert "Line 1: " not in out

    def test_does_not_synthesize_a_statement_that_is_not_in_the_source(self, tmp_path, capsys):
        """The report describes "name (from module)", never a fabricated
        "from module import name" statement that never appears verbatim."""
        f = tmp_path / "x.py"
        f.write_text(MULTILINE_BULK_IMPORT)

        with patch.object(sys, "argv", ["checker.py", "--check", str(f)]):
            main()
        out = capsys.readouterr().out

        assert "from ancestry_mcp.tools import trees_write" not in out
        assert "trees_write" in out
        assert "ancestry_mcp.tools" in out


class TestPossiblyIntentionalImports:
    """HIGH #2: side-effect / re-export imports are hedged, not "unused"."""

    def test_dunder_all_export_is_already_used_never_reaches_unused(self, tmp_path):
        # Pre-existing behaviour (not new for #26): __all__-exported names are
        # never flagged unused in the first place, so they never need hedging.
        f = tmp_path / "x.py"
        f.write_text("import os\n\n__all__ = ['os']\n")
        checker = ImportChecker(check_mode=True, quiet=True)
        checker.process_file(f)
        assert checker.total_issues == 0

    def test_init_py_unused_imports_are_hedged_not_definite(self, tmp_path):
        f = tmp_path / "__init__.py"
        f.write_text("from .tools import auth\n")
        checker = ImportChecker(check_mode=True, quiet=True)
        checker.process_file(f)

        assert checker.total_issues == 1
        imp = next(i for i in checker.findings if i["code"] == "possible-intentional-import")
        assert "__init__.py" in imp["message"]

    def test_dotted_bare_import_never_attribute_accessed_is_hedged(self, tmp_path):
        f = tmp_path / "server.py"
        f.write_text("import ancestry_mcp.tools.registry\nprint('hi')\n")
        checker = ImportChecker(check_mode=True, quiet=True)
        checker.process_file(f)

        finding = checker.findings[0]
        assert finding["code"] == "possible-intentional-import"
        # Internal severity is "warning" -> the shared JSON ladder maps it to
        # "low" (see build_json_report / _to_finding), lower than a definite
        # unused import's "error" -> "high".
        assert finding["severity"] == "warning"

    def test_single_segment_bare_import_stays_definite_unused(self, tmp_path):
        """A plain top-level `import os` (no dot) is ordinary dead code, not
        hedged -- only *dotted* whole-module imports get the side-effect hedge."""
        f = tmp_path / "server.py"
        f.write_text("import os\nprint('hi')\n")
        checker = ImportChecker(check_mode=True, quiet=True)
        checker.process_file(f)

        finding = checker.findings[0]
        assert finding["code"] == "unused-import"

    def test_bulk_fully_unused_from_import_is_hedged(self, tmp_path):
        """The ticket's own repro: an 8(+)-name from-import where every name is
        unused looks like a plugin/tool-registry import, not dead code."""
        f = tmp_path / "server.py"
        f.write_text(MULTILINE_BULK_IMPORT)
        checker = ImportChecker(check_mode=True, quiet=True)
        checker.process_file(f)

        assert checker.total_issues == 3
        assert all(finding["code"] == "possible-intentional-import" for finding in checker.findings)

    def test_partially_unused_from_import_stays_definite(self, tmp_path):
        """A from-import where *some* names are used is ordinary dead code for
        the unused ones -- the bulk heuristic only fires when ALL are unused."""
        f = tmp_path / "server.py"
        f.write_text("from typing import Dict, List, Set\nx: Dict[str, int] = {}\n")
        checker = ImportChecker(check_mode=True, quiet=True)
        checker.process_file(f)

        assert checker.total_issues == 2  # List, Set
        assert all(finding["code"] == "unused-import" for finding in checker.findings)

    def test_two_name_from_import_fully_unused_is_not_bulk(self, tmp_path):
        """Below the bulk threshold (>= 3 names): two unused names in one
        from-import is still ordinary dead code, not a registry-import hedge."""
        f = tmp_path / "server.py"
        f.write_text("from typing import Dict, List\nprint('hi')\n")
        checker = ImportChecker(check_mode=True, quiet=True)
        checker.process_file(f)

        assert checker.total_issues == 2
        assert all(finding["code"] == "unused-import" for finding in checker.findings)

    def test_report_check_lists_hedged_separately_from_definite(self, tmp_path, capsys):
        f = tmp_path / "server.py"
        content = MULTILINE_BULK_IMPORT + "import sys\n"  # sys: plain, definite-unused
        f.write_text(content)

        with patch.object(sys, "argv", ["checker.py", "--check", str(f)]):
            main()
        out = capsys.readouterr().out

        assert "Found 1 unused import:" in out  # sys
        assert "possibly-intentional imports" in out
        assert "[every name in this multi-import statement is unused" in out


class TestCleanupNeverAutoRemovesHedgedImports:
    """HIGH #2: --cleanup must never delete a possibly-intentional import
    without the explicit --remove-possible-reexports opt-in."""

    def test_cleanup_leaves_bulk_hedged_import_in_place_by_default(self, tmp_path):
        f = tmp_path / "server.py"
        original = MULTILINE_BULK_IMPORT
        f.write_text(original)

        checker = ImportChecker(check_mode=False, quiet=True)
        checker.process_file(f)

        # Not removed: the file is untouched and no backup was written.
        assert f.read_text() == original
        assert not f.with_suffix(".py.backup").exists()

    def test_cleanup_leaves_init_py_import_in_place_by_default(self, tmp_path):
        f = tmp_path / "__init__.py"
        original = "from .tools import auth\n"
        f.write_text(original)

        checker = ImportChecker(check_mode=False, quiet=True)
        checker.process_file(f)

        assert f.read_text() == original

    def test_remove_possible_reexports_opt_in_does_remove_them(self, tmp_path):
        f = tmp_path / "__init__.py"
        f.write_text("from .tools import auth\n")

        checker = ImportChecker(check_mode=False, quiet=True, remove_possible_reexports=True)
        checker.process_file(f)

        assert "auth" not in f.read_text()

    def test_cleanup_mixed_batch_removes_definite_keeps_hedged(self, tmp_path):
        """Batch/fan-out regression: a directory with a mix of definite-unused,
        hedged (__init__.py + bulk-from-import), and used imports -- cleanup
        must remove only the definite ones across every file in one run."""
        normal = tmp_path / "utils.py"
        normal.write_text("import sys\nimport os\nprint(os.getcwd())\n")  # sys unused (definite)

        pkg_init = tmp_path / "__init__.py"
        pkg_init.write_text("from .tools import auth\n")  # hedged (__init__.py)

        registry = tmp_path / "server.py"
        registry.write_text(MULTILINE_BULK_IMPORT)  # hedged (bulk from-import)

        checker = ImportChecker(check_mode=False, quiet=True)
        checker.run(tmp_path)

        assert "import sys" not in normal.read_text()
        assert "import os" in normal.read_text()
        assert pkg_init.read_text() == "from .tools import auth\n"
        assert registry.read_text() == MULTILINE_BULK_IMPORT
        assert normal.with_suffix(".py.backup").exists()
        assert not pkg_init.with_suffix(".py.backup").exists()
        assert not registry.with_suffix(".py.backup").exists()


class TestQuietByDefault:
    """MEDIUM: clean files are quiet by default; --verbose restores the
    per-file "Analyzing:/No unused imports found" stream."""

    def test_clean_directory_prints_no_per_file_noise_by_default(self, tmp_path, capsys):
        (tmp_path / "a.py").write_text("import os\nprint(os.getcwd())\n")
        (tmp_path / "b.py").write_text("import sys\nprint(sys.version)\n")

        with patch.object(sys, "argv", ["checker.py", "--check", str(tmp_path)]):
            code = main()
        out = capsys.readouterr().out

        assert code == 0
        assert "Analyzing:" not in out
        assert "No unused imports found" not in out
        assert "2 files clean" in out

    def test_verbose_restores_per_file_clean_stream(self, tmp_path, capsys):
        (tmp_path / "a.py").write_text("import os\nprint(os.getcwd())\n")

        with patch.object(sys, "argv", ["checker.py", "--check", "--verbose", str(tmp_path)]):
            main()
        out = capsys.readouterr().out

        assert "Analyzing:" in out
        assert "No unused imports found" in out

    def test_dirty_file_still_prints_by_default(self, tmp_path, capsys):
        (tmp_path / "a.py").write_text("import sys\n")  # unused

        with patch.object(sys, "argv", ["checker.py", "--check", str(tmp_path)]):
            main()
        out = capsys.readouterr().out

        assert "Analyzing:" in out
        assert "Found 1 unused import:" in out


class TestRelativePaths:
    """MEDIUM: paths print relative to the cwd, matching the JSON convention."""

    def test_analyzing_line_is_relative_to_cwd(self, tmp_path, capsys):
        f = tmp_path / "x.py"
        f.write_text("import sys\n")

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch.object(sys, "argv", ["checker.py", "--check", "x.py"]):
                main()
        finally:
            os.chdir(original_cwd)
        out = capsys.readouterr().out

        assert "Analyzing: x.py" in out
        assert str(tmp_path) not in out


class TestCleanupHint:
    """MEDIUM: a findings>0 run tells the user how to fix it."""

    def test_hint_present_when_findings_found(self, tmp_path, capsys):
        f = tmp_path / "x.py"
        f.write_text("import sys\n")

        with patch.object(sys, "argv", ["checker.py", "--check", str(f)]):
            main()
        out = capsys.readouterr().out

        assert "import-checker --cleanup" in out
        assert ".backup" in out

    def test_no_hint_when_clean(self, tmp_path, capsys):
        f = tmp_path / "x.py"
        f.write_text("import os\nprint(os.getcwd())\n")

        with patch.object(sys, "argv", ["checker.py", "--check", str(f)]):
            main()
        out = capsys.readouterr().out

        assert "import-checker --cleanup" not in out


class TestSingularPluralWording:
    """LOW: real singular/plural, not 'import(s)'."""

    def test_singular_unused_import(self, tmp_path, capsys):
        f = tmp_path / "x.py"
        f.write_text("import sys\n")
        with patch.object(sys, "argv", ["checker.py", "--check", str(f)]):
            main()
        out = capsys.readouterr().out
        assert "Found 1 unused import:" in out
        assert "import(s)" not in out

    def test_plural_unused_imports(self, tmp_path, capsys):
        f = tmp_path / "x.py"
        f.write_text("import sys\nimport json\n")
        with patch.object(sys, "argv", ["checker.py", "--check", str(f)]):
            main()
        out = capsys.readouterr().out
        assert "Found 2 unused imports:" in out
        assert "import(s)" not in out

    def test_summary_noun_matches_per_file_noun(self, tmp_path, capsys):
        f = tmp_path / "x.py"
        f.write_text("import sys\n")
        with patch.object(sys, "argv", ["checker.py", "--check", str(f)]):
            main()
        out = capsys.readouterr().out
        assert "1 unused import found" in out
        assert "Issues found" not in out


class TestRemovePossibleReexportsFlag:
    """CLI plumbing for the --remove-possible-reexports opt-in."""

    def test_defaults_to_false(self, tmp_path):
        from checker import setup_argument_parser

        f = tmp_path / "x.py"
        f.write_text("import os\n")
        parser = setup_argument_parser()
        args = parser.parse_args(["--check", str(f)])
        assert args.remove_possible_reexports is False

    def test_flag_parses_true(self, tmp_path):
        from checker import setup_argument_parser

        f = tmp_path / "x.py"
        f.write_text("import os\n")
        parser = setup_argument_parser()
        args = parser.parse_args(["--cleanup", "--remove-possible-reexports", str(f)])
        assert args.remove_possible_reexports is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
