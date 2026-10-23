"""Serve only the public card code; itinerary data stays in authenticated HA."""

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

CARD_URL = "/journey_guardian/journey-guardian-card.js"
CARD_FILE = Path(__file__).parent / "frontend" / "journey-guardian-card.js"
_REGISTERED = "journey_guardian_card_registered"


async def async_register_card(hass: HomeAssistant) -> None:
    """Register a single packaged file, once per HA process, never a directory."""
    if "http" not in hass.config.components or hass.data.get(_REGISTERED):
        return
    await hass.http.async_register_static_paths([
        StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)
    ])
    hass.data[_REGISTERED] = True
