"""Journey Guardian update coordinator."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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

    async def async_review_live_rail(
        self,
        *,
        decision_path: str = "transportapi_manual",
        urgent: bool = False,
    ) -> JourneySnapshot:
        """Run a quota-controlled provider review and publish its snapshot."""
        try:
            snapshot = await self.engine.async_review_live_rail(
                decision_path=decision_path,
                urgent=urgent,
            )
        except ValueError as err:
            raise HomeAssistantError(str(err)) from None
        self.async_set_updated_data(snapshot)
        return snapshot
