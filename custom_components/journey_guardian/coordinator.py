"""Journey Guardian update coordinator."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEFAULT_UPDATE_INTERVAL, NAME
from .engine import JourneyGuardianEngine
from .models import JourneySnapshot

_LOGGER = logging.getLogger(__name__)


class JourneyGuardianCoordinator(DataUpdateCoordinator[JourneySnapshot]):
    """Coordinate calendar reviews and entity updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        engine: JourneyGuardianEngine,
    ) -> None:
        """Initialize the coordinator."""
        self.engine = engine
        super().__init__(
            hass,
            logger=_LOGGER,
            config_entry=entry,
            name=NAME,
            update_interval=DEFAULT_UPDATE_INTERVAL,
            always_update=False,
        )

    async def _async_update_data(self) -> JourneySnapshot:
        """Return the latest normalized journey state."""
        return await self.engine.async_review()
