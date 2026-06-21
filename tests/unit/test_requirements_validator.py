"""Unit tests for the requirements.txt validator."""

import os
import sys

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from validators.requirements_validator import SECURITY_CODES, validate_requirements  # noqa: E402


def _error_codes(result):
    return {e.code for e in result.errors}


def _warning_codes(result):
    return {w.code for w in result.warnings}


class TestRequirements:
    def test_valid_pinned_clean(self):
        r = validate_requirements("requests==2.31.0\nclick==8.1.7\n")
        assert r.valid is True
        assert r.warnings == []

    def test_unpinned_warns(self):
        r = validate_requirements("requests>=2.0\n")
        assert "REQ_UNPINNED" in _warning_codes(r)

    def test_invalid_line_errors(self):
        r = validate_requirements("this is not valid !!!\n")
        assert "REQ_INVALID" in _error_codes(r)

    def test_comment_and_blank_ignored(self):
        r = validate_requirements("# a comment\n\nrequests==2.0\n")
        assert r.valid is True
        assert r.info["requirements"] == 1

    def test_marker_not_flagged_unpinned(self):
        r = validate_requirements("typing-extensions; python_version < '3.10'\n")
        assert "REQ_UNPINNED" not in _warning_codes(r)


class TestSecurity:
    def test_trusted_host_always_error(self):
        r = validate_requirements("--trusted-host example.com\n")
        assert "REQ_TRUSTED_HOST" in _error_codes(r)

    def test_creds_in_index_url_error(self):
        r = validate_requirements("--index-url https://user:secret@pypi.example.com/simple\n")
        assert "REQ_PLAINTEXT_SECRET" in _error_codes(r)

    def test_http_index_warns(self):
        r = validate_requirements("--index-url http://pypi.example.com/simple\n")
        assert "REQ_INSECURE_INDEX" in _warning_codes(r)

    def test_security_codes_exposed(self):
        assert SECURITY_CODES == {"REQ_PLAINTEXT_SECRET", "REQ_TRUSTED_HOST", "REQ_UNTRUSTED_INDEX"}


class TestIndexTrust:
    def test_private_index_url_without_allowlist_errors(self):
        r = validate_requirements("--index-url https://nexus.corp.local/simple\n")
        assert "REQ_UNTRUSTED_INDEX" in _error_codes(r)
        assert r.valid is False

    def test_private_index_url_with_allowlist_ok(self):
        r = validate_requirements(
            "--index-url https://nexus.corp.local/simple\n",
            allowed_hosts=["nexus.corp.local"],
        )
        assert "REQ_UNTRUSTED_INDEX" not in _error_codes(r)

    def test_extra_index_url_private_flagged(self):
        r = validate_requirements("--extra-index-url https://mirror.example.com/simple\n")
        assert "REQ_UNTRUSTED_INDEX" in _error_codes(r)

    def test_public_index_not_flagged(self):
        r = validate_requirements("--index-url https://pypi.org/simple\n")
        assert "REQ_UNTRUSTED_INDEX" not in _error_codes(r)

    def test_url_requirement_not_flagged_as_index(self):
        # A direct package URL is not an index option; it must not trip the
        # untrusted-index check.
        r = validate_requirements("https://example.com/wheels/foo-1.0-py3-none-any.whl\n")
        assert "REQ_UNTRUSTED_INDEX" not in _error_codes(r)


class TestLineNumbers:
    def test_error_line_number(self):
        r = validate_requirements("requests==2.0\n--trusted-host example.com\n")
        trusted = [e for e in r.errors if e.code == "REQ_TRUSTED_HOST"]
        assert trusted and trusted[0].line == 2
