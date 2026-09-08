"""Automatic station-access refreshes as departure approaches."""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .coordinator import JourneyGuardianCoordinator

_LOGGER = logging.getLogger(__name__)

CHECKPOINT_MINUTES = (360, 120, 45, 15)


class StationAccessMonitor:
    """Refresh the live route at a bounded set of useful checkpoints."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: JourneyGuardianCoordinator,
    ) -> None:
        """Initialize the monitor."""
        self._hass = hass
        self._coordinator = coordinator
        self._checkpoint_cancellers: list[Callable[[], None]] = []
        self._remove_listener: Callable[[], None] | None = None

    @callback
    def start(self) -> None:
        """Listen for journey changes and schedule future checkpoints."""
        self._remove_listener = self._coordinator.async_add_listener(
            self._handle_coordinator_update
        )
        self._handle_coordinator_update()

    @callback
    def stop(self) -> None:
        """Cancel all listeners and future checkpoints."""
        self._cancel_checkpoints()
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Rebuild checkpoints for the current planned journey."""
        self._cancel_checkpoints()
        self._coordinator.next_station_access_check_at = None
        snapshot = self._coordinator.data
        journey = snapshot.next_journey
        if (
            journey is None
            or snapshot.simulation_active
            or snapshot.status in {"active", "cancelled"}
            or not self._coordinator.engine.station_access_configured
        ):
            return

        now = dt_util.now()
        future_points: list[datetime] = []
        for lead_minutes in CHECKPOINT_MINUTES:
            point = journey.start - timedelta(minutes=lead_minutes)
            if point <= now:
                continue
            future_points.append(point)
            self._checkpoint_cancellers.append(
                async_track_point_in_utc_time(
                    self._hass,
                    functools.partial(
                        self._async_checkpoint_reached,
                        departure=journey.start,
                    ),
                    point,
                )
            )
        if future_points:
            self._coordinator.next_station_access_check_at = min(future_points)

    @callback
    def _cancel_checkpoints(self) -> None:
        for cancel in self._checkpoint_cancellers:
            cancel()
        self._checkpoint_cancellers.clear()

    async def _async_checkpoint_reached(
        self,
        _reached_at: datetime,
        departure: datetime,
    ) -> None:
        """Force a fresh route if this is still the selected journey."""
        current = self._coordinator.data.next_journey
        if current is None or current.start != departure:
            return
        try:
            await self._coordinator.async_test_station_access()
        except Exception as err:  # Errors are sanitized in coordinator data.
            _LOGGER.warning(
                "Automatic station access check failed with %s",
                type(err).__name__,
            )
