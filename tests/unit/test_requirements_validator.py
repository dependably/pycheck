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

    def test_unpinned_errors_by_default(self):
        # pinned-versions is error by default (suite parity with npm-check);
        # a .dependably rules override is what downgrades it, not the validator.
        r = validate_requirements("requests>=2.0\n")
        assert "REQ_UNPINNED" in _error_codes(r)
        assert r.valid is False

    def test_invalid_line_errors(self):
        r = validate_requirements("this is not valid !!!\n")
        assert "REQ_INVALID" in _error_codes(r)

    def test_comment_and_blank_ignored(self):
        r = validate_requirements("# a comment\n\nrequests==2.0\n")
        assert r.valid is True
        assert r.info["requirements"] == 1

    def test_marker_bearing_unpinned_still_flagged(self):
        # A marker must not exempt a genuinely unpinned dependency.
        r = validate_requirements("typing-extensions; python_version < '3.10'\n")
        assert "REQ_UNPINNED" in _error_codes(r)

    def test_marker_bearing_pinned_not_flagged(self):
        # The `==` lives in the requirement, so it is pinned -> no finding.
        r = validate_requirements("typing-extensions==4.0; python_version < '3.10'\n")
        assert "REQ_UNPINNED" not in _error_codes(r)

    def test_marker_internal_equals_not_treated_as_pin(self):
        # `==` inside the marker must NOT count as a version pin.
        r = validate_requirements("typing-extensions; python_version == '3.9'\n")
        assert "REQ_UNPINNED" in _error_codes(r)


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


class TestHashPinnedAndOptions:
    """#18: hash-pinned files and per-requirement options are valid."""

    def test_backslash_continued_hash_valid(self):
        # Exactly what `pip-compile --generate-hashes` emits.
        r = validate_requirements("foo==1.0 \\\n    --hash=sha256:aaaa\n")
        assert "REQ_INVALID" not in _error_codes(r)
        assert r.info["requirements"] == 1

    def test_inline_per_requirement_option_valid(self):
        r = validate_requirements("FooProject == 1.2 --hash=sha256:aaaa\n")
        assert "REQ_INVALID" not in _error_codes(r)

    def test_multiple_hashes_continued(self):
        r = validate_requirements("foo==1.0 \\\n    --hash=sha256:aaaa \\\n    --hash=sha256:bbbb\n")
        assert "REQ_INVALID" not in _error_codes(r)

    def test_tab_separated_comment_stripped(self):
        r = validate_requirements("foo==1.0\t# pinned\n")
        assert "REQ_INVALID" not in _error_codes(r)

    def test_url_egg_fragment_not_treated_as_comment(self):
        r = validate_requirements("git+https://example.com/repo.git#egg=foo\n")
        # The `#egg=` fragment must survive; no bogus parse error.
        assert "REQ_INVALID" not in _error_codes(r)

    def test_continued_line_number_points_at_first_line(self):
        r = validate_requirements("requests==2.0\nfoo bar baz \\\n    qux\n")
        invalid = [e for e in r.errors if e.code == "REQ_INVALID"]
        assert invalid and invalid[0].line == 2


class TestEditableCredentialScanning:
    """#19: `-e`/`--editable` VCS URLs are credential-scanned."""

    def test_editable_plaintext_credential_flagged(self):
        r = validate_requirements("-e git+https://user:secret@internal.example.com/repo.git#egg=foo\n")
        assert "REQ_PLAINTEXT_SECRET" in _error_codes(r)

    def test_long_editable_flag_flagged(self):
        r = validate_requirements("--editable git+https://user:secret@host.example.com/repo.git#egg=foo\n")
        assert "REQ_PLAINTEXT_SECRET" in _error_codes(r)

    def test_editable_ssh_git_user_not_flagged(self):
        # `git@host` in an SSH URL is the standard secret-free convention.
        r = validate_requirements("-e git+ssh://git@github.com/org/repo.git#egg=foo\n")
        assert "REQ_PLAINTEXT_SECRET" not in _error_codes(r)

    def test_plain_ssh_git_user_not_flagged(self):
        r = validate_requirements("git+ssh://git@github.com/org/repo.git#egg=foo\n")
        assert "REQ_PLAINTEXT_SECRET" not in _error_codes(r)

    def test_editable_env_ref_credential_ok(self):
        r = validate_requirements("-e git+https://${TOKEN}@host.example.com/repo.git#egg=foo\n")
        assert "REQ_PLAINTEXT_SECRET" not in _error_codes(r)
