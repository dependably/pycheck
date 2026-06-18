"""Unit tests for the shared validation contract (result.py)."""

import os
import sys

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from checker import ImportCheckerError  # noqa: E402
from validators.result import ValidationError, ValidationResult, ValidationWarning  # noqa: E402


class TestValidationResult:
    def test_default_is_valid_and_empty(self):
        r = ValidationResult()
        assert r.valid is True
        assert r.errors == []
        assert r.warnings == []
        assert r.info == {}

    def test_add_error_flips_valid(self):
        r = ValidationResult()
        r.add_error("boom", "CODE_X", line=5)
        assert r.valid is False
        assert len(r.errors) == 1
        err = r.errors[0]
        assert isinstance(err, ValidationError)
        assert err.code == "CODE_X"
        assert err.line == 5
        assert str(err) == "boom"

    def test_add_warning_keeps_valid(self):
        r = ValidationResult()
        r.add_warning("heads up", "WARN_X")
        assert r.valid is True
        assert len(r.warnings) == 1
        assert isinstance(r.warnings[0], ValidationWarning)
        assert r.warnings[0].code == "WARN_X"
        assert r.warnings[0].line is None


class TestValidationError:
    def test_is_import_checker_error(self):
        err = ValidationError("bad", "CODE", line=3)
        assert isinstance(err, ImportCheckerError)

    def test_repr_includes_code_and_line(self):
        err = ValidationError("bad thing", "CODE", line=7)
        assert "CODE" in repr(err)
        assert "line 7" in repr(err)
        assert "bad thing" in repr(err)
