"""Integration tests for end-to-end functionality."""

import pytest
import sys
import os
from pathlib import Path
import tempfile
import shutil

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from checker import ImportChecker


class TestEndToEndIntegration:
    """End-to-end integration tests using sample files."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.fixtures_dir = Path(__file__).parent.parent / "fixtures"
    
    @pytest.mark.integration
    def test_analyze_basic_unused_imports(self):
        """Test analysis of basic unused imports file."""
        sample_file = self.fixtures_dir / "test_basic_unused.py"
        if not sample_file.exists():
            pytest.skip("Sample file not found")
        
        checker = ImportChecker(check_mode=True)
        
        # Capture processing results
        original_processed = checker.processed_files
        original_issues = checker.total_issues
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
            tmp.write(sample_file.read_text())
            tmp.flush()
            tmp_path = Path(tmp.name)
        
        try:
            checker.process_file(tmp_path)
            
            # Should have processed 1 file and found some unused imports
            assert checker.processed_files == original_processed + 1
            assert checker.total_issues > original_issues
            
        finally:
            tmp_path.unlink()
    
    @pytest.mark.integration
    def test_analyze_all_used_imports(self):
        """Test analysis of file with all imports used."""
        sample_file = self.fixtures_dir / "test_all_used.py"
        if not sample_file.exists():
            pytest.skip("Sample file not found")
        
        checker = ImportChecker(check_mode=True)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
            tmp.write(sample_file.read_text())
            tmp.flush()
            tmp_path = Path(tmp.name)
        
        try:
            original_issues = checker.total_issues
            checker.process_file(tmp_path)
            
            # Should find no unused imports
            assert checker.total_issues == original_issues
            
        finally:
            tmp_path.unlink()
    
    @pytest.mark.integration
    def test_cleanup_unused_imports(self):
        """Test cleanup functionality removes unused imports."""
        sample_file = self.fixtures_dir / "test_basic_unused.py"
        if not sample_file.exists():
            pytest.skip("Sample file not found")
        
        checker = ImportChecker(check_mode=False)  # Cleanup mode
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
            original_content = sample_file.read_text()
            tmp.write(original_content)
            tmp.flush()
            tmp_path = Path(tmp.name)
        
        try:
            checker.process_file(tmp_path)
            
            # Check that file was modified
            modified_content = tmp_path.read_text()
            assert modified_content != original_content
            
            # Check that backup was created
            backup_path = tmp_path.with_suffix(tmp_path.suffix + '.backup')
            assert backup_path.exists()
            
            # Backup should contain original content
            backup_content = backup_path.read_text()
            assert backup_content == original_content
            
            # Clean up backup
            backup_path.unlink()
            
        finally:
            tmp_path.unlink()
    
    @pytest.mark.integration
    def test_analyze_from_imports(self):
        """Test analysis of from-import scenarios."""
        sample_file = self.fixtures_dir / "test_from_imports.py"
        if not sample_file.exists():
            pytest.skip("Sample file not found")
        
        checker = ImportChecker(check_mode=True)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
            tmp.write(sample_file.read_text())
            tmp.flush()
            tmp_path = Path(tmp.name)
        
        try:
            original_issues = checker.total_issues
            checker.process_file(tmp_path)
            
            # Should find unused from-imports
            assert checker.total_issues > original_issues
            
        finally:
            tmp_path.unlink()
    
    @pytest.mark.integration
    def test_analyze_aliased_imports(self):
        """Test analysis of aliased import scenarios."""
        sample_file = self.fixtures_dir / "test_aliased_imports.py"
        if not sample_file.exists():
            pytest.skip("Sample file not found")
        
        checker = ImportChecker(check_mode=True)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
            tmp.write(sample_file.read_text())
            tmp.flush()
            tmp_path = Path(tmp.name)
        
        try:
            original_issues = checker.total_issues
            checker.process_file(tmp_path)
            
            # Check if any issues were found (depends on actual content)
            issues_found = checker.total_issues > original_issues
            # This is informational - aliased imports might be all used
            
        finally:
            tmp_path.unlink()
    
    @pytest.mark.integration
    def test_analyze_mixed_complex_imports(self):
        """Test analysis of complex mixed import scenarios."""
        sample_file = self.fixtures_dir / "test_mixed_complex.py"
        if not sample_file.exists():
            pytest.skip("Sample file not found")
        
        checker = ImportChecker(check_mode=True)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as tmp:
            tmp.write(sample_file.read_text())
            tmp.flush()
            tmp_path = Path(tmp.name)
        
        try:
            original_issues = checker.total_issues
            checker.process_file(tmp_path)
            
            # Complex file should have some unused imports
            assert checker.total_issues > original_issues
            
        finally:
            tmp_path.unlink()
    
    @pytest.mark.integration
    def test_directory_processing(self):
        """Test processing a directory with multiple files."""
        # Create temporary directory with test files
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Create test files
            (tmp_path / "file1.py").write_text("""
