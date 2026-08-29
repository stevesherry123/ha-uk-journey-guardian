"""Journey Guardian decision engine."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .budget import TransportAPIBudget
from .const import DEFAULT_LOOKAHEAD_HOURS
from .journey import select_next_journey
from .models import JourneySnapshot

_LOGGER = logging.getLogger(__name__)


class JourneyGuardianEngine:
    """Read journey inputs and produce one normalized decision snapshot."""

    def __init__(
        self,
        hass: HomeAssistant,
        calendar_entity: str,
        budget: TransportAPIBudget,
    ) -> None:
        """Initialize the engine."""
        self._hass = hass
        self._calendar_entity = calendar_entity
        self._budget = budget

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
            return JourneySnapshot(
                status=status,
                checked_at=checked_at,
                next_journey=next_journey,
                budget=self._budget.snapshot(),
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
