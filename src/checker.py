#!/usr/bin/env python3
"""
Python Import Checker CLI Tool

A command-line tool to analyze and clean up unused imports in Python files.
Supports both read-only analysis and automatic cleanup of unused imports.
"""

import argparse
import ast
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

__version__ = "1.2.0"

# Process exit codes, aligned with the Dependably suite convention:
#   0 clean · 1 findings (block) · 2 usage error / operational-internal error.
EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


class ImportCheckerError(Exception):
    """Custom exception for import checker errors."""

    pass


# Identity reported in the shared Dependably finding JSON envelope (schema v1).
TOOL_NAME = "python-check"
SCHEMA_VERSION = "1.0"

# python-check's internal severities map onto the single shared ladder
# (critical > high > moderate > low > info). error->high, warning->low.
_SEVERITY_LADDER: Dict[str, str] = {"error": "high", "warning": "low"}

# Short, optional remediation hints keyed by ruleId. Anything absent -> null.
_REMEDIATION: Dict[str, str] = {
    "unused-import": "Remove the unused import.",
}


def _to_finding(raw: Dict[str, Any], category: str) -> Dict[str, Any]:
    """Map an internal finding dict to the shared schema-v1 ``Finding`` shape.

    Internal findings carry ``code`` / ``file`` / ``line`` / ``message`` /
    ``severity`` (``error``|``warning``); the shared shape uses ``ruleId``,
    ``category``, a ``location`` object, a ladder ``severity`` string and an
    optional ``remediation``.
    """
    rule_id = raw.get("code")
    return {
        "severity": _SEVERITY_LADDER.get(str(raw.get("severity")), "info"),
        "ruleId": rule_id,
        "category": category,
        "message": raw.get("message", ""),
        "location": {
            "file": raw.get("file"),
            "line": raw.get("line"),
            "column": None,
        },
        "remediation": _REMEDIATION.get(str(rule_id)),
    }


def build_json_report(
    target: Any,
    scanned: int,
    raw_findings: List[Dict[str, Any]],
    category: str,
    exit_code: int,
) -> Dict[str, Any]:
    """Assemble the shared Dependably finding JSON envelope (schema v1).

    Every Dependably tool emits this exact envelope so a single consumer parses
    all of them the same way: ``tool`` / ``toolVersion`` / ``schemaVersion`` /
    ``target`` / ``summary`` / ``findings``. ``raw_findings`` (internal shape)
    are mapped to the shared ``Finding`` shape under ``category`` (``lint`` for
    import findings, ``config`` for config-validation findings).

    ``summary.scanned`` is the number of files/artifacts examined,
    ``summary.findings`` always equals ``len(findings)`` (never truncated), and
    ``summary.exitCode`` equals the real process exit code.
    """
    findings = [_to_finding(raw, category) for raw in raw_findings]
    by_severity = {"critical": 0, "high": 0, "moderate": 0, "low": 0, "info": 0}
    for finding in findings:
        by_severity[finding["severity"]] += 1
    return {
        "tool": TOOL_NAME,
        "toolVersion": __version__,
        "schemaVersion": SCHEMA_VERSION,
        "target": str(target),
        "summary": {
            "scanned": scanned,
            "findings": len(findings),
            "bySeverity": by_severity,
            "exitCode": exit_code,
        },
        "findings": findings,
    }


