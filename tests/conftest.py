"""Pytest-Fixtures für die Frickelalarm-Tests."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Eigene Integration in allen Tests ladbar machen."""
    yield
