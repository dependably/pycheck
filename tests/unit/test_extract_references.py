"""Unit tests for ImportChecker.extract_name_references method."""

import ast
import pytest
import sys
import os

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from checker import ImportChecker


class TestExtractNameReferences:
    """Test cases for extract_name_references method."""
    
    def setup_method(self):
        """Set up test instance."""
        self.checker = ImportChecker()
    
    def test_extract_simple_names(self):
        """Test extraction of simple name references."""
        code = """
x = 5
y = x + 10
result = y * 2
"""
        tree = ast.parse(code)
        
        references = self.checker.extract_name_references(tree)
        
        assert "x" in references
        assert "y" in references
        # result is stored, not loaded, so shouldn't be in references
        assert "result" not in references
    
    def test_extract_function_calls(self):
        """Test extraction of function call references."""
        code = """
result = len(data)
output = print(result)
value = max(numbers)
"""
        tree = ast.parse(code)
        
        references = self.checker.extract_name_references(tree)
        
        assert "len" in references
        assert "data" in references
        assert "print" in references
        assert "result" in references
        assert "max" in references
        assert "numbers" in references
        # output and value are stored, not loaded
        assert "output" not in references
        assert "value" not in references
    
    def test_extract_attribute_access(self):
        """Test extraction of attribute access references."""
        code = """
current_dir = os.getcwd()
file_size = os.path.getsize(filename)
result = obj.method()
"""
        tree = ast.parse(code)
        
        references = self.checker.extract_name_references(tree)
        
        assert "os" in references  # Base object for attribute access
        assert "filename" in references
        assert "obj" in references
        # current_dir, file_size, result are stored
        assert "current_dir" not in references
        assert "file_size" not in references
        assert "result" not in references
        # getcwd, getsize, method are attributes, not name references
        assert "getcwd" not in references
        assert "getsize" not in references
        assert "method" not in references
    
    def test_extract_nested_attribute_access(self):
        """Test extraction with nested attribute access."""
        code = """
size = os.path.getsize(filename)
version = sys.version_info.major
"""
        tree = ast.parse(code)
        
        references = self.checker.extract_name_references(tree)
        
        assert "os" in references  # Base name in os.path.getsize
        assert "sys" in references  # Base name in sys.version_info.major
        assert "filename" in references
        # size and version are stored
        assert "size" not in references
        assert "version" not in references
    
    def test_ignore_import_statements(self):
        """Test that import statements are ignored."""
        code = """
import os
import sys as system
from pathlib import Path
from typing import Dict, List

# These should be detected as references
result = os.getcwd()
version = system.version
"""
        tree = ast.parse(code)
        
        references = self.checker.extract_name_references(tree)
        
        # Import statement names should not be in references
        assert "os" in references  # Used in os.getcwd()
        assert "system" in references  # Used in system.version
        assert "sys" not in references  # Only imported, not used
        assert "pathlib" not in references  # Only imported
        assert "Path" not in references  # Only imported
        assert "Dict" not in references  # Only imported
        assert "List" not in references  # Only imported
    
    def test_extract_in_function_definition(self):
        """Test extraction inside function definitions."""
        code = """
def process_data(data):
    result = len(data)
    processed = transform(result)
    return processed
"""
        tree = ast.parse(code)
        
        references = self.checker.extract_name_references(tree)
        
        assert "len" in references
        assert "data" in references  # Function parameter used
        assert "transform" in references
        assert "result" in references  # Used as argument to transform
        assert "processed" in references  # Used in return
        # Function name and parameter in definition are not references
        assert "process_data" not in references
    
    def test_extract_in_class_definition(self):
        """Test extraction inside class definitions."""
        code = """
class DataProcessor:
    def __init__(self, config):
        self.config = config
        self.data = []
    
    def process(self):
        result = transform(self.data)
        return result
"""
        tree = ast.parse(code)
        
        references = self.checker.extract_name_references(tree)
        
        assert "config" in references  # Parameter used
        assert "self" in references  # Used in attribute access
        assert "transform" in references
        # Class name and method names are not references
        assert "DataProcessor" not in references
        assert "__init__" not in references
        assert "process" not in references
    
    def test_extract_with_list_comprehension(self):
        """Test extraction in list comprehensions."""
        code = """
numbers = [1, 2, 3, 4, 5]
squares = [x**2 for x in numbers]
filtered = [item for item in data if condition(item)]
"""
        tree = ast.parse(code)
        
        references = self.checker.extract_name_references(tree)
        
        assert "numbers" in references  # Used in comprehension
        assert "data" in references  # Used in comprehension
        assert "condition" in references  # Function call in comprehension
        # Comprehension variables x and item are not references in this context
    
    def test_extract_with_lambda(self):
        """Test extraction in lambda expressions."""
        code = """
func = lambda x: transform(x) + offset
result = apply(func, data)
"""
        tree = ast.parse(code)
        
        references = self.checker.extract_name_references(tree)
        
        assert "transform" in references
        assert "offset" in references
        assert "apply" in references
        assert "func" in references
        assert "data" in references
        # Lambda parameter x is not a reference
    
    def test_extract_with_exception_handling(self):
        """Test extraction in try/except blocks."""
        code = """
try:
    result = risky_operation(data)
    log.info(result)
except ValueError as e:
    error_handler(e)
    fallback_result = default_value
"""
        tree = ast.parse(code)
        
        references = self.checker.extract_name_references(tree)
        
        assert "risky_operation" in references
        assert "data" in references
        assert "log" in references  # For log.info()
        assert "error_handler" in references
        assert "e" in references  # Exception variable used
        assert "default_value" in references
        # result is stored then loaded again in log.info(result), so it is referenced
        assert "result" in references
        # fallback_result is only assigned, never loaded
        assert "fallback_result" not in references
    
    def test_extract_with_context_manager(self):
        """Test extraction in with statements."""
        code = """
with open(filename, 'r') as f:
    content = f.read()
    processor.handle(content)
"""
        tree = ast.parse(code)
        
        references = self.checker.extract_name_references(tree)
        
        assert "open" in references
        assert "filename" in references
        assert "f" in references  # Used in f.read()
        assert "processor" in references  # For processor.handle()
        assert "content" in references  # Used as argument
    
    def test_extract_assignment_targets_excluded(self):
        """Test that assignment targets are not included in references."""
        code = """
x = 5
y, z = get_values()
obj.attr = value
items[0] = new_value
"""
        tree = ast.parse(code)
        
        references = self.checker.extract_name_references(tree)
        
        # Assignment targets should not be in references
        assert "x" not in references
        assert "y" not in references  
        assert "z" not in references
        
        # But these should be references (right side of assignment)
        assert "get_values" in references
        assert "obj" in references  # For obj.attr
        assert "value" in references
        assert "items" in references  # For items[0]
        assert "new_value" in references
    
    def test_extract_global_and_nonlocal(self):
        """Test extraction with global and nonlocal statements."""
        code = """
def outer():
    x = 10
    def inner():
        global y
        nonlocal x
        result = transform(x) + y
        return result
"""
        tree = ast.parse(code)
        
        references = self.checker.extract_name_references(tree)
        
        assert "transform" in references
        assert "x" in references  # Used in transform(x)
        assert "y" in references  # Used in addition
        assert "result" in references  # Used in return
        # Function names are not references
        assert "outer" not in references
        assert "inner" not in references
    
    def test_extract_empty_code(self):
        """Test extraction from empty code."""
        code = ""
        tree = ast.parse(code)
        
        references = self.checker.extract_name_references(tree)
        
        assert len(references) == 0
    
    def test_extract_only_imports(self):
        """Test extraction from code with only imports."""
        code = """
import os
import sys
from pathlib import Path
"""
        tree = ast.parse(code)
        
        references = self.checker.extract_name_references(tree)
        
        # Only imports, no usage, should have empty references
        assert len(references) == 0