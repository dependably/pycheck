"""Unit tests for the pragmatic PEP 508 / PEP 440 helpers."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest  # noqa: E402

from validators._pep508 import (  # noqa: E402
    is_valid_pep508,
    is_valid_version,
)


@pytest.mark.parametrize(
    "version",
    [
        "1.0",
        "1.0.0",
        "2.3.4",
        "1!2.0",
        "1.0rc1",
        "1.0.post1",
        "1.0.dev1",
        "1.0+abc",
        # #20: separator spellings PEP 440 permits
        "1.0.a1",
        "1.0-alpha1",
        "1.0.rev1",
        "1.0-dev1",
        "1.0+ubuntu-1",
        "1.0-1",  # implicit post release
    ],
)
def test_valid_versions(version):
    assert is_valid_version(version)


@pytest.mark.parametrize("version", ["1.0.x", "not-a-version", "1..0", "", "abc"])
def test_invalid_versions(version):
    assert not is_valid_version(version)


@pytest.mark.parametrize(
    "req",
    [
        "requests",
        "requests==2.31.0",
        "requests>=2.0,<3.0",
        "requests[security]>=2.0",
        "name @ https://example.com/x.whl",
        "requests; python_version >= '3.9'",
        "requests (>=2.0)",  # #20: parenthesized specifiers
    ],
)
def test_valid_requirements(req):
    assert is_valid_pep508(req)


@pytest.mark.parametrize("req", ["foo-==1.0", "bad spec !!!", "== 1.0", ""])
def test_invalid_requirements(req):
    assert not is_valid_pep508(req)
