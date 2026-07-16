"""Unit tests for CLI argument parsing functionality."""

import argparse
import pytest
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from checker import (
    setup_argument_parser,
    validate_target_path,
    main,
    ImportCheckerError,
    parse_fail_on,
    parse_rule_overrides,
    gate_trips,
)


class TestValidateTargetPath:
    """Test cases for validate_target_path function."""

    def test_validate_existing_file(self, tmp_path):
        """Test validation of existing file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        result = validate_target_path(str(test_file))
        assert isinstance(result, Path)
        assert result == test_file

    def test_validate_existing_directory(self, tmp_path):
        """Test validation of existing directory."""
        result = validate_target_path(str(tmp_path))
        assert isinstance(result, Path)
        assert result == tmp_path

    def test_validate_nonexistent_path(self):
        """Test validation of non-existent path."""
        with pytest.raises(argparse.ArgumentTypeError) as excinfo:
            validate_target_path("/nonexistent/path")

        assert "Path does not exist" in str(excinfo.value)

    def test_validate_relative_path(self, tmp_path):
        """Test validation of relative path."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        # Change to parent directory and use relative path
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path.parent)
            relative_path = tmp_path.name + "/test.py"

            result = validate_target_path(relative_path)
            assert isinstance(result, Path)
            assert result.exists()
        finally:
            os.chdir(original_cwd)


class TestSetupArgumentParser:
    """Test cases for setup_argument_parser function."""

    def setup_method(self):
        """Set up test instance."""
        self.parser = setup_argument_parser()

    def test_parser_creation(self):
        """Test that parser is created correctly."""
        assert isinstance(self.parser, argparse.ArgumentParser)
        assert self.parser.prog == "python-import-checker"

    def test_check_mode_argument(self, tmp_path):
        """Test --check argument."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        args = self.parser.parse_args(["--check", str(test_file)])

        assert args.check is True
        assert args.cleanup is False
        assert args.target == test_file

    def test_cleanup_mode_argument(self, tmp_path):
        """Test --cleanup argument."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        args = self.parser.parse_args(["--cleanup", str(test_file)])

        assert args.check is False
        assert args.cleanup is True
        assert args.target == test_file

    def test_validate_mode_argument(self, tmp_path):
        """Test --validate argument."""
        args = self.parser.parse_args(["--validate", str(tmp_path)])

        assert args.validate is True
        assert args.check is False
        assert args.cleanup is False
        assert args.target == tmp_path

    def test_mutually_exclusive_modes(self, tmp_path):
        """Test that --check and --cleanup are mutually exclusive."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        with pytest.raises(SystemExit):
            self.parser.parse_args(["--check", "--cleanup", str(test_file)])

    def test_validate_mutually_exclusive(self, tmp_path):
        """Test that --validate is mutually exclusive with the other modes."""
        with pytest.raises(SystemExit):
            self.parser.parse_args(["--validate", "--check", str(tmp_path)])

    def test_missing_mode_argument(self, tmp_path):
        """Test that mode argument is required."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        with pytest.raises(SystemExit):
            self.parser.parse_args([str(test_file)])

    def test_recursive_default(self, tmp_path):
        """Test that recursive is True by default (no --recursive flag needed)."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        args = self.parser.parse_args(["--check", str(test_file)])
        assert args.recursive is True

    def test_recursive_flag_removed(self, tmp_path):
        """The dead --recursive flag is gone (it was a no-op default=True)."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        with pytest.raises(SystemExit) as excinfo:
            self.parser.parse_args(["--check", "--recursive", str(test_file)])
        # argparse rejects unknown options with exit code 2.
        assert excinfo.value.code == 2

    def test_no_recursive_argument(self, tmp_path):
        """Test --no-recursive argument."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        args = self.parser.parse_args(["--check", "--no-recursive", str(test_file)])
        assert args.recursive is False

    def test_verbose_argument(self, tmp_path):
        """Test --verbose argument."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        args = self.parser.parse_args(["--check", "--verbose", str(test_file)])
        assert args.verbose is True

        # Test short form
        args = self.parser.parse_args(["--check", "-v", str(test_file)])
        assert args.verbose is True

    def test_verbose_default(self, tmp_path):
        """Test that verbose is False by default."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        args = self.parser.parse_args(["--check", str(test_file)])
        assert args.verbose is False

    def test_version_argument(self):
        """Test --version argument."""
        with pytest.raises(SystemExit) as excinfo:
            self.parser.parse_args(["--version"])

        # argparse exits with code 0 for --version
        assert excinfo.value.code == 0

    def test_help_argument(self):
        """Test --help argument."""
        with pytest.raises(SystemExit) as excinfo:
            self.parser.parse_args(["--help"])

        # argparse exits with code 0 for --help
        assert excinfo.value.code == 0

    def test_directory_target(self, tmp_path):
        """Test parsing with directory target."""
        args = self.parser.parse_args(["--check", str(tmp_path)])

        assert args.check is True
        assert args.target == tmp_path
        assert args.recursive is True

    def test_all_arguments_together(self, tmp_path):
        """Test parsing with all optional arguments."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        args = self.parser.parse_args(["--cleanup", "--no-recursive", "--verbose", str(test_file)])

        assert args.cleanup is True
        assert args.check is False
        assert args.recursive is False
        assert args.verbose is True
        assert args.target == test_file


