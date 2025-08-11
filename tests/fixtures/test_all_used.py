#!/usr/bin/env python3
"""
Test file where all imports are used.
This file should have no unused imports detected.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List

def use_all_imports():
    """Function that uses all imported modules and types."""
    # Use os
    current_dir = os.getcwd()
    
    # Use sys
    python_version = sys.version
    
    # Use json
    data = {"key": "value"}
    json_string = json.dumps(data)
    
    # Use pathlib
    path_obj = Path(current_dir)
    
    # Use typing annotations
    result: Dict[str, List[str]] = {
        "directory": [current_dir],
        "version": [python_version],
        "json": [json_string],
        "path": [str(path_obj)]
    }
    
    return result

if __name__ == "__main__":
    result = use_all_imports()
    print(f"All imports used: {result}")