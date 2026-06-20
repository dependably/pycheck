# Contributing to Python Library Checker

Thank you for your interest in contributing to Python Library Checker! We welcome contributions from developers of all skill levels. This guide will help you get started.

## Code of Conduct

This project follows the [Contributor Covenant](https://www.contributor-covenant.org/). By participating, you are expected to be respectful and constructive.

## How to Contribute

### Reporting Issues

Before creating an issue, please:

1. **Search existing issues** to avoid duplicates
2. **Use the latest version** to ensure the issue hasn't been fixed
3. **Provide clear reproduction steps** with example files when possible

[Open an issue](https://gitlab.northwardlabs.ca/dependably/python-check/-/issues) on GitLab — describe bugs with reproduction steps and example files, and feature requests with the use case.

### Development Setup

#### Prerequisites

- Python 3.9 or higher
- Git
- Basic familiarity with Python AST and import analysis (helpful but not required)

#### Getting Started

1. **Fork and clone the repository:**
   ```bash
   git clone https://gitlab.northwardlabs.ca/dependably/python-check.git
   cd python-check
   ```

2. **Create a virtual environment (recommended):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install development dependencies** (from the private Dependably registry):
   ```bash
   # One-time: add your registry token to ~/.netrc (chmod 600)
   #   machine dependably.northwardlabs.ca
   #     login ci
   #     password <your REGISTRY_KEY token>
   make install        # uses ./pip.conf -> https://dependably.northwardlabs.ca/simple/
   ```
   (`make install` is `PIP_CONFIG_FILE=./pip.conf pip install -e ".[dev]"`.)

4. **Verify the setup:**
   ```bash
   python src/checker.py --check src/checker.py
   ```

#### Development Tools

We use several tools to maintain code quality:

- **Black**: Code formatting (`black src/ tests/`)
- **Flake8**: Linting (`flake8 src/ tests/`)
- **MyPy**: Type checking (`mypy src/`)
- **Pytest**: Testing (`pytest tests/`)

Install the repo's git hooks (recommended):
```bash
make install-hooks            # or: ./scripts/install-hooks.sh
```
This points git's `core.hooksPath` at the tracked `.githooks/` directory. On
each commit the hook dogfoods the config validators (`checker.py --validate .`),
runs `black --check` and `flake8`, and a fast unit-test subset.

### Code Style Requirements

#### Python Code Standards

- **Follow PEP 8** with 120-character line length
- **Use type hints** for all function signatures
- **Add docstrings** for public functions and classes
- **Use descriptive variable names** (e.g., `unused_imports` not `ui`)
- **Keep functions focused** - single responsibility principle

#### Code Formatting

Run before committing:
```bash
# Format code
black src/ tests/

# Check linting
flake8 src/ tests/

# Type checking
mypy src/

# Run tests
pytest tests/
```

#### Example Code Style

```python
from typing import List, Dict, Optional
import ast


def find_unused_imports(file_path: str, verbose: bool = False) -> List[str]:
    """Find unused imports in a Python file.
    
    Args:
        file_path: Path to the Python file to analyze
        verbose: Whether to enable verbose output
        
    Returns:
        List of unused import statements
        
    Raises:
        FileNotFoundError: If the file doesn't exist
        SyntaxError: If the file has invalid Python syntax
    """
    unused_imports: List[str] = []
    # Implementation here...
    return unused_imports
```

### Testing Requirements

#### Test Structure

- **Unit tests**: Focus on individual functions
- **Integration tests**: Test complete workflows
- **Test files**: Use the existing test files in `tests/` directory

#### Writing Tests

1. **Create test files** for new functionality:
   ```python
   # tests/test_new_feature.py
   import unittest
   from src.checker import your_function
   
   class TestNewFeature(unittest.TestCase):
       def test_basic_functionality(self):
           result = your_function("test_input")
           self.assertEqual(result, expected_output)
   ```

2. **Test with existing test files:**
   ```bash
   # Test your changes against known good/bad sample files
   python src/checker.py --check tests/fixtures/test_basic_unused.py
   ```

#### Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src/

# Run specific test
pytest tests/test_specific.py

# Verbose output
pytest tests/ -v
```

### Pull Request Process

#### Before Submitting

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make focused commits:**
   - One logical change per commit
   - Clear, descriptive commit messages
   - Use imperative mood: "Add feature" not "Added feature"

3. **Test thoroughly:**
   ```bash
   # Run the full test suite
   python src/checker.py --check tests/ --verbose
   black src/ tests/
   flake8 src/ tests/
   mypy src/
   pytest tests/
   ```

4. **Update documentation** if needed

#### Submitting Your PR

1. **Push your branch:**
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create a merge request** on GitLab against `main`

3. **Describe your change completely:**
   - Clear description of changes
   - Link to related issues
   - Testing instructions

#### PR Review Process

- **Automated checks** must pass (formatting, linting, tests)
- **Code review** by maintainers
- **Testing** on various Python versions and file types
- **Documentation** updates if needed

We aim to review PRs within 48 hours and provide constructive feedback.

## Development Guidelines

### Understanding the Codebase

The tool's core logic involves:

1. **AST Parsing**: Using `ast.parse()` to analyze Python files
2. **Import Detection**: Finding all import statements and their line numbers
3. **Usage Analysis**: Tracking how imported names are used
4. **Smart Cleanup**: Removing only truly unused imports

Key files:
- `src/checker.py`: Main implementation
- `tests/`: Various test cases for different scenarios

### Common Contribution Areas

#### Easy (Good First Issues)
- Improve error messages
- Add command-line options
- Enhance documentation
- Add test cases

#### Medium
- Improve import usage detection
- Handle edge cases (decorators, type hints)
- Performance optimizations
- Better handling of complex imports

#### Advanced
- Support for configuration files
- Integration with other tools
- Advanced AST analysis features
- Plugin architecture

### Testing Your Changes

Always test with:

1. **The provided test files** in `tests/`
2. **Your own Python projects** (with backups!)
3. **Edge cases**: Complex imports, syntax errors, empty files
4. **Both modes**: `--check` and `--cleanup`

Example testing workflow:
```bash
# Test on various file types
python src/checker.py --check tests/ --verbose
python src/checker.py --check your_project/ --verbose

# Test cleanup (creates backups)
cp tests/fixtures/test_basic_unused.py temp_test.py
python src/checker.py --cleanup temp_test.py
# Verify the changes are correct
```

## Release Process

### Version Numbering

We follow [semantic versioning](https://semver.org/):
- **Major** (1.0.0): Breaking changes
- **Minor** (1.1.0): New features, backward compatible
- **Patch** (1.0.1): Bug fixes

### Release Checklist

1. Update version in `pyproject.toml`
2. Update changelog in `README.md`
3. Run full test suite
4. Create release tag
5. Update documentation

## Getting Help

### Communication Channels

- **GitLab Issues**: Bug reports and feature requests
- **Merge Request Comments**: Code-specific discussions

### Documentation

- **README.md**: User documentation and examples
- **CLAUDE.md**: Development context and architecture
- **Code comments**: Implementation details

### Questions?

Don't hesitate to ask questions! We're here to help:

1. **Check existing issues** for similar questions
2. **Create an issue** for general questions or specific problems
3. **Comment on merge requests** for code-related questions

## Recognition

Contributors are recognized in several ways:

- **GitLab contributors page**
- **Release notes** for significant contributions
- **Issue/MR acknowledgments**

Thank you for contributing to Python Library Checker! 🐍✨