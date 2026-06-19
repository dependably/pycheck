"""Unit tests for ImportInfo class."""

import sys
import os

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from checker import ImportInfo


class TestImportInfo:
    """Test cases for ImportInfo class."""

    def test_init_basic_import(self):
        """Test initialization for basic import statement."""
        import_info = ImportInfo(module="os", names=[], line_number=5, is_from_import=False)

        assert import_info.module == "os"
        assert import_info.names == []
        assert import_info.alias is None
        assert import_info.line_number == 5
        assert import_info.is_from_import is False
        assert import_info.used is False

    def test_init_from_import(self):
        """Test initialization for from-import statement."""
        import_info = ImportInfo(module="pathlib", names=["Path"], line_number=10, is_from_import=True)

        assert import_info.module == "pathlib"
        assert import_info.names == ["Path"]
        assert import_info.alias is None
        assert import_info.line_number == 10
        assert import_info.is_from_import is True
        assert import_info.used is False

    def test_init_with_alias(self):
        """Test initialization with alias."""
        import_info = ImportInfo(module="numpy", names=[], alias="np", line_number=3, is_from_import=False)

        assert import_info.module == "numpy"
        assert import_info.names == []
        assert import_info.alias == "np"
        assert import_info.line_number == 3
        assert import_info.is_from_import is False
        assert import_info.used is False

    def test_init_from_import_with_alias(self):
        """Test initialization for from-import with alias."""
        import_info = ImportInfo(module="datetime", names=["datetime"], alias="dt", line_number=8, is_from_import=True)

        assert import_info.module == "datetime"
        assert import_info.names == ["datetime"]
        assert import_info.alias == "dt"
        assert import_info.line_number == 8
        assert import_info.is_from_import is True
        assert import_info.used is False

    def test_init_multiple_names(self):
        """Test initialization with multiple imported names."""
        import_info = ImportInfo(module="typing", names=["Dict", "List", "Set"], line_number=2, is_from_import=True)

        assert import_info.module == "typing"
        assert import_info.names == ["Dict", "List", "Set"]
        assert import_info.alias is None
        assert import_info.line_number == 2
        assert import_info.is_from_import is True
        assert import_info.used is False

    def test_init_default_values(self):
        """Test initialization with default values."""
        import_info = ImportInfo(module="sys", names=["version"])

        assert import_info.module == "sys"
        assert import_info.names == ["version"]
        assert import_info.alias is None
        assert import_info.line_number == 0
        assert import_info.is_from_import is False
        assert import_info.used is False

    def test_used_property(self):
        """Test the used property can be modified."""
        import_info = ImportInfo(module="os", names=[])

        assert import_info.used is False

        import_info.used = True
        assert import_info.used is True

        import_info.used = False
        assert import_info.used is False

    def test_repr(self):
        """Test string representation."""
        import_info = ImportInfo(module="pathlib", names=["Path"], alias="PathClass", line_number=15)

        expected_repr = "ImportInfo(module='pathlib', names=['Path'], alias='PathClass', line=15)"
        assert repr(import_info) == expected_repr

    def test_repr_no_alias(self):
        """Test string representation without alias."""
        import_info = ImportInfo(module="os", names=["getcwd"], line_number=5)

        expected_repr = "ImportInfo(module='os', names=['getcwd'], alias='None', line=5)"
        assert repr(import_info) == expected_repr

    def test_repr_empty_names(self):
        """Test string representation with empty names list."""
        import_info = ImportInfo(module="sys", names=[], line_number=1)

        expected_repr = "ImportInfo(module='sys', names=[], alias='None', line=1)"
        assert repr(import_info) == expected_repr

    def test_additional_attributes(self):
        """Test that additional attributes can be added dynamically."""
        import_info = ImportInfo(module="test", names=["func"])

        # These attributes are set by the ImportChecker during processing
        import_info.all_names_on_line = ["func", "other_func"]
        import_info.all_aliases_on_line = [None, "alias"]

        assert hasattr(import_info, "all_names_on_line")
        assert hasattr(import_info, "all_aliases_on_line")
        assert import_info.all_names_on_line == ["func", "other_func"]
        assert import_info.all_aliases_on_line == [None, "alias"]