class TestMainFunction:
    """Test cases for main function."""

    @patch("checker.ImportChecker")
    def test_main_check_mode(self, mock_checker_class, tmp_path):
        """Test main function in check mode."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        mock_checker = MagicMock()
        mock_checker_class.return_value = mock_checker
        mock_checker.total_issues = 0

        with patch.object(sys, "argv", ["checker.py", "--check", str(test_file)]):
            result = main()

        assert result == 0
        mock_checker_class.assert_called_once_with(
            check_mode=True, verbose=False, quiet=False, remove_possible_reexports=False
        )
        mock_checker.run.assert_called_once_with(target_path=test_file, recursive=True)

    @patch("checker.ImportChecker")
    def test_main_cleanup_mode(self, mock_checker_class, tmp_path):
        """Test main function in cleanup mode."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        mock_checker = MagicMock()
        mock_checker_class.return_value = mock_checker
        mock_checker.total_issues = 0

        with patch.object(sys, "argv", ["checker.py", "--cleanup", str(test_file)]):
            result = main()

        assert result == 0
        mock_checker_class.assert_called_once_with(
            check_mode=False, verbose=False, quiet=False, remove_possible_reexports=False
        )
        mock_checker.run.assert_called_once_with(target_path=test_file, recursive=True)

    @patch("validators.runner.run_validators")
    def test_main_validate_mode(self, mock_run_validators, tmp_path):
        """Test main function dispatches to the validators and propagates exit code."""
        mock_run_validators.return_value = 0

        with patch.object(sys, "argv", ["checker.py", "--validate", str(tmp_path)]):
            result = main()

        assert result == 0
        mock_run_validators.assert_called_once_with(
            tmp_path, recursive=True, config_path=None, output_format="human", fail_on=[], rule_overrides={}
        )

    @patch("validators.runner.run_validators")
    def test_main_validate_propagates_failure(self, mock_run_validators, tmp_path):
        """Test main returns the runner's non-zero exit code."""
        mock_run_validators.return_value = 1

        with patch.object(sys, "argv", ["checker.py", "--validate", str(tmp_path)]):
            result = main()

        assert result == 1

    @patch("validators.runner.run_validators")
    def test_main_validate_threads_config_flag(self, mock_run_validators, tmp_path):
        """--config <path> is threaded to the runner as config_path."""
        mock_run_validators.return_value = 0
        cfg = tmp_path / ".dependably-check"
        cfg.write_text("{}", encoding="utf-8")

        with patch.object(sys, "argv", ["checker.py", "--validate", str(tmp_path), "--config", str(cfg)]):
            result = main()

        assert result == 0
        mock_run_validators.assert_called_once_with(
            tmp_path, recursive=True, config_path=cfg, output_format="human", fail_on=[], rule_overrides={}
        )

    def test_main_check_exits_nonzero_on_unused(self, tmp_path):
        """--check returns 1 when unused imports are found (gates CI/hooks)."""
        test_file = tmp_path / "x.py"
        test_file.write_text("import os\nimport sys\nprint(os.getcwd())\n")  # sys unused

        with patch.object(sys, "argv", ["checker.py", "--check", str(test_file)]):
            assert main() == 1

    def test_main_check_exits_zero_when_clean(self, tmp_path):
        """--check returns 0 when there are no unused imports."""
        test_file = tmp_path / "x.py"
        test_file.write_text("import os\nprint(os.getcwd())\n")

        with patch.object(sys, "argv", ["checker.py", "--check", str(test_file)]):
            assert main() == 0

    @patch("checker.ImportChecker")
    def test_main_verbose_mode(self, mock_checker_class, tmp_path):
        """Test main function with verbose option."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        mock_checker = MagicMock()
        mock_checker_class.return_value = mock_checker
        mock_checker.total_issues = 0

        with patch.object(sys, "argv", ["checker.py", "--check", "--verbose", str(test_file)]):
            result = main()

        assert result == 0
        mock_checker_class.assert_called_once_with(
            check_mode=True, verbose=True, quiet=False, remove_possible_reexports=False
        )

    @patch("checker.ImportChecker")
    def test_main_no_recursive(self, mock_checker_class, tmp_path):
        """Test main function with no-recursive option."""
        mock_checker = MagicMock()
        mock_checker_class.return_value = mock_checker
        mock_checker.total_issues = 0

        with patch.object(sys, "argv", ["checker.py", "--check", "--no-recursive", str(tmp_path)]):
            result = main()

        assert result == 0
        mock_checker.run.assert_called_once_with(target_path=tmp_path, recursive=False)

    @patch("checker.ImportChecker")
    @patch("builtins.print")
    def test_main_with_import_checker_error(self, mock_print, mock_checker_class, tmp_path):
        """Test main function handling ImportCheckerError."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        mock_checker = MagicMock()
        mock_checker.run.side_effect = ImportCheckerError("Test error")
        mock_checker_class.return_value = mock_checker
        mock_checker.total_issues = 0

        with patch.object(sys, "argv", ["checker.py", "--check", str(test_file)]):
            result = main()

        # Operational error (not a finding) -> exit 2 per the suite convention.
        assert result == 2
        mock_print.assert_called_with("Error: Test error", file=sys.stderr)

    @patch("checker.ImportChecker")
    @patch("builtins.print")
    def test_main_with_keyboard_interrupt(self, mock_print, mock_checker_class, tmp_path):
        """Test main function handling KeyboardInterrupt."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        mock_checker = MagicMock()
        mock_checker.run.side_effect = KeyboardInterrupt()
        mock_checker_class.return_value = mock_checker
        mock_checker.total_issues = 0

        with patch.object(sys, "argv", ["checker.py", "--check", str(test_file)]):
            result = main()

        # Interrupted run is not a finding -> exit 2 per the suite convention.
        assert result == 2
        mock_print.assert_called_with("\nOperation cancelled by user", file=sys.stderr)

    @patch("checker.ImportChecker")
    @patch("builtins.print")
    def test_main_with_unexpected_error(self, mock_print, mock_checker_class, tmp_path):
        """Test main function handling unexpected errors."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        mock_checker = MagicMock()
        mock_checker.run.side_effect = RuntimeError("Unexpected error")
        mock_checker_class.return_value = mock_checker
        mock_checker.total_issues = 0

        with patch.object(sys, "argv", ["checker.py", "--check", str(test_file)]):
            result = main()

        # Internal error (not a finding) -> exit 2 per the suite convention.
        assert result == 2
        mock_print.assert_called_with("Unexpected error: Unexpected error", file=sys.stderr)

    def test_main_with_invalid_arguments(self):
        """Test main function with invalid arguments."""
        with patch.object(sys, "argv", ["checker.py", "--invalid"]):
            with pytest.raises(SystemExit) as excinfo:
                main()

            # argparse exits with code 2 for invalid arguments
            assert excinfo.value.code == 2

    @patch("checker.ImportChecker")
    @patch("builtins.print")
    def test_main_prints_verbose_info(self, mock_print, mock_checker_class, tmp_path):
        """Test main function prints verbose information."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import os")

        mock_checker = MagicMock()
        mock_checker_class.return_value = mock_checker
        mock_checker.total_issues = 0

        with patch.object(sys, "argv", ["checker.py", "--check", "--verbose", str(test_file)]):
            result = main()

        assert result == 0

        # Check that verbose information was printed
        print_calls = [call[0][0] for call in mock_print.call_args_list]
        verbose_info_printed = any("Running in check mode" in call for call in print_calls)
        assert verbose_info_printed


class TestParseFailOn:
    """Unit tests for the unified --fail-on grammar parser."""

    def test_parses_severity_rule(self):
        assert parse_fail_on(["severity=high"]) == [("severity", "high")]

    def test_parses_count_rule(self):
        assert parse_fail_on(["count=5"]) == [("count", "5")]

    def test_parses_repeated_rules(self):
        assert parse_fail_on(["severity=low", "count=0"]) == [("severity", "low"), ("count", "0")]

    def test_empty_is_no_rules(self):
        assert parse_fail_on([]) == []

    @pytest.mark.parametrize(
        "bad",
        [
            "severity",  # no '='
            "severity=nope",  # not a ladder level
            "count=abc",  # not an int
            "count=-1",  # negative
            "bogus=high",  # unknown key
        ],
    )
    def test_bad_rule_raises(self, bad):
        with pytest.raises(ValueError):
            parse_fail_on([bad])


class TestParseRuleOverrides:
    """Unit tests for the repeatable --rule ID:SEVERITY override parser."""

    def test_parses_single_override(self):
        assert parse_rule_overrides(["pinned-versions:warn"]) == {"pinned-versions": "warn"}

    def test_parses_repeated_overrides(self):
        assert parse_rule_overrides(["pinned-versions:off", "valid-requirements:warn"]) == {
            "pinned-versions": "off",
            "valid-requirements": "warn",
        }

    def test_empty_is_no_overrides(self):
        assert parse_rule_overrides([]) == {}

    def test_severity_case_insensitive(self):
        assert parse_rule_overrides(["pinned-versions:WARN"]) == {"pinned-versions": "warn"}

    @pytest.mark.parametrize(
        "bad",
        [
            "pinned-versions",  # no ':'
            "pinned-versions:fatal",  # not error/warn/off
            "bogus:error",  # unknown rule id
        ],
    )
    def test_bad_override_raises(self, bad):
        with pytest.raises(ValueError):
            parse_rule_overrides([bad])


class TestGateTrips:
    """Unit tests for the --fail-on gate evaluation against raw findings."""

    # unused-import findings carry internal severity "error" -> ladder "high".
    _ERROR = [{"severity": "error"}]
    _WARNING = [{"severity": "warning"}]

    def test_no_rules_never_trips(self):
        assert gate_trips(self._ERROR, []) is False

    def test_severity_high_trips_on_error(self):
        assert gate_trips(self._ERROR, [("severity", "high")]) is True

    def test_severity_critical_does_not_trip_on_error(self):
        assert gate_trips(self._ERROR, [("severity", "critical")]) is False

    def test_severity_low_trips_on_warning(self):
        assert gate_trips(self._WARNING, [("severity", "low")]) is True

    def test_severity_high_does_not_trip_on_warning(self):
        assert gate_trips(self._WARNING, [("severity", "high")]) is False

    def test_count_trips_when_exceeded(self):
        assert gate_trips(self._ERROR * 3, [("count", "2")]) is True

    def test_count_does_not_trip_at_threshold(self):
        assert gate_trips(self._ERROR * 2, [("count", "2")]) is False

    def test_any_rule_trips(self):
        # critical won't trip, but count=0 will.
        assert gate_trips(self._ERROR, [("severity", "critical"), ("count", "0")]) is True


class TestFailOnEndToEnd:
    """End-to-end --fail-on behavior through main()."""

    def _clean_file(self, tmp_path):
        f = tmp_path / "clean.py"
        f.write_text("import os\nprint(os.getcwd())\n")
        return f

    def _unused_file(self, tmp_path):
        f = tmp_path / "dirty.py"
        f.write_text("import os\nimport sys\nprint(os.getcwd())\n")  # sys unused
        return f

    def test_fail_on_severity_high_trips_on_unused(self, tmp_path):
        f = self._unused_file(tmp_path)
        with patch.object(sys, "argv", ["checker.py", "--check", "--fail-on", "severity=high", str(f)]):
            assert main() == 1

    def test_fail_on_severity_high_passes_when_clean(self, tmp_path):
        f = self._clean_file(tmp_path)
        with patch.object(sys, "argv", ["checker.py", "--check", "--fail-on", "severity=high", str(f)]):
            assert main() == 0

    def test_fail_on_count_trips(self, tmp_path):
        f = self._unused_file(tmp_path)
        with patch.object(sys, "argv", ["checker.py", "--check", "--fail-on", "count=0", str(f)]):
            assert main() == 1

    def test_fail_on_count_passes_clean(self, tmp_path):
        f = self._clean_file(tmp_path)
        with patch.object(sys, "argv", ["checker.py", "--check", "--fail-on", "count=0", str(f)]):
            assert main() == 0

    def test_fail_on_repeatable(self, tmp_path):
        f = self._unused_file(tmp_path)
        argv = ["checker.py", "--check", "--fail-on", "severity=critical", "--fail-on", "count=0", str(f)]
        with patch.object(sys, "argv", argv):
            assert main() == 1

    def test_fail_on_escalates_cleanup_exit(self, tmp_path):
        # Cleanup mode normally returns 0; --fail-on escalates it to a finding
        # because the removed imports were recorded as findings.
        f = self._unused_file(tmp_path)
        with patch.object(sys, "argv", ["checker.py", "--cleanup", "--fail-on", "count=0", str(f)]):
            assert main() == 1

    def test_cleanup_without_fail_on_still_zero(self, tmp_path):
        f = self._unused_file(tmp_path)
        with patch.object(sys, "argv", ["checker.py", "--cleanup", str(f)]):
            assert main() == 0

    def test_bad_fail_on_value_is_usage_error(self, tmp_path):
        f = self._clean_file(tmp_path)
        with patch.object(sys, "argv", ["checker.py", "--check", "--fail-on", "severity=nope", str(f)]):
            with pytest.raises(SystemExit) as excinfo:
                main()
            # argparse usage errors exit with code 2.
            assert excinfo.value.code == 2
