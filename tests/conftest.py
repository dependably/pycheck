"""Pytest configuration for the test suite.

The ``tests/fixtures`` directory contains sample Python files used as *input
data* for the import checker. Several of them are named ``test_*.py`` (and some
intentionally import third-party modules such as ``numpy``), so pytest would
otherwise try to import them as test modules and fail during collection. They
are read as text by the integration tests, never imported, so exclude them.
"""

collect_ignore_glob = ["fixtures/*"]
