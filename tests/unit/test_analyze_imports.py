"""Unit tests for ImportChecker.analyze_imports method."""

import sys
import os

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from checker import ImportChecker, ImportInfo


class TestAnalyzeImports:
    """Test cases for analyze_imports method."""

    def setup_method(self):
        """Set up test instance."""
        self.checker = ImportChecker()

    def test_analyze_all_used_imports(self):
        """Test analysis when all imports are used."""
        imports = [
            ImportInfo("os", [], line_number=1),
            ImportInfo("sys", [], line_number=2),
            ImportInfo("json", [], line_number=3),
        ]
        references = {"os", "sys", "json"}

        used_imports, unused_imports = self.checker.analyze_imports(imports, references)

        assert len(used_imports) == 3
        assert len(unused_imports) == 0

        # Check that all imports are marked as used
        for imp in used_imports:
            assert imp.used is True

    def test_analyze_all_unused_imports(self):
        """Test analysis when all imports are unused."""
        imports = [
            ImportInfo("os", [], line_number=1),
            ImportInfo("sys", [], line_number=2),
            ImportInfo("json", [], line_number=3),
        ]
        references = set()  # No references

        used_imports, unused_imports = self.checker.analyze_imports(imports, references)

        assert len(used_imports) == 0
        assert len(unused_imports) == 3

        # Check that all imports are marked as unused
        for imp in unused_imports:
            assert imp.used is False

    def test_analyze_mixed_usage(self):
        """Test analysis with mixed used and unused imports."""
        imports = [
            ImportInfo("os", [], line_number=1),  # Used
            ImportInfo("sys", [], line_number=2),  # Unused
            ImportInfo("json", [], line_number=3),  # Used
        ]
        references = {"os", "json"}

        used_imports, unused_imports = self.checker.analyze_imports(imports, references)

        assert len(used_imports) == 2
        assert len(unused_imports) == 1

        used_modules = [imp.module for imp in used_imports]
        unused_modules = [imp.module for imp in unused_imports]

        assert "os" in used_modules
        assert "json" in used_modules
        assert "sys" in unused_modules

    def test_analyze_import_with_alias(self):
        """Test analysis of imports with aliases."""
        imports = [
            ImportInfo("numpy", [], alias="np", line_number=1),  # Used via alias
            ImportInfo("pandas", [], alias="pd", line_number=2),  # Unused
            ImportInfo("matplotlib", [], alias="plt", line_number=3),  # Used via alias
        ]
        references = {"np", "plt"}  # Using aliases, not original names

        used_imports, unused_imports = self.checker.analyze_imports(imports, references)

        assert len(used_imports) == 2
        assert len(unused_imports) == 1

        used_aliases = [imp.alias for imp in used_imports]
        unused_aliases = [imp.alias for imp in unused_imports]

        assert "np" in used_aliases
        assert "plt" in used_aliases
        assert "pd" in unused_aliases

    def test_analyze_from_imports_single_name(self):
        """Test analysis of from-imports with single names."""
        imports = [
            ImportInfo("pathlib", ["Path"], line_number=1, is_from_import=True),  # Used
            ImportInfo("os", ["getcwd"], line_number=2, is_from_import=True),  # Used
            ImportInfo("sys", ["exit"], line_number=3, is_from_import=True),  # Unused
        ]
        references = {"Path", "getcwd"}

        used_imports, unused_imports = self.checker.analyze_imports(imports, references)

        assert len(used_imports) == 2
        assert len(unused_imports) == 1

        used_names = [imp.names[0] for imp in used_imports]
        unused_names = [imp.names[0] for imp in unused_imports]

        assert "Path" in used_names
        assert "getcwd" in used_names
        assert "exit" in unused_names

    def test_analyze_from_imports_with_alias(self):
        """Test analysis of from-imports with aliases."""
        imports = [
            ImportInfo("datetime", ["datetime"], alias="dt", line_number=1, is_from_import=True),  # Used
            ImportInfo("datetime", ["timedelta"], alias="td", line_number=1, is_from_import=True),  # Unused
            ImportInfo("pathlib", ["Path"], alias="PathClass", line_number=2, is_from_import=True),  # Used
        ]
        references = {"dt", "PathClass"}  # Using aliases

        used_imports, unused_imports = self.checker.analyze_imports(imports, references)

        assert len(used_imports) == 2
        assert len(unused_imports) == 1

        used_aliases = [imp.alias for imp in used_imports]
        unused_aliases = [imp.alias for imp in unused_imports]

        assert "dt" in used_aliases
        assert "PathClass" in used_aliases
        assert "td" in unused_aliases

    def test_analyze_dotted_module_access(self):
        """Test analysis of dotted module access."""
        imports = [
            ImportInfo("os.path", [], line_number=1),  # Used via os
            ImportInfo("xml.etree", [], line_number=2),  # Unused
            ImportInfo("urllib.parse", [], line_number=3),  # Used via urllib
        ]
        references = {"os", "urllib"}  # Using base module names

        used_imports, unused_imports = self.checker.analyze_imports(imports, references)

        assert len(used_imports) == 2
        assert len(unused_imports) == 1

        used_modules = [imp.module for imp in used_imports]
        unused_modules = [imp.module for imp in unused_imports]

        assert "os.path" in used_modules
        assert "urllib.parse" in used_modules
        assert "xml.etree" in unused_modules

    def test_analyze_module_with_full_name_reference(self):
        """Test analysis when full module name is referenced."""
        imports = [
            ImportInfo("collections", [], line_number=1),  # Used with full name
            ImportInfo("itertools", [], line_number=2),  # Unused
        ]
        references = {"collections"}  # Full module name used

        used_imports, unused_imports = self.checker.analyze_imports(imports, references)

        assert len(used_imports) == 1
        assert len(unused_imports) == 1

        assert used_imports[0].module == "collections"
        assert unused_imports[0].module == "itertools"

    def test_analyze_mixed_import_types(self):
        """Test analysis with mixed import types."""
        imports = [
            ImportInfo("os", [], line_number=1),  # Regular import, used
            ImportInfo("sys", [], alias="system", line_number=2),  # Aliased import, unused
            ImportInfo("json", ["loads"], line_number=3, is_from_import=True),  # From import, used
            ImportInfo("json", ["dumps"], line_number=3, is_from_import=True),  # From import, unused
            ImportInfo(
                "pathlib", ["Path"], alias="P", line_number=4, is_from_import=True
            ),  # From import with alias, used
        ]
        references = {"os", "loads", "P"}

        used_imports, unused_imports = self.checker.analyze_imports(imports, references)

        assert len(used_imports) == 3
        assert len(unused_imports) == 2

        used_info = [(imp.module, imp.names, imp.alias, imp.is_from_import) for imp in used_imports]
        unused_info = [(imp.module, imp.names, imp.alias, imp.is_from_import) for imp in unused_imports]

        assert ("os", [], None, False) in used_info
        assert ("json", ["loads"], None, True) in used_info
        assert ("pathlib", ["Path"], "P", True) in used_info

        assert ("sys", [], "system", False) in unused_info
        assert ("json", ["dumps"], None, True) in unused_info

    def test_analyze_case_sensitivity(self):
        """Test that analysis is case sensitive."""
        imports = [ImportInfo("OS", [], line_number=1), ImportInfo("sys", [], line_number=2)]  # Different case
        references = {"os", "sys"}  # Lowercase 'os', correct 'sys'

        used_imports, unused_imports = self.checker.analyze_imports(imports, references)

        assert len(used_imports) == 1
        assert len(unused_imports) == 1

        assert used_imports[0].module == "sys"
        assert unused_imports[0].module == "OS"

    def test_analyze_empty_inputs(self):
        """Test analysis with empty inputs."""
        # Empty imports
        used_imports, unused_imports = self.checker.analyze_imports([], {"os", "sys"})
        assert len(used_imports) == 0
        assert len(unused_imports) == 0

        # Empty references
        imports = [ImportInfo("os", [], line_number=1)]
        used_imports, unused_imports = self.checker.analyze_imports(imports, set())
        assert len(used_imports) == 0
        assert len(unused_imports) == 1

        # Both empty
        used_imports, unused_imports = self.checker.analyze_imports([], set())
        assert len(used_imports) == 0
        assert len(unused_imports) == 0

    def test_analyze_star_import(self):
        """Star imports expose an unknowable set of names, so they can never be
        proven unused and must always be treated as used (never auto-removed)."""
        imports = [ImportInfo("math", ["*"], line_number=1, is_from_import=True)]
        references: set = set()  # Nothing references the star import by name.

        used_imports, unused_imports = self.checker.analyze_imports(imports, references)

        assert len(unused_imports) == 0
        assert len(used_imports) == 1
        assert used_imports[0].names == ["*"]

    def test_analyze_preserves_import_info(self):
        """Test that analysis preserves all ImportInfo attributes."""
        imports = [ImportInfo("os", [], alias="operating_system", line_number=5)]
        imports[0].all_names_on_line = ["os"]  # Additional attribute

        references = {"operating_system"}

        used_imports, unused_imports = self.checker.analyze_imports(imports, references)

        assert len(used_imports) == 1
        used_import = used_imports[0]

        # Check all attributes are preserved
        assert used_import.module == "os"
        assert used_import.names == []
        assert used_import.alias == "operating_system"
        assert used_import.line_number == 5
        assert used_import.is_from_import is False
        assert used_import.used is True
        assert hasattr(used_import, "all_names_on_line")
        assert used_import.all_names_on_line == ["os"]
