"""Unit tests for the pip.conf validator."""

import os
import sys

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from validators.pip_conf_validator import SECURITY_CODES, validate_pip_conf  # noqa: E402


def _error_codes(result):
    return {e.code for e in result.errors}


def _warning_codes(result):
    return {w.code for w in result.warnings}


class TestSecurity:
    def test_trusted_host_is_always_error(self):
        r = validate_pip_conf("[global]\ntrusted-host = example.com\n")
        assert "PIP_TRUSTED_HOST" in _error_codes(r)
        assert r.valid is False

    def test_plaintext_credentials_error(self):
        r = validate_pip_conf("[global]\nindex-url = https://user:secret@pypi.example.com/simple\n")
        assert "PIP_PLAINTEXT_SECRET" in _error_codes(r)

    def test_env_ref_credentials_ok(self):
        r = validate_pip_conf("[global]\nindex-url = https://${PIP_USER}:${PIP_PASS}@pypi.example.com/simple\n")
        assert "PIP_PLAINTEXT_SECRET" not in _error_codes(r)

    def test_security_codes_exposed(self):
        assert "PIP_TRUSTED_HOST" in SECURITY_CODES
        assert "PIP_PLAINTEXT_SECRET" in SECURITY_CODES

    def test_secret_is_redacted_in_message(self):
        r = validate_pip_conf("[global]\nindex-url = https://user:supersecret@pypi.example.com/simple\n")
        assert all("supersecret" not in str(e) for e in r.errors)


class TestIndexTrust:
    def test_private_index_without_allowlist_errors(self):
        r = validate_pip_conf("[global]\nindex-url = https://nexus.corp.local/simple\n")
        assert "PIP_UNTRUSTED_INDEX" in _error_codes(r)
        assert r.valid is False

    def test_private_index_with_allowlist_ok(self):
        r = validate_pip_conf(
            "[global]\nindex-url = https://nexus.corp.local/simple\n",
            allowed_hosts=["nexus.corp.local"],
        )
        assert "PIP_UNTRUSTED_INDEX" not in _error_codes(r)
        assert r.valid is True

    def test_public_pypi_index_not_flagged(self):
        r = validate_pip_conf("[global]\nindex-url = https://pypi.org/simple\n")
        assert "PIP_UNTRUSTED_INDEX" not in _error_codes(r)

    def test_public_pythonhosted_not_flagged(self):
        r = validate_pip_conf("[global]\nextra-index-url = https://files.pythonhosted.org/simple\n")
        assert "PIP_UNTRUSTED_INDEX" not in _error_codes(r)

    def test_extra_index_url_private_flagged(self):
        r = validate_pip_conf("[global]\nextra-index-url = https://mirror.example.com/simple\n")
        assert "PIP_UNTRUSTED_INDEX" in _error_codes(r)

    def test_allowlist_is_case_insensitive(self):
        r = validate_pip_conf(
            "[global]\nindex-url = https://Nexus.Corp.Local/simple\n",
            allowed_hosts=["nexus.corp.local"],
        )
        assert "PIP_UNTRUSTED_INDEX" not in _error_codes(r)

    def test_untrusted_index_in_security_codes(self):
        assert "PIP_UNTRUSTED_INDEX" in SECURITY_CODES


class TestWarnings:
    def test_http_index_is_warning(self):
        r = validate_pip_conf("[global]\nindex-url = http://pypi.example.com/simple\n")
        assert "PIP_INSECURE_INDEX" in _warning_codes(r)

    def test_unknown_key_warns(self):
        r = validate_pip_conf("[global]\nbogus-key = 1\n")
        assert "PIP_UNKNOWN_KEY" in _warning_codes(r)

    def test_valid_config_clean(self):
        r = validate_pip_conf("[global]\nindex-url = https://pypi.org/simple\ntimeout = 60\n")
        assert r.valid is True
        assert r.warnings == []


class TestLineNumbers:
    def test_line_numbers_reported(self):
        content = "[global]\nindex-url = https://pypi.org/simple\ntrusted-host = example.com\n"
        r = validate_pip_conf(content)
        trusted = [e for e in r.errors if e.code == "PIP_TRUSTED_HOST"]
        assert trusted and trusted[0].line == 3

    def test_colon_syntax_line_numbers(self):
        content = "[global]\ntrusted-host: example.com\n"
        r = validate_pip_conf(content)
        trusted = [e for e in r.errors if e.code == "PIP_TRUSTED_HOST"]
        assert trusted and trusted[0].line == 2