def emit_json(report: Dict[str, Any]) -> None:
    """Write a single JSON document to stdout (kept clean: no text mixed in)."""
    json.dump(report, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")


class ImportInfo:
    """Class to store information about an import statement."""

    def __init__(
        self,
        module: str,
        names: List[str],
        alias: Optional[str] = None,
        line_number: int = 0,
        is_from_import: bool = False,
    ):
        self.module = module  # The module being imported
        self.names = names  # List of names being imported (empty for 'import module')
        self.alias = alias  # Alias if used (as clause)
        self.line_number = line_number
        self.is_from_import = is_from_import  # True for 'from X import Y'
        self.used = False  # Track if this import is used
        # Populated for from-imports: every name/alias sharing this physical line
        self.all_names_on_line: List[str] = []
        self.all_aliases_on_line: List[Optional[str]] = []

    def __repr__(self) -> str:
        return f"ImportInfo(module='{self.module}', names={self.names}, alias='{self.alias}', line={self.line_number})"


class _NameReferenceVisitor(ast.NodeVisitor):
    """Collect names referenced (loaded) in a module, plus `__all__` exports.

    Names listed in `__all__` are re-exported public API, so an import of such a
    name counts as "used" even when it is not otherwise referenced.
    """

    def __init__(self, references: Set[str]) -> None:
        self._references = references

    def visit_Name(self, node: ast.Name) -> None:
        # Only count names that are being loaded (not stored).
        if isinstance(node.ctx, ast.Load):
            self._references.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Handle attribute access like 'module.function'.
        if isinstance(node.value, ast.Name) and isinstance(node.value.ctx, ast.Load):
            self._references.add(node.value.id)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        # Skip import statements themselves.
        pass

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # Skip import statements themselves.
        pass

    def visit_Assign(self, node: ast.Assign) -> None:
        if any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            self._collect_all_exports(node.value)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        # Handle `__all__ += [...]`.
        if isinstance(node.target, ast.Name) and node.target.id == "__all__":
            self._collect_all_exports(node.value)
        self.generic_visit(node)

    def _collect_all_exports(self, value: ast.expr) -> None:
        if isinstance(value, (ast.List, ast.Tuple)):
            for elt in value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    self._references.add(elt.value)


class ImportChecker:
    """Main class for handling Python import checking and cleanup."""

    def __init__(self, check_mode: bool = True, verbose: bool = False, quiet: bool = False):
        """
        Initialize the ImportChecker.

        Args:
            check_mode: If True, perform read-only analysis. If False, cleanup unused imports.
            verbose: Enable verbose output
            quiet: Suppress all human-readable stdout (used by ``--format json`` so
                stdout carries only the JSON document). Findings are still
                collected in ``self.findings``.
        """
        self.check_mode = check_mode
        self.verbose = verbose
        self.quiet = quiet
        self.processed_files = 0
        self.total_issues = 0
        # Machine-readable findings, collected regardless of output format.
        self.findings: List[Dict[str, Any]] = []

    def log_verbose(self, message: str) -> None:
        """Print verbose message if verbose mode is enabled (and not quiet)."""
        if self.verbose and not self.quiet:
            print(f"[VERBOSE] {message}")

    def _record_findings(self, file_path: Path, unused_imports: List[ImportInfo]) -> None:
        """Append one finding per unused import to the machine-readable list."""
        for import_info in unused_imports:
            self.findings.append(
                {
                    "code": "unused-import",
                    "file": str(file_path),
                    "line": import_info.line_number,
                    "message": f"unused import: {self._format_import(import_info)}",
                    # Unused imports block the gate (exit 1) in check mode, so they
                    # are reported as errors, mirroring the validator severity model.
                    "severity": "error",
                }
            )

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
                        is_from_import=False,
                    )
                    imports.append(import_info)

            elif isinstance(node, ast.ImportFrom):
                # Handle 'from module import name' statements
                module_name = node.module or ""  # Handle relative imports

                # `from __future__ import ...` are compiler directives, not real
                # imports — they're never referenced by name, so never "unused".
                if module_name == "__future__":
                    continue

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
                        is_from_import=True,
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
        references: Set[str] = set()
        _NameReferenceVisitor(references).visit(tree)
        return references

    def analyze_imports(
        self, imports: List[ImportInfo], references: Set[str]
    ) -> Tuple[List[ImportInfo], List[ImportInfo]]:
        """
        Analyze imports to determine which are used and which are unused.

        Args:
            imports: List of ImportInfo objects
            references: Set of names referenced in the code

        Returns:
            Tuple of (used_imports, unused_imports)
        """
        used_imports: List[ImportInfo] = []
        unused_imports: List[ImportInfo] = []

        for import_info in imports:
            import_info.used = self._import_is_used(import_info, references)
            (used_imports if import_info.used else unused_imports).append(import_info)

        return used_imports, unused_imports

    @staticmethod
    def _import_is_used(import_info: ImportInfo, references: Set[str]) -> bool:
        """Return True if an import (or its alias) is referenced in the code."""
        if import_info.is_from_import:
            # 'from module import name' — any imported name (or its alias) used.
            return any((import_info.alias or name) in references for name in import_info.names)

        # 'import module' — match the alias/module, including dotted access.
        check_name = import_info.alias if import_info.alias else import_info.module
        module_base = check_name.split(".")[0]
        return module_base in references or check_name in references

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
        unused_by_line, lines_to_remove = self._partition_unused(unused_imports)

        # Rewrite each from-import statement that needs partial removal.
        for line_number, unused_from_line in unused_by_line.items():
            self._rewrite_from_import(lines, line_number, unused_from_line, lines_to_remove)

        filtered_lines = [line for i, line in enumerate(lines) if i not in lines_to_remove]
        return self._collapse_blank_lines(filtered_lines)

    @staticmethod
    def _partition_unused(
        unused_imports: List[ImportInfo],
    ) -> Tuple[Dict[int, List[ImportInfo]], Set[int]]:
        """Split unused imports into per-line from-imports and whole lines to drop.

        Returns (from-imports grouped by 1-based line number, 0-based line
        indices to remove outright for plain ``import module`` statements).
        """
        unused_by_line: Dict[int, List[ImportInfo]] = {}
        lines_to_remove: Set[int] = set()
        for import_info in unused_imports:
            if import_info.is_from_import:
                unused_by_line.setdefault(import_info.line_number, []).append(import_info)
            else:
                lines_to_remove.add(import_info.line_number - 1)  # 0-based
        return unused_by_line, lines_to_remove

    def _rewrite_from_import(
        self,
        lines: List[str],
        line_number: int,
        unused_from_line: List[ImportInfo],
        lines_to_remove: Set[int],
    ) -> None:
        """Rewrite a single from-import statement in place, dropping unused names.

        A from-import may span several physical lines (parenthesized or
        backslash-continued); continuation lines are removed and the statement is
        rewritten on its first line, or removed entirely if nothing remains.
        """
        start_idx = line_number - 1  # 0-based
        if not (0 <= start_idx < len(lines)):
            return

        end_idx = self._find_statement_span(lines, start_idx)
        original_line = lines[start_idx]
        all_names = unused_from_line[0].all_names_on_line
        all_aliases = unused_from_line[0].all_aliases_on_line
        unused_names = {imp.names[0] for imp in unused_from_line}

        remaining_names = [
            f"{name} as {all_aliases[i]}" if all_aliases[i] else name
            for i, name in enumerate(all_names)
            if name not in unused_names
        ]

        # Drop every continuation line of the statement.
        for idx in range(start_idx + 1, end_idx + 1):
            lines_to_remove.add(idx)

        if not remaining_names:
            # All names were unused — remove the entire statement.
            lines_to_remove.add(start_idx)
            return

        module_name = unused_from_line[0].module
        new_import_line = f"from {module_name} import {', '.join(remaining_names)}"
        indent = original_line[: len(original_line) - len(original_line.lstrip())]
        newline = "\r\n" if original_line.endswith("\r\n") else "\n"

        # Preserve an inline comment only for single-line statements.
        comment = ""
        if end_idx == start_idx and "#" in original_line:
            comment = original_line[original_line.find("#") :].rstrip("\r\n")

        if comment:
            lines[start_idx] = f"{indent}{new_import_line}  {comment}{newline}"
        else:
            lines[start_idx] = f"{indent}{new_import_line}{newline}"

    @staticmethod
    def _collapse_blank_lines(filtered_lines: List[str]) -> str:
        """Join lines, collapsing runs of more than 2 consecutive blank lines."""
        result_lines: List[str] = []
        blank_count = 0
        for line in filtered_lines:
            if line.strip() == "":
                blank_count += 1
                if blank_count <= 2:  # Allow up to 2 consecutive blank lines
                    result_lines.append(line)
            else:
                blank_count = 0
                result_lines.append(line)
        return "".join(result_lines)

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
            code = lines[idx].split("#", 1)[0]
            depth += code.count("(") - code.count(")")
            continues = code.rstrip().endswith("\\")
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
        if line.endswith("\\") or line.endswith(","):
            return False

        # Check if next line looks like a continuation of import
        if line_idx + 1 < len(lines):
            next_line = lines[line_idx + 1].strip()
            # If next line starts with whitespace and contains import-like content
            if (
                next_line
                and lines[line_idx + 1].startswith((" ", "\t"))
                and not next_line.startswith(("import ", "from "))
            ):
                return False

        return True

    @staticmethod
    def _format_import(import_info: ImportInfo) -> str:
        """Render an ImportInfo back to its source-like statement string."""
        if import_info.is_from_import:
            import_str = f"from {import_info.module} import {', '.join(import_info.names)}"
        else:
            import_str = f"import {import_info.module}"
        if import_info.alias:
            import_str += f" as {import_info.alias}"
        return import_str

    def _read_and_parse(self, file_path: Path) -> Tuple[str, ast.AST]:
        """Read a file (UTF-8 with latin-1 fallback) and parse it into an AST."""
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                content = file.read()
            tree = ast.parse(content, filename=str(file_path))
        except UnicodeDecodeError:
            # Retry with a permissive encoding if UTF-8 fails.
            with open(file_path, "r", encoding="latin-1") as file:
                content = file.read()
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError as e:
            raise ImportCheckerError(f"Syntax error in {file_path}: {e}")
        return content, tree

    def _report_check(self, file_path: Path, used_imports: List[ImportInfo], unused_imports: List[ImportInfo]) -> None:
        """Print read-only analysis results for one file."""
        if self.quiet:
            return
        print(f"Analyzing: {file_path}")
        if unused_imports:
            print(f"  Found {len(unused_imports)} unused import(s):")
            for import_info in unused_imports:
                print(f"    Line {import_info.line_number}: {self._format_import(import_info)}")
        else:
            print("  No unused imports found")

        if self.verbose:
            print(f"  Used imports: {len(used_imports)}")
            for import_info in used_imports:
                print(f"    Line {import_info.line_number}: {self._format_import(import_info)}")

    def _report_cleanup(self, file_path: Path, content: str, unused_imports: List[ImportInfo]) -> None:
        """Remove unused imports from a file (with backup) and print results."""
        if not self.quiet:
            print(f"Cleaning: {file_path}")
        if not unused_imports:
            if not self.quiet:
                print("  No unused imports to remove")
            return

        if not self.quiet:
            print(f"  Removing {len(unused_imports)} unused import(s)")

        # Create a backup before modifying.
        backup_path = file_path.with_suffix(file_path.suffix + ".backup")
        self.log_verbose(f"Creating backup: {backup_path}")
        shutil.copy2(file_path, backup_path)

        modified_content = self.remove_unused_imports(content, unused_imports)
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(modified_content)

        if not self.quiet:
            print("  Removed imports:")
            for import_info in unused_imports:
                print(f"    Line {import_info.line_number}: {self._format_import(import_info)}")
            print(f"  Backup saved as: {backup_path}")

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
            if file_path.suffix not in [".py", ".pyw"]:
                self.log_verbose(f"Skipping non-Python file: {file_path}")
                return

            content, tree = self._read_and_parse(file_path)

            imports = self.extract_imports_from_ast(tree)
            references = self.extract_name_references(tree)
            self.log_verbose(f"Found {len(imports)} imports and {len(references)} name references")

            used_imports, unused_imports = self.analyze_imports(imports, references)

            self.processed_files += 1
            self.total_issues += len(unused_imports)
            self._record_findings(file_path, unused_imports)

            if self.check_mode:
                self._report_check(file_path, used_imports, unused_imports)
            else:
                self._report_cleanup(file_path, content, unused_imports)

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
                if not self.quiet:
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
            if not self.quiet:
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
        """,
    )

    # Mode selection (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--check", action="store_true", help="Perform read-only analysis of imports (no changes made)"
    )
    mode_group.add_argument("--cleanup", action="store_true", help="Remove unused imports from files (modifies files)")
    mode_group.add_argument(
        "--validate",
        action="store_true",
        help="Validate committed config artifacts (pyproject.toml, pip.conf, requirements.txt)",
    )

    # Target path (required)
    parser.add_argument("target", type=validate_target_path, help="Path to Python file or directory to process")

    # Optional arguments
    parser.add_argument(
        "--recursive", action="store_true", default=True, help="Process directories recursively (default: True)"
    )
    parser.add_argument(
        "--no-recursive", dest="recursive", action="store_false", help="Do not process directories recursively"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        help=(
            "Output format (default: human). 'json' emits a single machine-readable "
            "JSON document to stdout with the full set of findings; stdout is kept "
            "clean (status/progress is routed to stderr)."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to a .dependably-check config (default: discovered by walking up from the target)",
    )
    parser.add_argument("--version", action="version", version=f"python-import-checker {__version__}")

    return parser


def _run_validate(target: Path, verbose: bool, config: Optional[Path] = None, output_format: str = "human") -> int:
    """Dispatch --validate to the validators package (lazy import)."""
    try:
        from validators.runner import run_validators
    except ImportError:  # installed wheel (src.validators)
        from .validators.runner import run_validators
    if verbose:
        # In json mode keep stdout clean; status goes to stderr.
        stream = sys.stderr if output_format == "json" else sys.stdout
        print(f"Validating config artifacts under: {target}", file=stream)
    exit_code: int = run_validators(target, config_path=config, output_format=output_format)
    return exit_code


def _run_import_check(args: argparse.Namespace) -> int:
    """Run the AST import checker in --check or --cleanup mode."""
    check_mode = args.check
    json_mode = args.format == "json"
    if args.verbose:
        mode_str = "check" if check_mode else "cleanup"
        # Route status to stderr in json mode so stdout carries only the document.
        stream = sys.stderr if json_mode else sys.stdout
        print(f"Running in {mode_str} mode on: {args.target}", file=stream)
        print(f"Recursive: {args.recursive}", file=stream)

    checker = ImportChecker(check_mode=check_mode, verbose=args.verbose, quiet=json_mode)
    checker.run(target_path=args.target, recursive=args.recursive)

    # In check mode, exit non-zero when unused imports are found so the tool can
    # gate CI / git hooks (linter convention). Cleanup mode returns 0 — it has
    # already removed them.
    exit_code = EXIT_FINDINGS if (check_mode and checker.total_issues > 0) else EXIT_OK

    if json_mode:
        emit_json(
            build_json_report(
                target=args.target,
                scanned=checker.processed_files,
                raw_findings=checker.findings,
                category="lint",
                exit_code=exit_code,
            )
        )

    return exit_code


def main() -> int:
    """
    Main entry point for the CLI application.

    Returns:
        Exit code: 0 clean, 1 findings (block), 2 usage/operational error.
    """
    try:
        parser = setup_argument_parser()
        args = parser.parse_args()

        if args.validate:
            return _run_validate(args.target, args.verbose, args.config, args.format)
        return _run_import_check(args)

    # Operational / internal errors are NOT findings: per the suite convention
    # exit 1 is reserved for findings (block), so these exit 2.
    except ImportCheckerError as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return EXIT_ERROR
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
