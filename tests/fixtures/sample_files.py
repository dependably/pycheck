"""Sample Python code snippets for testing."""

# Sample code with various import scenarios

BASIC_UNUSED_IMPORTS = '''#!/usr/bin/env python3
import os  # Used
import sys  # Unused
import json  # Unused

def main():
    current_dir = os.getcwd()
    return current_dir
'''

ALL_USED_IMPORTS = '''#!/usr/bin/env python3
import os
import sys
import json

def main():
    current_dir = os.getcwd()
    python_version = sys.version
    data = {"key": "value"}
    json_str = json.dumps(data)
    return current_dir, python_version, json_str
'''

FROM_IMPORTS_MIXED = '''#!/usr/bin/env python3
from os import getcwd, getenv  # getcwd used, getenv unused
from pathlib import Path, PurePath  # Path used, PurePath unused
from typing import Dict, List, Set  # Dict and List used, Set unused

def process():
    current_dir = getcwd()
    path_obj = Path(current_dir)
    data: Dict[str, List[str]] = {"items": ["a", "b"]}
    return path_obj, data
'''

ALIASED_IMPORTS = '''#!/usr/bin/env python3
import numpy as np  # Used
import pandas as pd  # Unused
from datetime import datetime as dt, timedelta as td  # dt used, td unused

def create_array():
    arr = np.array([1, 2, 3])
    now = dt.now()
    return arr, now
'''

STAR_IMPORTS = '''#!/usr/bin/env python3
from math import *  # Star import - should be preserved

def calculate():
    result = sin(pi / 2)
    return result
'''

MULTILINE_IMPORTS = '''#!/usr/bin/env python3
from collections import (
    Counter,  # Used
    defaultdict,  # Unused
    deque,  # Unused
    OrderedDict  # Used
)

def process_data():
    counter = Counter([1, 2, 2, 3])
    ordered = OrderedDict([('a', 1), ('b', 2)])
    return counter, ordered
'''

NO_IMPORTS = '''#!/usr/bin/env python3
"""File with no imports."""

def main():
    return "Hello, World!"
'''

ALL_UNUSED_IMPORTS = '''#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path
from typing import Dict, List

def main():
    return "No imports used"
'''

COMPLEX_USAGE = '''#!/usr/bin/env python3
import os  # Used in attribute access
import sys  # Used
from pathlib import Path as PathClass  # Used with alias
from typing import Optional  # Used in annotation

class DataProcessor:
    def __init__(self, path: Optional[PathClass] = None):
        self.base_path = path or PathClass.cwd()
        self.file_size = 0
    
    def process_file(self, filename: str):
        file_path = self.base_path / filename
        if file_path.exists():
            self.file_size = os.path.getsize(file_path)
            sys.stdout.write(f"Processing {filename}\\n")
        return self.file_size
'''

RELATIVE_IMPORTS = '''#!/usr/bin/env python3
from . import helper  # Relative import - used
from ..utils import formatter  # Relative import - unused

def main():
    result = helper.process_data()
    return result
'''

SYNTAX_ERROR_CODE = '''#!/usr/bin/env python3
import os
import sys

def main(
    # Missing closing parenthesis - syntax error
    return "error"
'''