"""
Python Library Checker

A tool to analyze Python files for unused imports and optionally clean them up.
"""

from .checker import ImportChecker, ImportCheckerError, ImportInfo, main

__version__ = "1.0.0"
__all__ = ["ImportChecker", "ImportCheckerError", "ImportInfo", "main"]