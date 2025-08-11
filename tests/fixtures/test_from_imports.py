#!/usr/bin/env python3
"""
Test file with various from-import scenarios.
This tests multi-name from imports with some used and some unused items.
"""

from os import getcwd  # getcwd used, getenv and listdir unused

from pathlib import Path  # Only Path used

from typing import Dict, List  # Dict and List used, others unused

from collections import Counter  # Only Counter used


def analyze_directory():
    """Function using some of the imported items."""
    current_dir = getcwd()
    path_obj = Path(current_dir)
    
    files: Dict[str, List[str]] = {}
    file_counts = Counter()
    
    return files, file_counts, path_obj

if __name__ == "__main__":
    result = analyze_directory()
    print(f"Analysis result: {result}")