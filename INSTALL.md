# Installation Guide

## Installation Methods

### 1. Install from Source (Development)

```bash
# Clone the repository
git clone <repository-url>
cd PythonLibraryChecker

# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e .

# Or install development dependencies
pip install -r requirements-dev.txt
```

### 2. Install from Distribution Package

```bash
# Install from wheel file
pip install dist/python_library_checker-1.0.0-py3-none-any.whl

# Or install from source distribution
pip install dist/python_library_checker-1.0.0.tar.gz
```

### 3. Build and Install

```bash
# Install build dependencies
pip install build

# Build the package
python -m build

# Install the built package
pip install dist/python_library_checker-1.0.0-py3-none-any.whl
```

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

- Python 3.7 or higher
- No external dependencies (uses only Python standard library)

## Development Dependencies (Optional)

- pytest >= 6.0.0
- black >= 22.0.0
- flake8 >= 4.0.0
- mypy >= 0.900