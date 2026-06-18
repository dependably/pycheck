#!/usr/bin/env python3
"""
Python Import Checker CLI Tool

A command-line tool to analyze and clean up unused imports in Python files.
Supports both read-only analysis and automatic cleanup of unused imports.
"""

import argparse
import ast
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Set, Tuple


class ImportCheckerError(Exception):
    """Custom exception for import checker errors."""
    pass


class ImportInfo:
    """Class to store information about an import statement."""
    
    def __init__(self, module: str, names: List[str], alias: Optional[str] = None, 
                 line_number: int = 0, is_from_import: bool = False):
        self.module = module  # The module being imported
        self.names = names    # List of names being imported (empty for 'import module')
        self.alias = alias    # Alias if used (as clause)
        self.line_number = line_number
        self.is_from_import = is_from_import  # True for 'from X import Y'
        self.used = False     # Track if this import is used
    
    def __repr__(self):
        return f"ImportInfo(module='{self.module}', names={self.names}, alias='{self.alias}', line={self.line_number})"


class ImportChecker:
    """Main class for handling Python import checking and cleanup."""
    
    def __init__(self, check_mode: bool = True, verbose: bool = False):
        """
        Initialize the ImportChecker.
        
        Args:
            check_mode: If True, perform read-only analysis. If False, cleanup unused imports.
            verbose: Enable verbose output
        """
        self.check_mode = check_mode
        self.verbose = verbose
        self.processed_files = 0
        self.total_issues = 0
    
    def log_verbose(self, message: str) -> None:
        """Print verbose message if verbose mode is enabled."""
        if self.verbose:
            print(f"[VERBOSE] {message}")
    
    def extract_imports_from_ast(self, tree: ast.AST) -> List[ImportInfo]:
        """
        Extract all import statements from an AST.
        
        Args:
            tree: The AST tree to analyze
            
        Returns:
            List of ImportInfo objects containing import details
        """
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                # Handle 'import module' statements
                for alias in node.names:
                    import_info = ImportInfo(
                        module=alias.name,
                        names=[],  # Empty for regular imports
                        alias=alias.asname,
                        line_number=node.lineno,
                        is_from_import=False
                    )
                    imports.append(import_info)
                    
            elif isinstance(node, ast.ImportFrom):
                # Handle 'from module import name' statements
                module_name = node.module or ""  # Handle relative imports
                
                # Store all names from this import in a single ImportInfo object
                all_names = [alias.name for alias in node.names]
                all_aliases = [alias.asname for alias in node.names]
                
                # Create individual ImportInfo objects for analysis
                for alias in node.names:
                    import_info = ImportInfo(
                        module=module_name,
                        names=[alias.name],
                        alias=alias.asname,
                        line_number=node.lineno,
                        is_from_import=True
                    )
                    # Store reference to all names on the same line for cleanup
                    import_info.all_names_on_line = all_names
                    import_info.all_aliases_on_line = all_aliases
                    imports.append(import_info)
        
        return imports
    
    def extract_name_references(self, tree: ast.AST) -> Set[str]:
        """
        Extract all name references from an AST (excluding imports).
        
        Args:
            tree: The AST tree to analyze
            
        Returns:
            Set of referenced names
        """
        references = set()
        
        class NameVisitor(ast.NodeVisitor):
            def visit_Name(self, node):
                # Only count names that are being loaded (not stored)
                if isinstance(node.ctx, ast.Load):
                    references.add(node.id)
                self.generic_visit(node)
            
            def visit_Attribute(self, node):
                # Handle attribute access like 'module.function'
                if isinstance(node.value, ast.Name) and isinstance(node.value.ctx, ast.Load):
                    references.add(node.value.id)
                self.generic_visit(node)
            
            def visit_Import(self, node):
                # Skip import statements themselves
                pass
            
            def visit_ImportFrom(self, node):
                # Skip import statements themselves
                pass
        
        visitor = NameVisitor()
        visitor.visit(tree)
        
        return references
    
    def analyze_imports(self, imports: List[ImportInfo], references: Set[str]) -> Tuple[List[ImportInfo], List[ImportInfo]]:
        """
        Analyze imports to determine which are used and which are unused.
        
        Args:
            imports: List of ImportInfo objects
            references: Set of names referenced in the code
            
        Returns:
            Tuple of (used_imports, unused_imports)
        """
        used_imports = []
        unused_imports = []
        
        for import_info in imports:
            is_used = False
            
            if import_info.is_from_import:
                # For 'from module import name' statements
                for name in import_info.names:
                    # Check if the imported name (or its alias) is referenced
                    check_name = import_info.alias if import_info.alias else name
                    if check_name in references:
                        is_used = True
                        break
            else:
                # For 'import module' statements
                check_name = import_info.alias if import_info.alias else import_info.module
                # For module imports, also check for dotted access
                module_base = check_name.split('.')[0]
                if module_base in references or check_name in references:
                    is_used = True
            
            import_info.used = is_used
            if is_used:
                used_imports.append(import_info)
            else:
                unused_imports.append(import_info)
        
        return used_imports, unused_imports
    
    def remove_unused_imports(self, content: str, unused_imports: List[ImportInfo]) -> str:
        """
        Remove unused import lines from file content while preserving formatting.
        Handles partial removal for multi-name imports.
        
        Args:
            content: Original file content as string
            unused_imports: List of ImportInfo objects for unused imports
            
        Returns:
            Modified content with unused imports removed
        """
        if not unused_imports:
            return content
        
        lines = content.splitlines(keepends=True)
        
        # Group unused imports by line number for from-imports
        unused_by_line = {}
        lines_to_remove = set()
        
        for import_info in unused_imports:
            line_number = import_info.line_number
            
            if import_info.is_from_import:
                if line_number not in unused_by_line:
                    unused_by_line[line_number] = []
                unused_by_line[line_number].append(import_info)
            else:
                # For regular imports, mark entire line for removal
                lines_to_remove.add(line_number - 1)  # Convert to 0-based
        
        # Process from-import lines that need partial removal
        for line_number, unused_from_line in unused_by_line.items():
            start_idx = line_number - 1  # Convert to 0-based

            if not (0 <= start_idx < len(lines)):
                continue

            # A from-import may span several physical lines (parenthesized or
            # backslash-continued). Find the full extent of the statement.
            end_idx = self._find_statement_span(lines, start_idx)
            original_line = lines[start_idx]

            # Get all imports from this statement (both used and unused)
            all_names = unused_from_line[0].all_names_on_line
            all_aliases = unused_from_line[0].all_aliases_on_line

            # Determine which names are unused
            unused_names = {imp.names[0] for imp in unused_from_line}

            # Keep the names that are still used, preserving aliases
            remaining_names = []
            for i, name in enumerate(all_names):
                if name not in unused_names:
                    alias = all_aliases[i]
                    remaining_names.append(f"{name} as {alias}" if alias else name)

            # Drop every continuation line; the statement is rewritten on its
            # first line (or removed entirely if nothing remains).
            for idx in range(start_idx + 1, end_idx + 1):
                lines_to_remove.add(idx)

            if remaining_names:
                # Reconstruct the import statement with the remaining names
                module_name = unused_from_line[0].module
                new_import_line = f"from {module_name} import {', '.join(remaining_names)}"

                # Preserve indentation and the original line ending
                indent = original_line[:len(original_line) - len(original_line.lstrip())]
                newline = "\r\n" if original_line.endswith("\r\n") else "\n"

                # Preserve an inline comment only for single-line statements
                comment = ""
                if end_idx == start_idx and '#' in original_line:
                    comment = original_line[original_line.find('#'):].rstrip("\r\n")

                if comment:
                    lines[start_idx] = f"{indent}{new_import_line}  {comment}{newline}"
                else:
                    lines[start_idx] = f"{indent}{new_import_line}{newline}"
            else:
                # All names were unused, remove the entire statement
                lines_to_remove.add(start_idx)

        # Remove lines marked for complete removal
        filtered_lines = [
            line for i, line in enumerate(lines) if i not in lines_to_remove
        ]

        # Clean up excessive blank lines (more than 2 consecutive)
        result_lines = []
        blank_count = 0
        
        for line in filtered_lines:
            if line.strip() == '':
                blank_count += 1
                if blank_count <= 2:  # Allow up to 2 consecutive blank lines
                    result_lines.append(line)
            else:
                blank_count = 0
                result_lines.append(line)
        
        return ''.join(result_lines)

    def _find_statement_span(self, lines: List[str], start_idx: int) -> int:
        """
        Find the index of the last physical line of an import statement that
        begins at ``start_idx``.

        Handles parenthesized (``from x import (a, b)``) and backslash-continued
        statements that span multiple physical lines.

        Args:
            lines: List of file lines
            start_idx: Index of the statement's first line

        Returns:
            Index of the statement's final line
        """
        depth = 0
        idx = start_idx
        while idx < len(lines):
            code = lines[idx].split('#', 1)[0]
            depth += code.count('(') - code.count(')')
            continues = code.rstrip().endswith('\\')
            if depth <= 0 and not continues:
                return idx
            idx += 1
        return len(lines) - 1

    def _is_complete_import_statement(self, lines: List[str], line_idx: int) -> bool:
        """
        Check if an import statement is complete at the given line.
        
        Args:
            lines: List of file lines
            line_idx: Index of line to check
            
        Returns:
            True if the import statement is complete
        """
        if line_idx >= len(lines):
            return True
        
        line = lines[line_idx].strip()
        
        # Check for obvious continuation indicators
        if line.endswith('\\') or line.endswith(','):
            return False
        
        # Check if next line looks like a continuation of import
        if line_idx + 1 < len(lines):
            next_line = lines[line_idx + 1].strip()
            # If next line starts with whitespace and contains import-like content
            if (next_line and 
                lines[line_idx + 1].startswith((' ', '\t')) and 
                not next_line.startswith(('import ', 'from '))):
                return False
        
        return True
    
    def process_file(self, file_path: Path) -> None:
        """
        Process a single Python file for import analysis.
        
        Args:
            file_path: Path to the Python file to process
            
        Raises:
            ImportCheckerError: If file processing fails
        """
        try:
            self.log_verbose(f"Processing file: {file_path}")
            
            # Validate file exists and is readable
            if not file_path.exists():
                raise ImportCheckerError(f"File not found: {file_path}")
            
            if not file_path.is_file():
                raise ImportCheckerError(f"Path is not a file: {file_path}")
            
            # Check if file is a Python file
            if file_path.suffix not in ['.py', '.pyw']:
                self.log_verbose(f"Skipping non-Python file: {file_path}")
                return
            
            # Read and parse the file
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                
                # Parse the AST
                tree = ast.parse(content, filename=str(file_path))
                
            except UnicodeDecodeError:
                # Try with different encoding if UTF-8 fails
                with open(file_path, 'r', encoding='latin-1') as file:
                    content = file.read()
                tree = ast.parse(content, filename=str(file_path))
            
            except SyntaxError as e:
                raise ImportCheckerError(f"Syntax error in {file_path}: {e}")
            
            # Extract imports and name references
            imports = self.extract_imports_from_ast(tree)
            references = self.extract_name_references(tree)
            
            self.log_verbose(f"Found {len(imports)} imports and {len(references)} name references")
            
            # Analyze imports
            used_imports, unused_imports = self.analyze_imports(imports, references)
            
            self.processed_files += 1
            file_issues = len(unused_imports)
            self.total_issues += file_issues
            
            if self.check_mode:
                print(f"Analyzing: {file_path}")
                
                if unused_imports:
                    print(f"  Found {file_issues} unused import(s):")
                    for import_info in unused_imports:
                        if import_info.is_from_import:
                            import_str = f"from {import_info.module} import {', '.join(import_info.names)}"
                        else:
                            import_str = f"import {import_info.module}"
                        
                        if import_info.alias:
                            import_str += f" as {import_info.alias}"
                        
                        print(f"    Line {import_info.line_number}: {import_str}")
                else:
                    print("  No unused imports found")
                    
                if self.verbose:
                    print(f"  Used imports: {len(used_imports)}")
                    for import_info in used_imports:
                        if import_info.is_from_import:
                            import_str = f"from {import_info.module} import {', '.join(import_info.names)}"
                        else:
                            import_str = f"import {import_info.module}"
                        
                        if import_info.alias:
                            import_str += f" as {import_info.alias}"
                        
                        print(f"    Line {import_info.line_number}: {import_str}")
            else:
                print(f"Cleaning: {file_path}")
                
                if unused_imports:
                    print(f"  Removing {file_issues} unused import(s)")
                    
                    # Create backup before modifying
                    backup_path = file_path.with_suffix(file_path.suffix + '.backup')
                    self.log_verbose(f"Creating backup: {backup_path}")
                    
                    shutil.copy2(file_path, backup_path)
                    
                    # Remove unused imports and rewrite file
                    modified_content = self.remove_unused_imports(content, unused_imports)
                    
                    # Write the modified content back to the file
                    with open(file_path, 'w', encoding='utf-8') as file:
                        file.write(modified_content)
                    
                    print(f"  Removed imports:")
                    for import_info in unused_imports:
                        if import_info.is_from_import:
                            import_str = f"from {import_info.module} import {', '.join(import_info.names)}"
                        else:
                            import_str = f"import {import_info.module}"
                        
                        if import_info.alias:
                            import_str += f" as {import_info.alias}"
                        
                        print(f"    Line {import_info.line_number}: {import_str}")
                    
                    print(f"  Backup saved as: {backup_path}")
                else:
                    print("  No unused imports to remove")
                
        except PermissionError as e:
            raise ImportCheckerError(f"Permission denied accessing file {file_path}: {e}")
        except Exception as e:
            raise ImportCheckerError(f"Error processing file {file_path}: {e}")
    
    def process_directory(self, directory_path: Path, recursive: bool = True) -> None:
        """
        Process all Python files in a directory.
        
        Args:
            directory_path: Path to the directory to process
            recursive: If True, process subdirectories recursively
            
        Raises:
            ImportCheckerError: If directory processing fails
        """
        try:
            self.log_verbose(f"Processing directory: {directory_path}")
            
            if not directory_path.exists():
                raise ImportCheckerError(f"Directory not found: {directory_path}")
            
            if not directory_path.is_dir():
                raise ImportCheckerError(f"Path is not a directory: {directory_path}")
            
            # Get pattern for finding Python files
            pattern = "**/*.py" if recursive else "*.py"
            
            # Process all Python files
            python_files = list(directory_path.glob(pattern))
            
            if not python_files:
                print(f"No Python files found in: {directory_path}")
                return
            
            self.log_verbose(f"Found {len(python_files)} Python files")
            
            for file_path in python_files:
                self.process_file(file_path)
                
        except PermissionError as e:
            raise ImportCheckerError(f"Permission denied accessing directory {directory_path}: {e}")
        except Exception as e:
            raise ImportCheckerError(f"Error processing directory {directory_path}: {e}")
    
    def run(self, target_path: Path, recursive: bool = True) -> None:
        """
        Run the import checker on the specified target.
        
        Args:
            target_path: Path to file or directory to process
            recursive: If True and target is directory, process recursively
            
        Raises:
            ImportCheckerError: If processing fails
        """
        try:
            # Resolve the path to handle relative paths and symlinks
            resolved_path = target_path.resolve()
            
            if resolved_path.is_file():
                self.process_file(resolved_path)
            elif resolved_path.is_dir():
                self.process_directory(resolved_path, recursive)
            else:
                raise ImportCheckerError(f"Target path does not exist: {target_path}")
            
            # Print summary
            mode_str = "Analysis" if self.check_mode else "Cleanup"
            print(f"\n{mode_str} complete:")
            print(f"  Files processed: {self.processed_files}")
            print(f"  Issues found: {self.total_issues}")
            
        except ImportCheckerError:
            raise
        except Exception as e:
            raise ImportCheckerError(f"Unexpected error during processing: {e}")


