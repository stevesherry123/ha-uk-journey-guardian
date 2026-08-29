"""Journey Guardian decision engine."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .budget import TransportAPIBudget
from .const import (
    DEFAULT_EARLY_WARNING_MINUTES,
    DEFAULT_LOOKAHEAD_HOURS,
    DEFAULT_PREPARATION_BUFFER_MINUTES,
    DEFAULT_STATION_ACCESS_FALLBACK_MINUTES,
    DEFAULT_STATION_BUFFER_MINUTES,
)
from .journey import select_next_journey
from .models import JourneySnapshot
from .timing import calculate_fallback_timing

_LOGGER = logging.getLogger(__name__)


class JourneyGuardianEngine:
    """Read journey inputs and produce one normalized decision snapshot."""

    def __init__(
        self,
        hass: HomeAssistant,
        calendar_entity: str,
        budget: TransportAPIBudget,
        preparation_buffer_minutes: int = DEFAULT_PREPARATION_BUFFER_MINUTES,
        early_warning_minutes: int = DEFAULT_EARLY_WARNING_MINUTES,
        station_buffer_minutes: int = DEFAULT_STATION_BUFFER_MINUTES,
        station_access_fallback_minutes: int = (
            DEFAULT_STATION_ACCESS_FALLBACK_MINUTES
        ),
    ) -> None:
        """Initialize the engine."""
        self._hass = hass
        self._calendar_entity = calendar_entity
        self._budget = budget
        self._preparation_buffer_minutes = preparation_buffer_minutes
        self._early_warning_minutes = early_warning_minutes
        self._station_buffer_minutes = station_buffer_minutes
        self._station_access_fallback_minutes = station_access_fallback_minutes

    async def async_review(self) -> JourneySnapshot:
        """Review the next calendar journey without consuming rail API quota."""
        checked_at = dt_util.now()
        try:
            events = await self._async_calendar_events(checked_at)
            next_journey = select_next_journey(events, checked_at)
            if next_journey is None:
                status = "idle"
            elif next_journey.start <= checked_at:
                status = "active"
            else:
                status = "planned"
            timing = (
                calculate_fallback_timing(
                    next_journey,
                    preparation_minutes=self._preparation_buffer_minutes,
                    early_warning_minutes=self._early_warning_minutes,
                    station_buffer_minutes=self._station_buffer_minutes,
                    station_access_minutes=self._station_access_fallback_minutes,
                )
                if next_journey is not None
                else None
            )
            return JourneySnapshot(
                status=status,
                checked_at=checked_at,
                next_journey=next_journey,
                budget=self._budget.snapshot(),
                timing=timing,
            )
        except Exception as err:  # Home Assistant service errors vary by provider
            # Exception messages from calendars and future provider clients may
            # contain entity IDs, event details, URLs, or credentials. Preserve
            # only a stable public category in coordinator data.
            _LOGGER.warning(
                "Calendar review failed with %s", type(err).__name__
            )
            return JourneySnapshot(
                status="error",
                checked_at=checked_at,
                next_journey=None,
                budget=self._budget.snapshot(),
                error="calendar_unavailable",
            )

    async def _async_calendar_events(self, start: Any) -> list[dict[str, Any]]:
        end = start + timedelta(hours=DEFAULT_LOOKAHEAD_HOURS)
        response = await self._hass.services.async_call(
            "calendar",
            "get_events",
            {
                "entity_id": self._calendar_entity,
                "start_date_time": start.isoformat(),
                "end_date_time": end.isoformat(),
            },
            blocking=True,
            return_response=True,
        )
        calendar_data = response.get(self._calendar_entity, {})
        events = calendar_data.get("events", [])
        return list(events) if isinstance(events, list) else []
