"""Home Assistant fixtures for Journey Guardian tests."""

from pathlib import Path

import pytest

import custom_components

ROOT = Path(__file__).parents[1]
CUSTOM_COMPONENTS_PATH = str(ROOT / "custom_components")

# `pip install .[test]` can import the built package before Home Assistant mounts
# the checkout. Ensure the loader always scans the source under test first.
if CUSTOM_COMPONENTS_PATH not in custom_components.__path__:
    custom_components.__path__.insert(0, CUSTOM_COMPONENTS_PATH)


@pytest.fixture
def hass_config_dir() -> str:
    """Use the repository root as Home Assistant's test config directory."""
    return str(ROOT)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load integrations from custom_components."""
    yield
