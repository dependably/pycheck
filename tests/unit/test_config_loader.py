"""Unit tests for the shared ``.dependably-check`` config loader."""

import os
import sys

import pytest

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from checker import ImportCheckerError  # noqa: E402
from validators.config import resolve_allowed_hosts  # noqa: E402


def _write(path, text):
    path.write_text(text, encoding="utf-8")


class TestDiscovery:
    def test_walk_up_finds_config(self, tmp_path):
        _write(
            tmp_path / ".dependably-check",
            '{"common": {"allowedRegistryHosts": ["dependably.northwardlabs.ca"]}}',
        )
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        hosts = resolve_allowed_hosts(target=nested)
        assert hosts == ["dependably.northwardlabs.ca"]

    def test_union_of_common_and_python(self, tmp_path):
        _write(
            tmp_path / ".dependably-check",
            """
            {
              "common": {"allowedRegistryHosts": ["common.example.com"]},
              "python": {"allowedRegistryHosts": ["py.example.com"]}
            }
            """,
        )
        hosts = resolve_allowed_hosts(target=tmp_path)
        assert set(hosts) == {"common.example.com", "py.example.com"}

    def test_other_sections_ignored(self, tmp_path):
        _write(
            tmp_path / ".dependably-check",
            """
            {
              "common": {"allowedRegistryHosts": ["common.example.com"]},
              "npm": {"allowedRegistryHosts": ["npm.example.com"]},
              "unknownKey": 42
            }
            """,
        )
        hosts = resolve_allowed_hosts(target=tmp_path)
        assert hosts == ["common.example.com"]

    def test_missing_sections_return_empty(self, tmp_path):
        _write(tmp_path / ".dependably-check", "{}")
        assert resolve_allowed_hosts(target=tmp_path) == []

    def test_no_config_returns_empty(self, tmp_path):
        assert resolve_allowed_hosts(target=tmp_path) == []

    def test_walk_stops_at_git_root(self, tmp_path):
        # Config above the repo root must not be discovered.
        _write(tmp_path / ".dependably-check", '{"common": {"allowedRegistryHosts": ["above.example.com"]}}')
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        nested = repo / "src"
        nested.mkdir()
        assert resolve_allowed_hosts(target=nested) == []

    def test_config_at_git_root_is_honoured(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        _write(repo / ".dependably-check", '{"python": {"allowedRegistryHosts": ["repo.example.com"]}}')
        nested = repo / "src" / "pkg"
        nested.mkdir(parents=True)
        assert resolve_allowed_hosts(target=nested) == ["repo.example.com"]


class TestExplicitPath:
    def test_explicit_config_wins(self, tmp_path):
        # A discoverable config in the target dir is ignored when --config is given.
        _write(tmp_path / ".dependably-check", '{"common": {"allowedRegistryHosts": ["discovered.example.com"]}}')
        explicit = tmp_path / "custom.json"
        _write(explicit, '{"common": {"allowedRegistryHosts": ["explicit.example.com"]}}')
        hosts = resolve_allowed_hosts(target=tmp_path, config_path=explicit)
        assert hosts == ["explicit.example.com"]

    def test_missing_explicit_path_raises(self, tmp_path):
        with pytest.raises(ImportCheckerError):
            resolve_allowed_hosts(target=tmp_path, config_path=tmp_path / "nope.json")


class TestMalformed:
    def test_malformed_json_raises_with_path(self, tmp_path):
        bad = tmp_path / ".dependably-check"
        _write(bad, "{not valid json")
        with pytest.raises(ImportCheckerError) as exc:
            resolve_allowed_hosts(target=tmp_path)
        assert str(bad) in str(exc.value)

    def test_non_object_top_level_raises(self, tmp_path):
        _write(tmp_path / ".dependably-check", "[1, 2, 3]")
        with pytest.raises(ImportCheckerError):
            resolve_allowed_hosts(target=tmp_path)

    def test_non_array_allowed_hosts_raises(self, tmp_path):
        _write(tmp_path / ".dependably-check", '{"common": {"allowedRegistryHosts": "host"}}')
        with pytest.raises(ImportCheckerError):
            resolve_allowed_hosts(target=tmp_path)
