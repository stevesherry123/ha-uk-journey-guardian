"""Home Assistant fixtures for Journey Guardian tests."""

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.fixture
def hass_config_dir() -> str:
    """Use the repository root as Home Assistant's test config directory."""
    return str(ROOT)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load integrations from custom_components."""
    yield
