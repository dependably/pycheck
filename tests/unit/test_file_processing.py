"""Unit tests for file processing functionality and error handling."""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from checker import ImportChecker, ImportCheckerError


class TestFileProcessing:
    """Test cases for file processing functionality."""
    
    def setup_method(self):
        """Set up test instance."""
        self.checker = ImportChecker(check_mode=True)
    
    def test_process_file_basic_python_file(self, tmp_path):
        """Test processing a basic Python file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""import os
import sys

def main():
    return os.getcwd()
""")
        
        # Capture output
        with patch('builtins.print') as mock_print:
            self.checker.process_file(test_file)
        
        assert self.checker.processed_files == 1
        assert self.checker.total_issues == 1  # sys is unused
        
        # Check that analysis output was printed
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("Analyzing:" in call for call in print_calls)
        assert any("Found 1 unused import(s):" in call for call in print_calls)
    
    def test_process_file_no_unused_imports(self, tmp_path):
        """Test processing file with no unused imports."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""import os
import sys

def main():
    return os.getcwd(), sys.version
""")
        
        with patch('builtins.print') as mock_print:
            self.checker.process_file(test_file)
        
        assert self.checker.processed_files == 1
        assert self.checker.total_issues == 0
        
        # Check that no issues were reported
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("No unused imports found" in call for call in print_calls)
    
    def test_process_file_cleanup_mode(self, tmp_path):
        """Test processing file in cleanup mode."""
        self.checker = ImportChecker(check_mode=False)
        
        test_file = tmp_path / "test.py"
        content = """import os
import sys
import json

def main():
    return os.getcwd()
"""
        test_file.write_text(content)
        
        with patch('builtins.print') as mock_print:
            self.checker.process_file(test_file)
        
        # Check that backup was created
        backup_file = test_file.with_suffix(test_file.suffix + '.backup')
        assert backup_file.exists()
        
        # Check that unused imports were removed
        modified_content = test_file.read_text()
        assert "import sys" not in modified_content
        assert "import json" not in modified_content
        assert "import os" in modified_content  # Used import should remain
        
        # Check output messages
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("Cleaning:" in call for call in print_calls)
        assert any("Removing 2 unused import(s)" in call for call in print_calls)
    
    def test_process_file_nonexistent_file(self):
        """Test processing non-existent file."""
        nonexistent_file = Path("/nonexistent/file.py")
        
        with pytest.raises(ImportCheckerError) as excinfo:
            self.checker.process_file(nonexistent_file)
        
        assert "File not found" in str(excinfo.value)
    
    def test_process_file_not_a_file(self, tmp_path):
        """Test processing a directory instead of file."""
        with pytest.raises(ImportCheckerError) as excinfo:
            self.checker.process_file(tmp_path)
        
        assert "Path is not a file" in str(excinfo.value)
    
    def test_process_file_non_python_file(self, tmp_path):
        """Test processing non-Python file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("This is not Python code")
        
        with patch('builtins.print'):
            self.checker.process_file(test_file)
        
        # Should be skipped, so no files processed
        assert self.checker.processed_files == 0
    
    def test_process_file_pyw_extension(self, tmp_path):
        """Test processing .pyw file."""
        test_file = tmp_path / "test.pyw"
        test_file.write_text("""import os
import sys

def main():
    return os.getcwd()
""")
        
        with patch('builtins.print'):
            self.checker.process_file(test_file)
        
        # .pyw files should be processed
        assert self.checker.processed_files == 1
        assert self.checker.total_issues == 1
    
    def test_process_file_syntax_error(self, tmp_path):
        """Test processing file with syntax error."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""import os
