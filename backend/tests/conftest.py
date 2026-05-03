"""Root conftest – registers custom markers for selective test runs."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "unit: Unit-Tests ohne IO")
    config.addinivalue_line("markers", "integration: Integrationstests mit Postgres")
