#!/usr/bin/env python3
"""
Complex test file with mixed import scenarios.
Tests various combinations of used/unused imports with different styles.
"""

# Standard library imports
import os  # Used
import sys  # Unused
import json as js  # Used with alias
import re as regex  # Unused with alias

# From imports with mixed usage
from pathlib import Path, PurePath  # Path used, PurePath unused
from typing import Dict, List, Set, Optional  # Dict and Optional used, List and Set unused
from collections import Counter, defaultdict, deque  # Only defaultdict used

# Multiple line from import (to test complex parsing)
from datetime import (
    datetime,  # Used
    timedelta,  # Unused
    date,  # Unused
    time  # Used
)

class DataProcessor:
    """Class that uses some but not all imports."""
    
    def __init__(self):
        self.data: Dict[str, Optional[str]] = defaultdict(lambda: None)
        self.current_path = Path.cwd()
        
    def process_json_file(self, filename: str):
        """Process a JSON file using various imports."""
        file_path = self.current_path / filename
        
        if file_path.exists():
            with open(file_path) as f:
                content = js.load(f)
            
            # Use datetime and time
            now = datetime.now()
            current_time = time(now.hour, now.minute, now.second)
            
            result = {
                "content": content,
                "processed_at": str(current_time),
                "file_size": os.path.getsize(file_path)
            }
            
            return result
        
        return None

if __name__ == "__main__":
    processor = DataProcessor()
    # This would use the processor if we had a test file
    print("DataProcessor initialized successfully")