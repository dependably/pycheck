"""Unit tests for ImportChecker.extract_imports_from_ast method."""

import ast
import sys
import os

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from checker import ImportChecker


class TestExtractImportsFromAst:
    """Test cases for extract_imports_from_ast method."""

    def setup_method(self):
        """Set up test instance."""
        self.checker = ImportChecker()

    def test_extract_basic_import(self):
        """Test extraction of basic import statements."""
        code = "import os\nimport sys"
        tree = ast.parse(code)

        imports = self.checker.extract_imports_from_ast(tree)

        assert len(imports) == 2

        # Check first import
        assert imports[0].module == "os"
        assert imports[0].names == []
        assert imports[0].alias is None
        assert imports[0].line_number == 1
        assert imports[0].is_from_import is False

        # Check second import
        assert imports[1].module == "sys"
        assert imports[1].names == []
        assert imports[1].alias is None
        assert imports[1].line_number == 2
        assert imports[1].is_from_import is False

    def test_extract_import_with_alias(self):
        """Test extraction of import with alias."""
        code = "import numpy as np\nimport pandas as pd"
        tree = ast.parse(code)

        imports = self.checker.extract_imports_from_ast(tree)

        assert len(imports) == 2

        # Check first import
        assert imports[0].module == "numpy"
        assert imports[0].names == []
        assert imports[0].alias == "np"
        assert imports[0].line_number == 1
        assert imports[0].is_from_import is False

        # Check second import
        assert imports[1].module == "pandas"
        assert imports[1].names == []
        assert imports[1].alias == "pd"
        assert imports[1].line_number == 2
        assert imports[1].is_from_import is False

    def test_extract_from_import_single(self):
        """Test extraction of single from-import."""
        code = "from pathlib import Path"
        tree = ast.parse(code)

        imports = self.checker.extract_imports_from_ast(tree)

        assert len(imports) == 1
        assert imports[0].module == "pathlib"
        assert imports[0].names == ["Path"]
        assert imports[0].alias is None
        assert imports[0].line_number == 1
        assert imports[0].is_from_import is True

    def test_extract_from_import_multiple(self):
        """Test extraction of multiple from-imports on same line."""
        code = "from typing import Dict, List, Set"
        tree = ast.parse(code)

        imports = self.checker.extract_imports_from_ast(tree)

        assert len(imports) == 3

        # Check that each name gets its own ImportInfo object
        names = [imp.names[0] for imp in imports]
        assert "Dict" in names
        assert "List" in names
        assert "Set" in names

        # Check that all have the same module and line number
        for imp in imports:
            assert imp.module == "typing"
            assert imp.line_number == 1
            assert imp.is_from_import is True
            assert len(imp.names) == 1

    def test_extract_from_import_with_alias(self):
        """Test extraction of from-import with alias."""
        code = "from datetime import datetime as dt, timedelta as td"
        tree = ast.parse(code)

        imports = self.checker.extract_imports_from_ast(tree)

        assert len(imports) == 2

        # Find imports by name
        dt_import = next(imp for imp in imports if imp.names == ["datetime"])
        td_import = next(imp for imp in imports if imp.names == ["timedelta"])

        assert dt_import.module == "datetime"
        assert dt_import.alias == "dt"
        assert dt_import.is_from_import is True

        assert td_import.module == "datetime"
        assert td_import.alias == "td"
        assert td_import.is_from_import is True

    def test_extract_multiple_import_statements(self):
        """Test extraction of mixed import statements."""
        code = """
import os
import sys as system
from pathlib import Path
from typing import Dict, List
"""
        tree = ast.parse(code)

        imports = self.checker.extract_imports_from_ast(tree)

        assert len(imports) == 5  # os, sys, Path, Dict, List

        # Find each import type
        os_import = next(imp for imp in imports if imp.module == "os")
        sys_import = next(imp for imp in imports if imp.module == "sys")
        path_import = next(imp for imp in imports if imp.names == ["Path"])
        dict_import = next(imp for imp in imports if imp.names == ["Dict"])
        list_import = next(imp for imp in imports if imp.names == ["List"])

        # Validate basic imports
        assert os_import.names == []
        assert os_import.alias is None
        assert os_import.is_from_import is False

        assert sys_import.names == []
        assert sys_import.alias == "system"
        assert sys_import.is_from_import is False

        # Validate from imports
        assert path_import.module == "pathlib"
        assert path_import.is_from_import is True

        assert dict_import.module == "typing"
        assert dict_import.is_from_import is True

        assert list_import.module == "typing"
        assert list_import.is_from_import is True

    def test_extract_relative_imports(self):
        """Test extraction of relative imports."""
        code = """
from . import helper
from ..utils import formatter
from ...parent import module
"""
        tree = ast.parse(code)

        imports = self.checker.extract_imports_from_ast(tree)

        assert len(imports) == 3

        helper_import = next(imp for imp in imports if imp.names == ["helper"])
        formatter_import = next(imp for imp in imports if imp.names == ["formatter"])
        module_import = next(imp for imp in imports if imp.names == ["module"])

        # The relative-import level (leading dots) is preserved so the module
        # round-trips on cleanup instead of collapsing to the wrong absolute name.
        assert helper_import.module == "."  # `from . import helper`
        assert formatter_import.module == "..utils"
        assert module_import.module == "...parent"

        for imp in imports:
            assert imp.is_from_import is True

    def test_extract_star_import(self):
        """Test extraction of star imports."""
        code = "from math import *"
        tree = ast.parse(code)

        imports = self.checker.extract_imports_from_ast(tree)

        assert len(imports) == 1
        assert imports[0].module == "math"
        assert imports[0].names == ["*"]
        assert imports[0].is_from_import is True

    def test_extract_no_imports(self):
        """Test extraction from code with no imports."""
        code = """
def main():
    return "Hello, World!"
"""
        tree = ast.parse(code)

        imports = self.checker.extract_imports_from_ast(tree)

        assert len(imports) == 0

    def test_extract_imports_with_docstring(self):
        """Test extraction ignores docstrings and comments."""
        code = '''
"""Module docstring."""
import os  # Import OS module
import sys
# This is a comment
from pathlib import Path
'''
        tree = ast.parse(code)

        imports = self.checker.extract_imports_from_ast(tree)

        assert len(imports) == 3

        modules = [imp.module for imp in imports if not imp.is_from_import]
        from_modules = [imp.module for imp in imports if imp.is_from_import]

        assert "os" in modules
        assert "sys" in modules
        assert "pathlib" in from_modules

    def test_extract_multiline_from_import(self):
        """Test extraction of multiline from-imports."""
        code = """
from collections import (
    Counter,
    defaultdict,
    deque
)
"""
        tree = ast.parse(code)

        imports = self.checker.extract_imports_from_ast(tree)

        assert len(imports) == 3

        names = [imp.names[0] for imp in imports]
        assert "Counter" in names
        assert "defaultdict" in names
        assert "deque" in names

        for imp in imports:
            assert imp.module == "collections"
            assert imp.is_from_import is True
            assert imp.line_number == 2  # Line where 'from' statement starts

    def test_extract_nested_imports(self):
        """Test extraction handles imports inside functions/classes."""
        code = """
import os

def function():
    import sys
    from pathlib import Path
    
class MyClass:
    import json
"""
        tree = ast.parse(code)

        imports = self.checker.extract_imports_from_ast(tree)

        assert len(imports) == 4

        modules = [imp.module for imp in imports if not imp.is_from_import]
        from_modules = [imp.module for imp in imports if imp.is_from_import]

        assert "os" in modules
        assert "sys" in modules
        assert "json" in modules
        assert "pathlib" in from_modules

    def test_all_names_on_line_attribute(self):
        """Test that all_names_on_line and all_aliases_on_line are set correctly."""
        code = "from typing import Dict, List as ListType, Set"
        tree = ast.parse(code)

        imports = self.checker.extract_imports_from_ast(tree)

        assert len(imports) == 3

        # Check that all imports have the same all_names_on_line
        expected_names = ["Dict", "List", "Set"]
        expected_aliases = [None, "ListType", None]

        for imp in imports:
            assert hasattr(imp, "all_names_on_line")
            assert hasattr(imp, "all_aliases_on_line")
            assert imp.all_names_on_line == expected_names
            assert imp.all_aliases_on_line == expected_aliases
