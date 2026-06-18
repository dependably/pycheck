#!/usr/bin/env python3
"""
Test file with various from-import scenarios.
This tests multi-name from imports with some used and some unused items.
"""

from os import getcwd, getenv, listdir  # getcwd used, getenv and listdir unused

from pathlib import Path, PurePath  # Only Path used, PurePath unused

from typing import Dict, List, Set, Tuple  # Dict and List used, Set and Tuple unused

from collections import Counter, defaultdict, OrderedDict  # Only Counter used


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