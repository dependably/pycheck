#!/usr/bin/env python3
"""
Test file with basic unused imports.
This file contains various unused imports that should be detected and removed.
"""

import os  # Used
import re  # Used
from typing import List  # Only List is used, Dict and Set are unused


def process_data():
    """Function that uses some imports but not others."""
    current_dir = os.getcwd()
    pattern = re.compile(r'\d+')
    
    data: List[str] = ["item1", "item2", "item3"]
    
    return data, current_dir, pattern

if __name__ == "__main__":
    result = process_data()
    print(f"Result: {result}")