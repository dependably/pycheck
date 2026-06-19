"""Unit tests for ImportChecker.remove_unused_imports method."""

import sys
import os

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from checker import ImportChecker, ImportInfo


class TestRemoveUnusedImports:
    """Test cases for remove_unused_imports method."""

    def setup_method(self):
        """Set up test instance."""
        self.checker = ImportChecker()

    def test_remove_no_unused_imports(self):
        """Test removal when there are no unused imports."""
        content = """import os
import sys

def main():
    return os.getcwd(), sys.version
"""
        unused_imports = []

        result = self.checker.remove_unused_imports(content, unused_imports)

        assert result == content  # Should be unchanged

    def test_remove_single_basic_import(self):
        """Test removal of single basic import."""
        content = """import os
import sys
import json

def main():
    return os.getcwd(), sys.version
"""
        unused_imports = [ImportInfo("json", [], line_number=3)]

        result = self.checker.remove_unused_imports(content, unused_imports)

        expected = """import os
import sys

def main():
    return os.getcwd(), sys.version
"""
        assert result == expected

    def test_remove_multiple_basic_imports(self):
        """Test removal of multiple basic imports."""
        content = """import os
import sys
import json
import re

def main():
    return os.getcwd()
"""
        unused_imports = [
            ImportInfo("sys", [], line_number=2),
            ImportInfo("json", [], line_number=3),
            ImportInfo("re", [], line_number=4),
        ]

        result = self.checker.remove_unused_imports(content, unused_imports)

        expected = """import os

def main():
    return os.getcwd()
"""
        assert result == expected

    def test_remove_from_import_single_name(self):
        """Test removal of from-import with single name."""
        content = """from os import getcwd
from sys import version
from json import dumps

def main():
    return getcwd(), version
"""
        unused_imports = [ImportInfo("json", ["dumps"], line_number=3, is_from_import=True)]
        unused_imports[0].all_names_on_line = ["dumps"]
        unused_imports[0].all_aliases_on_line = [None]

        result = self.checker.remove_unused_imports(content, unused_imports)

        expected = """from os import getcwd
from sys import version

def main():
    return getcwd(), version
"""
        assert result == expected

    def test_remove_from_import_partial(self):
        """Test partial removal from multi-name from-import."""
        content = """from typing import Dict, List, Set
from collections import Counter, defaultdict

def main():
    data: Dict[str, List[str]] = {}
    counter = Counter([1, 2, 3])
    return data, counter
"""
        unused_imports = [
            ImportInfo("typing", ["Set"], line_number=1, is_from_import=True),
            ImportInfo("collections", ["defaultdict"], line_number=2, is_from_import=True),
        ]

        # Set up all_names_on_line for each import
        unused_imports[0].all_names_on_line = ["Dict", "List", "Set"]
        unused_imports[0].all_aliases_on_line = [None, None, None]
        unused_imports[1].all_names_on_line = ["Counter", "defaultdict"]
        unused_imports[1].all_aliases_on_line = [None, None]

        result = self.checker.remove_unused_imports(content, unused_imports)

        expected = """from typing import Dict, List
from collections import Counter

def main():
    data: Dict[str, List[str]] = {}
    counter = Counter([1, 2, 3])
    return data, counter
"""
        assert result == expected

    def test_remove_from_import_with_aliases(self):
        """Test removal of from-imports with aliases."""
        content = """from datetime import datetime as dt, timedelta as td, date as d

def main():
    now = dt.now()
    return now
"""
        unused_imports = [
            ImportInfo("datetime", ["timedelta"], alias="td", line_number=1, is_from_import=True),
            ImportInfo("datetime", ["date"], alias="d", line_number=1, is_from_import=True),
        ]

        # Set up all_names_on_line
        for imp in unused_imports:
            imp.all_names_on_line = ["datetime", "timedelta", "date"]
            imp.all_aliases_on_line = ["dt", "td", "d"]

        result = self.checker.remove_unused_imports(content, unused_imports)

        expected = """from datetime import datetime as dt

def main():
    now = dt.now()
    return now
"""
        assert result == expected

    def test_remove_entire_from_import_line(self):
        """Test removal of entire from-import line when all names are unused."""
        content = """from typing import Dict, List, Set
from collections import Counter

def main():
    counter = Counter([1, 2, 3])
    return counter
"""
        unused_imports = [
            ImportInfo("typing", ["Dict"], line_number=1, is_from_import=True),
            ImportInfo("typing", ["List"], line_number=1, is_from_import=True),
            ImportInfo("typing", ["Set"], line_number=1, is_from_import=True),
        ]

        # Set up all_names_on_line for all imports from same line
        for imp in unused_imports:
            imp.all_names_on_line = ["Dict", "List", "Set"]
            imp.all_aliases_on_line = [None, None, None]

        result = self.checker.remove_unused_imports(content, unused_imports)

        expected = """from collections import Counter

def main():
    counter = Counter([1, 2, 3])
    return counter
"""
        assert result == expected

    def test_remove_with_comments(self):
        """Test removal preserves comments."""
        content = """import os  # Operating system interface
import sys  # System specific parameters
import json  # JSON encoder/decoder

def main():
    return os.getcwd()  # Get current directory
"""
        unused_imports = [ImportInfo("sys", [], line_number=2), ImportInfo("json", [], line_number=3)]

        result = self.checker.remove_unused_imports(content, unused_imports)

        expected = """import os  # Operating system interface

def main():
    return os.getcwd()  # Get current directory
"""
        assert result == expected

    def test_remove_with_inline_comments_from_import(self):
        """Test removal preserves inline comments in from-imports."""
        content = """from typing import Dict, List, Set  # Type hints
from collections import Counter, defaultdict  # Collection types

def main():
    data: Dict[str, str] = {}
    return data
"""
        unused_imports = [
            ImportInfo("typing", ["List"], line_number=1, is_from_import=True),
            ImportInfo("typing", ["Set"], line_number=1, is_from_import=True),
            ImportInfo("collections", ["Counter"], line_number=2, is_from_import=True),
            ImportInfo("collections", ["defaultdict"], line_number=2, is_from_import=True),
        ]

        # Set up all_names_on_line
        unused_imports[0].all_names_on_line = ["Dict", "List", "Set"]
        unused_imports[0].all_aliases_on_line = [None, None, None]
        unused_imports[1].all_names_on_line = ["Dict", "List", "Set"]
        unused_imports[1].all_aliases_on_line = [None, None, None]
        unused_imports[2].all_names_on_line = ["Counter", "defaultdict"]
        unused_imports[2].all_aliases_on_line = [None, None]
        unused_imports[3].all_names_on_line = ["Counter", "defaultdict"]
        unused_imports[3].all_aliases_on_line = [None, None]

        result = self.checker.remove_unused_imports(content, unused_imports)

        expected = """from typing import Dict  # Type hints

def main():
    data: Dict[str, str] = {}
    return data
"""
        assert result == expected

    def test_remove_preserves_indentation(self):
        """Test removal preserves indentation in nested imports."""
        content = """def function():
    import os
    import sys
    import json
    
    return os.getcwd()
"""
        unused_imports = [ImportInfo("sys", [], line_number=3), ImportInfo("json", [], line_number=4)]

        result = self.checker.remove_unused_imports(content, unused_imports)

        expected = """def function():
    import os
    
    return os.getcwd()
"""
        assert result == expected

    def test_remove_preserves_blank_lines(self):
        """Test removal preserves appropriate blank lines."""
        content = """#!/usr/bin/env python3
\"\"\"Module docstring.\"\"\"

import os
import sys
import json

import requests
import numpy

def main():
    return os.getcwd(), requests.get('http://example.com')
"""
        unused_imports = [
            ImportInfo("sys", [], line_number=5),
            ImportInfo("json", [], line_number=6),
            ImportInfo("numpy", [], line_number=9),
        ]

        result = self.checker.remove_unused_imports(content, unused_imports)

        expected = """#!/usr/bin/env python3
\"\"\"Module docstring.\"\"\"

import os

import requests

def main():
    return os.getcwd(), requests.get('http://example.com')
"""
        assert result == expected

    def test_remove_multiline_from_import(self):
        """Test removal from multiline from-import."""
        content = """from collections import (
    Counter,
    defaultdict,
    deque,
    OrderedDict
)

def main():
    counter = Counter([1, 2, 3])
    ordered = OrderedDict([('a', 1)])
    return counter, ordered
"""
        unused_imports = [
            ImportInfo("collections", ["defaultdict"], line_number=1, is_from_import=True),
            ImportInfo("collections", ["deque"], line_number=1, is_from_import=True),
        ]

        # Set up all_names_on_line
        for imp in unused_imports:
            imp.all_names_on_line = ["Counter", "defaultdict", "deque", "OrderedDict"]
            imp.all_aliases_on_line = [None, None, None, None]

        result = self.checker.remove_unused_imports(content, unused_imports)

        expected = """from collections import Counter, OrderedDict

def main():
    counter = Counter([1, 2, 3])
    ordered = OrderedDict([('a', 1)])
    return counter, ordered
"""
        assert result == expected

    def test_remove_excessive_blank_lines(self):
        """Test removal cleans up excessive blank lines."""
        content = """import os
import sys
import json



import requests


def main():
    return os.getcwd()
"""
        unused_imports = [
            ImportInfo("sys", [], line_number=2),
            ImportInfo("json", [], line_number=3),
            ImportInfo("requests", [], line_number=7),
        ]

        result = self.checker.remove_unused_imports(content, unused_imports)

        # Should clean up excessive blank lines (limit to 2 consecutive)
        expected = """import os


def main():
    return os.getcwd()
"""
        assert result == expected

    def test_remove_mixed_import_types(self):
        """Test removal of mixed import types."""
        content = """import os
from sys import version
import json as js
from pathlib import Path, PurePath
from typing import Dict, List

def main():
    current_dir = os.getcwd()
    path_obj = Path(current_dir)
    data: Dict[str, str] = {}
    return current_dir, path_obj, data
"""
        unused_imports = [
            ImportInfo("sys", ["version"], line_number=2, is_from_import=True),
            ImportInfo("json", [], alias="js", line_number=3),
            ImportInfo("pathlib", ["PurePath"], line_number=4, is_from_import=True),
            ImportInfo("typing", ["List"], line_number=5, is_from_import=True),
        ]

        # Set up all_names_on_line for from-imports
        unused_imports[0].all_names_on_line = ["version"]
        unused_imports[0].all_aliases_on_line = [None]
        unused_imports[2].all_names_on_line = ["Path", "PurePath"]
        unused_imports[2].all_aliases_on_line = [None, None]
        unused_imports[3].all_names_on_line = ["Dict", "List"]
        unused_imports[3].all_aliases_on_line = [None, None]

        result = self.checker.remove_unused_imports(content, unused_imports)

        expected = """import os
from pathlib import Path
from typing import Dict

def main():
    current_dir = os.getcwd()
    path_obj = Path(current_dir)
    data: Dict[str, str] = {}
    return current_dir, path_obj, data
"""
        assert result == expected

    def test_remove_empty_content(self):
        """Test removal from empty content."""
        content = ""
        unused_imports = []

        result = self.checker.remove_unused_imports(content, unused_imports)

        assert result == ""

    def test_remove_with_windows_line_endings(self):
        """Test removal preserves Windows line endings."""
        content = "import os\r\nimport sys\r\n\r\ndef main():\r\n    return os.getcwd()\r\n"
        unused_imports = [ImportInfo("sys", [], line_number=2)]

        result = self.checker.remove_unused_imports(content, unused_imports)

        expected = "import os\r\n\r\ndef main():\r\n    return os.getcwd()\r\n"
        assert result == expected
