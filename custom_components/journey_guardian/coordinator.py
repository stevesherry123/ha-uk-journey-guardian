"""Journey Guardian update coordinator."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime

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
        self.last_live_check_at: datetime | None = None
        self.next_live_check_at: datetime | None = None
        self.last_station_access_test_at: datetime | None = None
        self.next_station_access_check_at: datetime | None = None
        self.last_notification: str | None = None
        self.last_notification_at: datetime | None = None
        self._last_live_snapshot: JourneySnapshot | None = None
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
        snapshot = await self.engine.async_review()
        previous = self._last_live_snapshot
        if (
            previous is not None
            and snapshot.status == "active"
            and snapshot.next_journey is not None
            and previous.next_journey is not None
            and previous.rail_observation is not None
            and snapshot.next_journey.start == previous.next_journey.start
            and snapshot.next_journey.summary == previous.next_journey.summary
        ):
            age_seconds = max(
                0,
                int(
                    (
                        snapshot.checked_at
                        - previous.rail_observation.observed_at
                    ).total_seconds()
                ),
            )
            snapshot = replace(
                snapshot,
                next_journey=previous.next_journey,
                rail_observation=replace(
                    previous.rail_observation,
                    freshness="historical",
                    age_seconds=age_seconds,
                    retained=True,
                ),
            )
        return snapshot

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
        self.last_live_check_at = snapshot.checked_at
        if snapshot.rail_observation is not None:
            self._last_live_snapshot = snapshot
        self.async_set_updated_data(snapshot)
        return snapshot

    async def async_test_station_access(self) -> JourneySnapshot:
        """Force one station-access request and publish the result."""
        snapshot = await self.engine.async_review(force_station_access=True)
        self.last_station_access_test_at = snapshot.checked_at
        self.async_set_updated_data(snapshot)
        return snapshot

    def record_notification(self, kind: str, sent_at: datetime) -> None:
        """Record privacy-safe notification diagnostics."""
        self.last_notification = kind
        self.last_notification_at = sent_at