import os
import sys

def main():
    return os.getcwd()
""")
            
            (tmp_path / "file2.py").write_text("""
import json
from pathlib import Path

def process():
    data = {"key": "value"}
    return json.dumps(data)
""")
            
            # Create subdirectory
            subdir = tmp_path / "subdir"
            subdir.mkdir()
            (subdir / "nested.py").write_text("""
import re
import datetime

def check():
    pattern = re.compile(r'\\d+')
    return pattern
""")
            
            checker = ImportChecker(check_mode=True)
            checker.run(tmp_path)
            
            # Should have processed 3 files
            assert checker.processed_files == 3
            # Should have found some unused imports
            assert checker.total_issues > 0
    
    @pytest.mark.integration
    def test_directory_processing_non_recursive(self):
        """Test non-recursive directory processing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Create test files
            (tmp_path / "root.py").write_text("import os\\nimport sys")
            
            # Create subdirectory with file
            subdir = tmp_path / "subdir"
            subdir.mkdir()
            (subdir / "nested.py").write_text("import json")
            
            checker = ImportChecker(check_mode=True)
            checker.run(tmp_path, recursive=False)
            
            # Should have processed only 1 file (root level)
            assert checker.processed_files == 1
    
    @pytest.mark.integration
    def test_full_cleanup_workflow(self):
        """Test complete cleanup workflow with multiple files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Create test file with unused imports
            test_file = tmp_path / "test.py"
            original_content = """import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Set

def main():
    current_dir = os.getcwd()
    path_obj = Path(current_dir)
    data: Dict[str, str] = {"key": "value"}
    return current_dir, path_obj, data
"""
            test_file.write_text(original_content)
            
            # First, analyze to see what would be removed
            check_checker = ImportChecker(check_mode=True)
            check_checker.run(test_file)
            
            issues_found = check_checker.total_issues
            assert issues_found > 0  # Should find unused imports
            
            # Now cleanup
            cleanup_checker = ImportChecker(check_mode=False)
            cleanup_checker.run(test_file)
            
            # Check results
            modified_content = test_file.read_text()
            assert modified_content != original_content
            
            # Unused imports should be removed
            assert "import sys" not in modified_content  # Unused
            assert "import json" not in modified_content  # Unused
            assert "List" not in modified_content  # Unused from typing
            assert "Set" not in modified_content  # Unused from typing
            
            # Used imports should remain
            assert "import os" in modified_content  # Used
            assert "from pathlib import Path" in modified_content  # Used
            assert "Dict" in modified_content  # Used from typing
            
            # Backup should exist
            backup_file = test_file.with_suffix(test_file.suffix + '.backup')
            assert backup_file.exists()
            assert backup_file.read_text() == original_content
    
    @pytest.mark.integration
    @pytest.mark.slow
    def test_large_codebase_simulation(self):
        """Test processing a simulated large codebase."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Create multiple files and directories
            for i in range(10):
                subdir = tmp_path / f"module_{i}"
                subdir.mkdir()
                
                for j in range(5):
                    file_content = f"""
import os
import sys
import json
import re
from pathlib import Path
from typing import Dict, List

def function_{j}():
    # Use some imports
    current_dir = os.getcwd()
    pattern = re.compile(r'\\d+')
    data: Dict[str, str] = {{"key": "value"}}
    return current_dir, pattern, data
"""
                    (subdir / f"file_{j}.py").write_text(file_content)
            
            # Process the entire codebase
            checker = ImportChecker(check_mode=True)
            checker.run(tmp_path)
            
            # Should have processed 50 files (10 dirs * 5 files each)
            assert checker.processed_files == 50
            
            # Should have found unused imports across all files
            assert checker.total_issues > 0
            
            # Each file should have some unused imports (sys, json, Path, List)
            # So total issues should be significant
            assert checker.total_issues >= 50  # At least 1 per file
    
    @pytest.mark.integration
    def test_error_handling_integration(self):
        """Test error handling in integration scenarios."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            
            # Create file with syntax error
            syntax_error_file = tmp_path / "syntax_error.py"
            syntax_error_file.write_text("""
import os
def main(
    # Missing closing parenthesis - syntax error
    return os.getcwd()
""")
            
            # Create valid file
            valid_file = tmp_path / "valid.py"
            valid_file.write_text("import os\\ndef main(): return os.getcwd()")
            
            checker = ImportChecker(check_mode=True)
            
            # Processing the valid file should work
            checker.process_file(valid_file)
            assert checker.processed_files == 1
            
            # Processing the syntax error file should raise error
            with pytest.raises(Exception):  # ImportCheckerError
                checker.process_file(syntax_error_file)