# Installation Guide

## Installation Methods

### 1. Install from Source (Development)

```bash
# Clone the repository
git clone https://gitlab.northwardlabs.ca/dependably/pycheck.git
cd pycheck

# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e .

# Or install development dependencies
pip install -r requirements-dev.txt
```

### 2. Build and Install a Distribution Package

The distribution is `Dependably.pycheck` (current version `1.2.0`). Build the
wheel and source distribution locally, then install the built artifact:

```bash
# Install the build front-end (one time)
pip install build

# Build the wheel + sdist into dist/
python -m build

# Install the freshly built wheel
pip install dist/dependably_pycheck-1.2.0-py3-none-any.whl

# Or install the source distribution
pip install dist/dependably_pycheck-1.2.0.tar.gz
```

`python -m build` normalizes the project name (`Dependably.pycheck`) to
`dependably_pycheck` in the artifact filenames, so the produced files are
`dependably_pycheck-1.2.0-py3-none-any.whl` and `dependably_pycheck-1.2.0.tar.gz`.
The editable install in method 1 (`pip install -e .`) avoids the filename
entirely and is the simplest path for development.

### 3. Install from PyPI (once published)

`Dependably.pycheck` is **not yet published to PyPI**. Once it is released, it
will install with:

```bash
pip install Dependably.pycheck
```

Until then, use the from-source (method 1) or build-and-install (method 2)
instructions above.

## Usage

After installation, the tool provides two command-line entry points:

### Command Line Usage

```bash
# Primary command
python-import-checker --check src/
python-import-checker --cleanup myfile.py

# Alternative command
import-checker --check src/
import-checker --cleanup myfile.py --verbose
```

### Python Module Usage

```python
from src import ImportChecker, ImportCheckerError

# Create checker instance
checker = ImportChecker(check_mode=True, verbose=True)

# Process a file or directory
from pathlib import Path
checker.run(Path("myfile.py"))
```

## Requirements

- Python 3.9 or higher
- No external dependencies (uses only Python standard library)

## Development Dependencies (Optional)

- pytest >= 6.0.0
- black >= 22.0.0
- flake8 >= 4.0.0
- mypy >= 0.900