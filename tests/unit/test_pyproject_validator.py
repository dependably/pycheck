"""Unit tests for the pyproject.toml validator."""

import os
import sys

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from validators import pyproject_validator  # noqa: E402
from validators.pyproject_validator import validate_pyproject  # noqa: E402

VALID = """
[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "sample-project"
version = "1.2.3"
license = "MIT"
requires-python = ">=3.9"
dependencies = ["requests==2.31.0", "click>=8.0"]

[project.optional-dependencies]
dev = ["pytest==7.4.0"]
"""


def _codes(result):
    return {e.code for e in result.errors}


class TestValidPyproject:
    def test_valid_passes(self):
        r = validate_pyproject(VALID)
        assert r.valid is True
        assert r.errors == []

    def test_accepts_parsed_dict(self):
        r = validate_pyproject({"project": {"name": "ok", "version": "1.0.0", "license": "MIT"}})
        assert r.valid is True


class TestInvalidPyproject:
    def test_invalid_name(self):
        r = validate_pyproject('[project]\nname = "bad name!"\nversion = "1.0.0"\nlicense="MIT"\n')
        assert "PP_INVALID_NAME" in _codes(r)

    def test_invalid_version(self):
        r = validate_pyproject('[project]\nname = "ok"\nversion = "1.0.x"\nlicense="MIT"\n')
        assert "PP_INVALID_VERSION" in _codes(r)

    def test_missing_name_and_version(self):
        r = validate_pyproject('[project]\nlicense = "MIT"\n')
        assert "PP_MISSING_NAME" in _codes(r)
        assert "PP_MISSING_VERSION" in _codes(r)

    def test_dynamic_version_allowed(self):
        r = validate_pyproject('[project]\nname = "ok"\ndynamic = ["version"]\nlicense="MIT"\n')
        assert "PP_MISSING_VERSION" not in _codes(r)

    def test_non_string_dependency(self):
        r = validate_pyproject('[project]\nname="ok"\nversion="1.0.0"\nlicense="MIT"\ndependencies=[42]\n')
        assert "PP_DEP_NOT_STRING" in _codes(r)

    def test_invalid_dependency_spec(self):
        r = validate_pyproject('[project]\nname="ok"\nversion="1.0.0"\nlicense="MIT"\ndependencies=["bad spec !!!"]\n')
        assert "PP_INVALID_DEP" in _codes(r)

    def test_invalid_requires_python(self):
        r = validate_pyproject('[project]\nname="ok"\nversion="1.0.0"\nlicense="MIT"\nrequires-python="3.9"\n')
        assert "PP_INVALID_REQUIRES_PYTHON" in _codes(r)

    def test_wrong_field_type(self):
        r = validate_pyproject('[project]\nname="ok"\nversion="1.0.0"\nlicense="MIT"\nkeywords="nope"\n')
        assert "PP_FIELD_TYPE" in _codes(r)

    def test_build_system_type(self):
        r = validate_pyproject(
            '[build-system]\nrequires = "setuptools"\n[project]\nname="ok"\nversion="1.0.0"\nlicense="MIT"\n'
        )
        assert "PP_BUILD_SYSTEM_TYPE" in _codes(r)

    def test_parse_error(self):
        r = validate_pyproject("this is not = valid toml [[[")
        assert "PP_PARSE" in _codes(r)


class TestWarnings:
    def test_missing_license_is_warning_not_error(self):
        r = validate_pyproject('[project]\nname = "ok"\nversion = "1.0.0"\n')
        assert r.valid is True
        assert any(w.code == "PP_MISSING_LICENSE" for w in r.warnings)

    def test_no_project_table_warns(self):
        r = validate_pyproject('[build-system]\nrequires = ["setuptools"]\n')
        assert any(w.code == "PP_NOT_TABLE" for w in r.warnings)


class TestSkipPath:
    def test_skips_when_tomllib_unavailable(self, monkeypatch):
        monkeypatch.setattr(pyproject_validator, "tomllib", None)
        r = validate_pyproject(VALID)
        assert r.valid is True
        assert r.info.get("skipped") is True

    def test_dict_still_validated_when_tomllib_unavailable(self, monkeypatch):
        monkeypatch.setattr(pyproject_validator, "tomllib", None)
        r = validate_pyproject({"project": {"name": "ok", "version": "1.0.0", "license": "MIT"}})
        assert r.info.get("skipped") is not True
        assert r.valid is True


class TestBuildSystemAndDynamicName:
    """#21: build-system.requires PEP 508 validation and dynamic-name rule."""

    def test_build_system_requires_pep508_validated(self):
        r = validate_pyproject(
            '[build-system]\nrequires = ["not a @@@ req"]\n[project]\nname="ok"\nversion="1.0.0"\nlicense="MIT"\n'
        )
        assert "PP_INVALID_DEP" in _codes(r)

    def test_build_system_requires_valid_ok(self):
        r = validate_pyproject(
            '[build-system]\nrequires = ["setuptools>=45", "wheel"]\n'
            '[project]\nname="ok"\nversion="1.0.0"\nlicense="MIT"\n'
        )
        assert "PP_INVALID_DEP" not in _codes(r)

    def test_dynamic_name_is_error(self):
        r = validate_pyproject('[project]\ndynamic = ["name", "version"]\nlicense="MIT"\n')
        assert "PP_DYNAMIC_NAME" in _codes(r)
        assert "PP_MISSING_NAME" in _codes(r)
