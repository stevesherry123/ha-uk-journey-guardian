"""Home Assistant fixtures for Journey Guardian tests."""

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.fixture
def hass_config_dir(tmp_path: Path) -> str:
    """Expose Journey Guardian inside Home Assistant's test config directory."""
    components = tmp_path / "custom_components"
    components.mkdir()
    (components / "journey_guardian").symlink_to(
        ROOT / "custom_components/journey_guardian",
        target_is_directory=True,
    )
    return str(tmp_path)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load integrations from custom_components."""
    yield
