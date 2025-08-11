#!/usr/bin/env python3
"""
Simple test runner for the Python Library Checker tests.
This script runs the tests without requiring pytest to be installed.
"""

import sys
import os
import importlib.util
import traceback
from pathlib import Path


def load_module_from_path(file_path):
    """Load a Python module from a file path."""
    spec = importlib.util.spec_from_file_location("test_module", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_test_method(test_class, method_name, instance=None):
    """Run a single test method."""
    if instance is None:
        instance = test_class()
    
    # Run setup if it exists
    if hasattr(instance, 'setup_method'):
        instance.setup_method()
    
    try:
        method = getattr(instance, method_name)
        method()
        return True, None
    except Exception as e:
        return False, e
    finally:
        # Run teardown if it exists
        if hasattr(instance, 'teardown_method'):
            instance.teardown_method()


def run_tests_in_file(test_file):
    """Run all tests in a single test file."""
    print(f"\\n{'='*60}")
    print(f"Running tests in {test_file.name}")
    print('='*60)
    
    try:
        module = load_module_from_path(test_file)
    except Exception as e:
        print(f"ERROR: Failed to load {test_file}: {e}")
        return 0, 1
    
    passed = 0
    failed = 0
    
    # Find all test classes
    for name in dir(module):
        obj = getattr(module, name)
        if (isinstance(obj, type) and 
            name.startswith('Test') and 
            hasattr(obj, '__dict__')):
            
            print(f"\\n{name}:")
            
            # Find all test methods
            test_methods = [method for method in dir(obj) 
                          if method.startswith('test_')]
            
            for method_name in test_methods:
                try:
                    success, error = run_test_method(obj, method_name)
                    if success:
                        print(f"  ✓ {method_name}")
                        passed += 1
                    else:
                        print(f"  ✗ {method_name}")
                        print(f"    Error: {error}")
                        failed += 1
                except Exception as e:
                    print(f"  ✗ {method_name}")
                    print(f"    Setup/Teardown Error: {e}")
                    failed += 1
    
    return passed, failed


def main():
    """Main test runner function."""
    # Add src directory to path
    src_dir = Path(__file__).parent / "src"
    sys.path.insert(0, str(src_dir))
    
    # Find all test files
    test_dir = Path(__file__).parent / "tests"
    test_files = []
    
    # Look for test files in unit and integration directories
    for subdir in ["unit", "integration"]:
        subdir_path = test_dir / subdir
        if subdir_path.exists():
            test_files.extend(subdir_path.glob("test_*.py"))
    
    if not test_files:
        print("No test files found!")
        return 1
    
    total_passed = 0
    total_failed = 0
    
    print("Python Library Checker - Test Suite")
    print("=" * 60)
    
    for test_file in sorted(test_files):
        try:
            passed, failed = run_tests_in_file(test_file)
            total_passed += passed
            total_failed += failed
        except Exception as e:
            print(f"ERROR: Failed to run tests in {test_file}: {e}")
            traceback.print_exc()
            total_failed += 1
    
    # Print summary
    print(f"\\n{'='*60}")
    print("TEST SUMMARY")
    print('='*60)
    print(f"Total Passed: {total_passed}")
    print(f"Total Failed: {total_failed}")
    print(f"Total Tests:  {total_passed + total_failed}")
    
    if total_failed == 0:
        print("\\n🎉 All tests passed!")
        return 0
    else:
        print(f"\\n❌ {total_failed} test(s) failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())