# Python Library Checker

[![CI](https://github.com/yourusername/python-library-checker/workflows/CI/badge.svg)](https://github.com/yourusername/python-library-checker/actions/workflows/ci.yml)
[![Release](https://github.com/yourusername/python-library-checker/workflows/Release/badge.svg)](https://github.com/yourusername/python-library-checker/actions/workflows/release.yml)
[![Security](https://github.com/yourusername/python-library-checker/workflows/Security/badge.svg)](https://github.com/yourusername/python-library-checker/actions/workflows/security.yml)
[![codecov](https://codecov.io/gh/yourusername/python-library-checker/branch/main/graph/badge.svg)](https://codecov.io/gh/yourusername/python-library-checker)
[![PyPI version](https://badge.fury.io/py/python-library-checker.svg)](https://badge.fury.io/py/python-library-checker)
[![Python versions](https://img.shields.io/pypi/pyversions/python-library-checker.svg)](https://pypi.org/project/python-library-checker/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A powerful command-line tool to analyze and clean up unused imports in Python files. Keep your Python code clean and efficient by automatically detecting and removing unnecessary imports.

## Features

- **Check Mode**: Analyze imports without making any changes to your files
- **Cleanup Mode**: Automatically remove unused imports with backup creation
- **Smart Analysis**: Uses AST parsing for accurate import detection
- **Partial Import Handling**: Handles complex `from module import a, b, c` statements intelligently
- **Recursive Directory Processing**: Process entire directory trees or single files
- **Backup Safety**: Creates `.backup` files before making any modifications
- **Verbose Output**: Detailed logging for troubleshooting and verification
- **Cross-platform**: Works on Windows, macOS, and Linux

## Installation

### Prerequisites

- Python 3.7 or higher
- No external dependencies required (uses only Python standard library)

### Quick Start

1. Clone the repository:
```bash
git clone https://github.com/yourusername/PythonLibraryChecker.git
cd PythonLibraryChecker
```

2. Run the tool directly:
```bash
python src/checker.py --check your_file.py
```

### System Installation (Optional)

To use the tool from anywhere on your system:

```bash
# Make the script executable
chmod +x src/checker.py

# Add to your PATH or create a symlink
ln -s $(pwd)/src/checker.py /usr/local/bin/python-import-checker
```

## Usage

### Command-Line Interface

```bash
python src/checker.py [--check | --cleanup] target [options]
```

### Required Arguments

- `target`: Path to Python file or directory to process
- Mode (one required):
  - `--check`: Perform read-only analysis (no changes made)
  - `--cleanup`: Remove unused imports (modifies files)

### Optional Arguments

- `--recursive`: Process directories recursively (default: True)
- `--no-recursive`: Process only the specified directory level
- `--verbose`, `-v`: Enable detailed output
- `--version`: Show version information
- `--help`: Display help message

## Examples

### Basic Usage

**Analyze a single file:**
```bash
python src/checker.py --check myfile.py
```

**Clean up a single file:**
```bash
python src/checker.py --cleanup myfile.py
```

### Directory Processing

**Analyze entire project recursively:**
```bash
python src/checker.py --check ./src/
```

**Clean up directory non-recursively:**
```bash
python src/checker.py --cleanup --no-recursive ./src/
```

### Verbose Output

**Get detailed analysis information:**
```bash
python src/checker.py --check --verbose ./src/
```

## Sample Output

### Check Mode Example

```bash
$ python src/checker.py --check example.py
Analyzing: example.py
  Found 2 unused import(s):
    Line 1: import os
    Line 3: from datetime import datetime, timedelta

Analysis complete:
  Files processed: 1
  Issues found: 2
```

### Cleanup Mode Example

```bash
$ python src/checker.py --cleanup example.py
Cleaning: example.py
  Removing 2 unused import(s)
  Removed imports:
    Line 1: import os
    Line 3: from datetime import datetime
  Backup saved as: example.py.backup

Cleanup complete:
  Files processed: 1
  Issues found: 2
```

### Verbose Output Example

```bash
$ python src/checker.py --check --verbose example.py
Running in check mode on: example.py
Recursive: True
[VERBOSE] Processing file: example.py
[VERBOSE] Found 5 imports and 3 name references
Analyzing: example.py
  Found 2 unused import(s):
    Line 1: import os
    Line 3: from datetime import datetime
  Used imports: 3
    Line 2: import sys
    Line 4: from pathlib import Path
    Line 5: from typing import List

Analysis complete:
  Files processed: 1
  Issues found: 2
```

## How It Works

The tool uses Python's built-in AST (Abstract Syntax Tree) module to:

1. **Parse Python files** safely without executing code
2. **Extract all import statements** with their line numbers and details
3. **Identify name references** throughout the code
4. **Match imports to usage** using sophisticated analysis
5. **Handle complex cases** like aliases, attribute access, and partial imports
6. **Preserve code formatting** when making modifications

### Smart Import Analysis

- **Module imports**: `import module` - checks for `module.attribute` usage
- **From imports**: `from module import name` - tracks individual name usage
- **Aliased imports**: `import module as alias` - follows alias references
- **Multi-name imports**: `from module import a, b, c` - removes only unused names
- **Attribute access**: Detects `module.function()` patterns

## Requirements and Compatibility

### Python Version Support

- **Python 3.7+**: Full support
- **Python 3.6**: May work but not officially supported
- **Python 2.x**: Not supported

### File Support

- `.py` files: Full support
- `.pyw` files: Full support (Windows Python scripts)
- Other files: Automatically skipped

### Encoding Support

- UTF-8 (preferred)
- Latin-1 (fallback)

## Safety Features

### Backup Creation

When using `--cleanup` mode, the tool automatically creates backup files:
- Original: `myfile.py`
- Backup: `myfile.py.backup`

### Non-Destructive Analysis

The `--check` mode never modifies files, making it safe to run on any codebase.

### Error Handling

- Syntax errors in Python files are reported but don't crash the tool
- Permission errors are handled gracefully
- Invalid file paths are validated before processing

## Contributing

We welcome contributions from developers of all skill levels! Please see our [CONTRIBUTING.md](CONTRIBUTING.md) for comprehensive development guidelines.

### Quick Start for Contributors

1. **Development Setup**: Clone the repository and set up your environment:
```bash
git clone https://github.com/yourusername/PythonLibraryChecker.git
cd PythonLibraryChecker
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

2. **Code Quality Tools**: Ensure you have the required tools:
```bash
black src/ tests/          # Code formatting
flake8 src/ tests/         # Linting
mypy src/                  # Type checking
pytest tests/              # Testing
```

3. **Testing Your Changes**:
```bash
# Test on various scenarios
python src/checker.py --check tests/ --verbose
python src/checker.py --cleanup tests/test_basic_unused.py
```

### How to Contribute

- **🐛 Found a bug?** Use our [Bug Report Template](.github/ISSUE_TEMPLATE/bug_report.yml)
- **💡 Have a feature idea?** Use our [Feature Request Template](.github/ISSUE_TEMPLATE/feature_request.yml)
- **🔧 Ready to code?** Check our [Pull Request Template](.github/PULL_REQUEST_TEMPLATE.md)

### Code Standards

- **Python 3.7+** compatibility required
- **Type hints** for all function signatures
- **Black formatting** with 120-character line length
- **Comprehensive tests** for new functionality
- **Clear documentation** and docstrings

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed technical requirements, testing procedures, and development workflows.

## Troubleshooting

### Common Issues

**"Syntax error in file"**
- The target file has Python syntax errors
- Fix the syntax errors before running the tool

**"Permission denied"**
- Insufficient permissions to read/write files
- Check file permissions or run with appropriate privileges

**"No Python files found"**
- No `.py` or `.pyw` files in the target directory
- Verify the directory contains Python files

### Getting Help

1. Use `--verbose` mode for detailed output
2. Check that your Python files have correct syntax
3. Verify file permissions and paths
4. Open an issue on GitHub with example files and error messages

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Changelog

### Version 1.0.0
- Initial release
- Support for check and cleanup modes
- Recursive directory processing
- Smart import analysis with AST parsing
- Backup file creation
- Verbose output mode
- Cross-platform compatibility

---

**Made with ❤️ for the Python community**