def main(
    # Missing closing parenthesis
    return os.getcwd()
""")
        
        with pytest.raises(ImportCheckerError) as excinfo:
            self.checker.process_file(test_file)
        
        assert "Syntax error" in str(excinfo.value)
    
    def test_process_file_unicode_decode_error(self, tmp_path):
        """Test processing file with encoding issues."""
        test_file = tmp_path / "test.py"
        
        # Write binary data that will cause UnicodeDecodeError
        with open(test_file, 'wb') as f:
            f.write(b"import os\n# \xff\xfe invalid utf-8\ndef main(): pass")
        
        # Should fallback to latin-1 encoding and process successfully
        with patch('builtins.print'):
            self.checker.process_file(test_file)
        
        assert self.checker.processed_files == 1
    
    def test_process_file_permission_error(self, tmp_path):
        """Test processing file with permission error."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")
        
        # Mock permission error on file read
        with patch('builtins.open', side_effect=PermissionError("Access denied")):
            with pytest.raises(ImportCheckerError) as excinfo:
                self.checker.process_file(test_file)
        
        assert "Permission denied accessing file" in str(excinfo.value)
    
    def test_process_file_verbose_mode(self, tmp_path):
        """Test processing file in verbose mode."""
        self.checker = ImportChecker(check_mode=True, verbose=True)
        
        test_file = tmp_path / "test.py"
        test_file.write_text("""import os
import sys

def main():
    return os.getcwd()
""")
        
        with patch('builtins.print') as mock_print:
            self.checker.process_file(test_file)
        
        # Check verbose output
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("[VERBOSE] Processing file:" in call for call in print_calls)
        assert any("[VERBOSE] Found 2 imports and" in call for call in print_calls)
        assert any("Used imports: 1" in call for call in print_calls)


