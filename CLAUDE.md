# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python Library Checker - A tool to analyze Python files for unused imports and optionally clean them up.

**Core functionality:**
1. **Check mode**: Analyze imports without making changes
2. **Cleanup mode**: Remove unused imports from files

## Architecture

**Simple single-module structure:**
- `src/checker.py` - Main implementation (currently empty, needs to be built)
- Entry point should accept command-line arguments for check-only vs cleanup modes

## Development Commands

**Running the tool:**
```bash
# Check mode (read-only analysis)
python src/checker.py --check <file_or_directory>

# Cleanup mode (removes unused imports)  
python src/checker.py --cleanup <file_or_directory>
```

**Testing:**
```bash
# Run on the checker itself
python src/checker.py --check src/checker.py
```

## Implementation Notes

**Core logic needed:**
- Parse Python files using `ast` module to identify imports
- Track actual usage of imported names throughout the file
- Differentiate between direct imports (`import module`) and from-imports (`from module import name`)
- Handle edge cases like star imports (`from module import *`)

**Command-line interface:**
- Use `argparse` for argument parsing
- Support both file and directory inputs
- Provide clear output showing unused imports found