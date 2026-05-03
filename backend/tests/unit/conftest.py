"""Unit-test conftest – no DB, no Docker, no IO.

All fixtures here are pure in-memory objects or mocks.
"""

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        item.add_marker(pytest.mark.unit)
