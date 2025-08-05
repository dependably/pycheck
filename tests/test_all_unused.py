#!/usr/bin/env python3
"""
Test file where all imports are unused.
This file should have all import statements removed when cleaned up.
"""


def main():
    """Function that doesn't use any imports."""
    message = "Hello, World!"
    number = 42
    result = message + " " + str(number)
    return result

if __name__ == "__main__":
    output = main()
    print(output)