class TestDirectoryProcessing:
    """Test cases for directory processing functionality."""
    
    def setup_method(self):
        """Set up test instance."""
        self.checker = ImportChecker(check_mode=True)
    
    def test_process_directory_basic(self, tmp_path):
        """Test processing a directory with Python files."""
        # Create test files
        (tmp_path / "file1.py").write_text("import os\ndef main(): return os.getcwd()")
        (tmp_path / "file2.py").write_text("import sys\ndef main(): return sys.version")
        (tmp_path / "not_python.txt").write_text("Not Python")
        
        with patch('builtins.print'):
            self.checker.process_directory(tmp_path)
        
        assert self.checker.processed_files == 2  # Only Python files
    
    def test_process_directory_recursive(self, tmp_path):
        """Test recursive directory processing."""
        # Create nested structure
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        
        (tmp_path / "root.py").write_text("import os")
        (subdir / "nested.py").write_text("import sys")
        
        with patch('builtins.print'):
            self.checker.process_directory(tmp_path, recursive=True)
        
        assert self.checker.processed_files == 2
    
    def test_process_directory_non_recursive(self, tmp_path):
        """Test non-recursive directory processing."""
        # Create nested structure
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        
        (tmp_path / "root.py").write_text("import os")
        (subdir / "nested.py").write_text("import sys")
        
        with patch('builtins.print'):
            self.checker.process_directory(tmp_path, recursive=False)
        
        assert self.checker.processed_files == 1  # Only root level
    
    def test_process_directory_no_python_files(self, tmp_path):
        """Test processing directory with no Python files."""
        (tmp_path / "readme.txt").write_text("README")
        (tmp_path / "config.json").write_text('{"key": "value"}')
        
        with patch('builtins.print') as mock_print:
            self.checker.process_directory(tmp_path)
        
        assert self.checker.processed_files == 0
        
        # Check that message was printed
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("No Python files found" in call for call in print_calls)
    
    def test_process_directory_nonexistent(self):
        """Test processing non-existent directory."""
        nonexistent_dir = Path("/nonexistent/directory")
        
        with pytest.raises(ImportCheckerError) as excinfo:
            self.checker.process_directory(nonexistent_dir)
        
        assert "Directory not found" in str(excinfo.value)
    
    def test_process_directory_not_a_directory(self, tmp_path):
        """Test processing a file instead of directory."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")
        
        with pytest.raises(ImportCheckerError) as excinfo:
            self.checker.process_directory(test_file)
        
        assert "Path is not a directory" in str(excinfo.value)
    
    def test_process_directory_permission_error(self, tmp_path):
        """Test processing directory with permission error."""
        with patch.object(Path, 'glob', side_effect=PermissionError("Access denied")):
            with pytest.raises(ImportCheckerError) as excinfo:
                self.checker.process_directory(tmp_path)
        
        assert "Permission denied accessing directory" in str(excinfo.value)


class TestRunMethod:
    """Test cases for the run method."""
    
    def setup_method(self):
        """Set up test instance."""
        self.checker = ImportChecker(check_mode=True)
    
    def test_run_with_file(self, tmp_path):
        """Test run method with file target."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os\nimport sys\ndef main(): return os.getcwd()")
        
        with patch('builtins.print') as mock_print:
            self.checker.run(test_file)
        
        assert self.checker.processed_files == 1
        
        # Check summary output
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("Analysis complete:" in call for call in print_calls)
        assert any("Files processed: 1" in call for call in print_calls)
        assert any("Issues found: 1" in call for call in print_calls)
    
    def test_run_with_directory(self, tmp_path):
        """Test run method with directory target."""
        (tmp_path / "file1.py").write_text("import os")
        (tmp_path / "file2.py").write_text("import sys")
        
        with patch('builtins.print') as mock_print:
            self.checker.run(tmp_path)
        
        assert self.checker.processed_files == 2
        
        # Check summary output
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("Analysis complete:" in call for call in print_calls)
        assert any("Files processed: 2" in call for call in print_calls)
    
    def test_run_cleanup_mode_summary(self, tmp_path):
        """Test run method summary in cleanup mode."""
        self.checker = ImportChecker(check_mode=False)
        
        test_file = tmp_path / "test.py"
        test_file.write_text("import os\nimport sys\ndef main(): return os.getcwd()")
        
        with patch('builtins.print') as mock_print:
            self.checker.run(test_file)
        
        # Check cleanup summary
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        assert any("Cleanup complete:" in call for call in print_calls)
    
    def test_run_nonexistent_path(self):
        """Test run method with non-existent path."""
        nonexistent_path = Path("/nonexistent/path")
        
        with pytest.raises(ImportCheckerError) as excinfo:
            self.checker.run(nonexistent_path)
        
        assert "Target path does not exist" in str(excinfo.value)
    
    def test_run_with_relative_path(self, tmp_path):
        """Test run method resolves relative paths."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")
        
        # Change to parent directory
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path.parent)
            relative_path = Path(tmp_path.name) / "test.py"
            
            with patch('builtins.print'):
                self.checker.run(relative_path)
            
            assert self.checker.processed_files == 1
        finally:
            os.chdir(original_cwd)
    
    def test_run_with_symlink(self, tmp_path):
        """Test run method follows symlinks."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")
        
        symlink_file = tmp_path / "link.py"
        symlink_file.symlink_to(test_file)
        
        with patch('builtins.print'):
            self.checker.run(symlink_file)
        
        assert self.checker.processed_files == 1
    
    def test_run_propagates_import_checker_error(self, tmp_path):
        """Test run method propagates ImportCheckerError."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")
        
        # Mock process_file to raise ImportCheckerError
        with patch.object(self.checker, 'process_file', 
                         side_effect=ImportCheckerError("Test error")):
            with pytest.raises(ImportCheckerError) as excinfo:
                self.checker.run(test_file)
        
        assert "Test error" in str(excinfo.value)
    
    def test_run_handles_unexpected_error(self, tmp_path):
        """Test run method handles unexpected errors."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")
        
        # Mock process_file to raise unexpected error
        with patch.object(self.checker, 'process_file', 
                         side_effect=RuntimeError("Unexpected")):
            with pytest.raises(ImportCheckerError) as excinfo:
                self.checker.run(test_file)
        
        assert "Unexpected error during processing" in str(excinfo.value)