def validate_target_path(path_str: str) -> Path:
    """
    Validate and convert target path string to Path object.
    
    Args:
        path_str: String representation of the target path
        
    Returns:
        Path object for the target
        
    Raises:
        argparse.ArgumentTypeError: If path is invalid
    """
    try:
        path = Path(path_str)
        
        # Basic validation - detailed validation happens in ImportChecker
        if not path.exists():
            raise argparse.ArgumentTypeError(f"Path does not exist: {path_str}")
        
        return path
        
    except Exception as e:
        raise argparse.ArgumentTypeError(f"Invalid path '{path_str}': {e}")


def setup_argument_parser() -> argparse.ArgumentParser:
    """
    Set up and configure the command-line argument parser.
    
    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        prog="python-import-checker",
        description="Analyze and clean up unused imports in Python files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --check myfile.py                    # Analyze single file
  %(prog)s --check src/                         # Analyze directory recursively
  %(prog)s --cleanup --no-recursive src/       # Clean directory non-recursively
  %(prog)s --cleanup myfile.py --verbose       # Clean file with verbose output
  %(prog)s --validate .                        # Validate config artifacts in this directory
        """
    )
    
    # Mode selection (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--check",
        action="store_true",
        help="Perform read-only analysis of imports (no changes made)"
    )
    mode_group.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove unused imports from files (modifies files)"
    )
    mode_group.add_argument(
        "--validate",
        action="store_true",
        help="Validate committed config artifacts (pyproject.toml, pip.conf, requirements.txt)"
    )
    
    # Target path (required)
    parser.add_argument(
        "target",
        type=validate_target_path,
        help="Path to Python file or directory to process"
    )
    
    # Optional arguments
    parser.add_argument(
        "--recursive",
        action="store_true",
        default=True,
        help="Process directories recursively (default: True)"
    )
    parser.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        help="Do not process directories recursively"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="python-import-checker 1.1.0"
    )
    
    return parser


def main() -> int:
    """
    Main entry point for the CLI application.
    
    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        # Parse command-line arguments
        parser = setup_argument_parser()
        args = parser.parse_args()
        
        # Validation mode is dispatched to the validators package and returns
        # early; the AST import-checker path below is untouched.
        if args.validate:
            # Lazy import so the import-checker fast path stays stdlib-only.
            try:
                from validators.runner import run_validators
            except ImportError:  # installed wheel (src.validators)
                from .validators.runner import run_validators
            if args.verbose:
                print(f"Validating config artifacts under: {args.target}")
            exit_code: int = run_validators(args.target, verbose=args.verbose)
            return exit_code

        # Determine mode
        check_mode = args.check

        if args.verbose:
            mode_str = "check" if check_mode else "cleanup"
            print(f"Running in {mode_str} mode on: {args.target}")
            print(f"Recursive: {args.recursive}")

        # Create and run checker
        checker = ImportChecker(
            check_mode=check_mode,
            verbose=args.verbose
        )
        
        checker.run(
            target_path=args.target,
            recursive=args.recursive
        )
        
        return 0
        
    except ImportCheckerError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())