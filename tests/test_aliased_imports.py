#!/usr/bin/env python3
"""
Test file with aliased imports.
This file tests various aliasing scenarios including used and unused aliases.
"""

import numpy as np  # Used alias
from pathlib import Path as PathAlias  # Used alias
from datetime import datetime as dt  # dt used, td unused


def create_array():
    """Function using numpy with alias."""
    arr = np.array([1, 2, 3, 4, 5])
    return arr

def get_current_time():
    """Function using datetime with alias."""
    now = dt.now()
    return now

def process_path():
    """Function using Path with alias."""
    current_path = PathAlias.cwd()
    return current_path

if __name__ == "__main__":
    array = create_array()
    time = get_current_time()
    path = process_path()
    print(f"Array: {array}, Time: {time}, Path: {path}")