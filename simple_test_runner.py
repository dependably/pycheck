#!/usr/bin/env python3
"""
Simple test runner that tests core functionality without external dependencies.
"""

import sys
import os
from pathlib import Path
import ast
import tempfile

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from checker import ImportChecker, ImportInfo, ImportCheckerError


def test_import_info_basic():
    """Test ImportInfo class basic functionality."""
    print("Testing ImportInfo class...")
    
    # Test basic initialization
    import_info = ImportInfo("os", [], line_number=5)
    assert import_info.module == "os"
    assert import_info.names == []
    assert import_info.line_number == 5
    
    # Test with from-import
    from_import = ImportInfo("pathlib", ["Path"], line_number=10, is_from_import=True)
    assert from_import.module == "pathlib"
    assert from_import.names == ["Path"]
    assert from_import.is_from_import is True
    
    # Test repr
    repr_str = repr(import_info)
    assert "ImportInfo" in repr_str
    assert "os" in repr_str
    
    print("✓ ImportInfo tests passed")


def test_extract_imports():
    """Test import extraction functionality."""
    print("Testing import extraction...")
    
    checker = ImportChecker()
    
    # Test basic imports
    code = """
import os
import sys as system
from pathlib import Path
from typing import Dict, List
"""
    tree = ast.parse(code)
    imports = checker.extract_imports_from_ast(tree)
    
    assert len(imports) == 5  # os, sys, Path, Dict, List
    
    # Find specific imports
    os_import = next(imp for imp in imports if imp.module == "os")
    sys_import = next(imp for imp in imports if imp.module == "sys")
    path_import = next(imp for imp in imports if imp.names == ["Path"])
    
    assert os_import.names == []
    assert os_import.is_from_import is False
    
    assert sys_import.alias == "system"
    assert sys_import.is_from_import is False
    
    assert path_import.module == "pathlib"
    assert path_import.is_from_import is True
    
    print("✓ Import extraction tests passed")


def test_extract_references():
    """Test name reference extraction."""
    print("Testing name reference extraction...")
    
    checker = ImportChecker()
    
    code = """
result = os.getcwd()
version = sys.version
data = transform(result)
"""
    tree = ast.parse(code)
    references = checker.extract_name_references(tree)
    
    expected_refs = {"os", "sys", "transform", "result"}
    assert expected_refs.issubset(references)
    
    # Should not include assignment targets
    assert "version" not in references
    assert "data" not in references
    
    print("✓ Name reference extraction tests passed")


def test_analyze_imports():
    """Test import analysis functionality."""
    print("Testing import analysis...")
    
    checker = ImportChecker()
    
    imports = [
        ImportInfo("os", [], line_number=1),          # Used
        ImportInfo("sys", [], line_number=2),         # Unused
        ImportInfo("json", ["loads"], line_number=3, is_from_import=True)  # Used
    ]
    
    references = {"os", "loads"}
    
    used_imports, unused_imports = checker.analyze_imports(imports, references)
    
    assert len(used_imports) == 2
    assert len(unused_imports) == 1
    
    used_modules = [imp.module for imp in used_imports]
    unused_modules = [imp.module for imp in unused_imports]
    
    assert "os" in used_modules
    assert "json" in used_modules
    assert "sys" in unused_modules
    
    print("✓ Import analysis tests passed")


def test_remove_unused_imports():
    """Test unused import removal."""
    print("Testing unused import removal...")
    
    checker = ImportChecker()
    
    content = """import os
import sys
import json

def main():
    return os.getcwd()
"""
    
    unused_imports = [
        ImportInfo("sys", [], line_number=2),
        ImportInfo("json", [], line_number=3)
    ]
    
    result = checker.remove_unused_imports(content, unused_imports)
    
    assert "import os" in result
    assert "import sys" not in result
    assert "import json" not in result
    assert "def main():" in result
    
    print("✓ Import removal tests passed")


def test_file_processing():
    """Test file processing functionality."""
    print("Testing file processing...")
    
    # Create temporary test file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
        tmp.write("""import os
import sys
import json

def main():
    return os.getcwd()
""")
        tmp.flush()
        tmp_path = Path(tmp.name)
    
    try:
        # Test check mode
        checker = ImportChecker(check_mode=True)
        original_issues = checker.total_issues
        
        checker.process_file(tmp_path)
        
        assert checker.processed_files == 1
        assert checker.total_issues > original_issues  # Should find unused imports
        
        # Test cleanup mode
        cleanup_checker = ImportChecker(check_mode=False)
        cleanup_checker.process_file(tmp_path)
        
        # Check that file was modified
        modified_content = tmp_path.read_text()
        assert "import sys" not in modified_content
        assert "import json" not in modified_content
        assert "import os" in modified_content  # Should remain
        
        # Check backup exists
        backup_path = tmp_path.with_suffix(tmp_path.suffix + '.backup')
        assert backup_path.exists()
        
        # Clean up backup
        backup_path.unlink()
        
    finally:
        tmp_path.unlink()
    
    print("✓ File processing tests passed")


def test_directory_processing():
    """Test directory processing functionality."""
    print("Testing directory processing...")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Create test files
        (tmp_path / "file1.py").write_text("import os\nimport sys\ndef main(): return os.getcwd()")
        (tmp_path / "file2.py").write_text("import json\nimport re\ndef process(): return json.dumps({})")
        (tmp_path / "not_python.txt").write_text("Not Python")
        
        checker = ImportChecker(check_mode=True)
        checker.run(tmp_path)
        
        assert checker.processed_files == 2  # Only Python files
        assert checker.total_issues > 0  # Should find unused imports
    
    print("✓ Directory processing tests passed")


def test_error_handling():
    """Test error handling."""
    print("Testing error handling...")
    
    checker = ImportChecker()
    
    # Test non-existent file
    try:
        checker.process_file(Path("/nonexistent/file.py"))
        assert False, "Should have raised ImportCheckerError"
    except ImportCheckerError as e:
        assert "File not found" in str(e)
    
    # Test syntax error file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
        tmp.write("""import os
def main(
    # Missing closing parenthesis
    return os.getcwd()
""")
        tmp.flush()
        tmp_path = Path(tmp.name)
    
    try:
        try:
            checker.process_file(tmp_path)
            assert False, "Should have raised ImportCheckerError"
        except ImportCheckerError as e:
            assert "Syntax error" in str(e)
    finally:
        tmp_path.unlink()
    
    print("✓ Error handling tests passed")


def main():
    """Run all tests."""
    print("Python Library Checker - Simple Test Suite")
    print("=" * 50)
    
    tests = [
        test_import_info_basic,
        test_extract_imports,
        test_extract_references,
        test_analyze_imports,
        test_remove_unused_imports,
        test_file_processing,
        test_directory_processing,
        test_error_handling
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
        print()
    
    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())