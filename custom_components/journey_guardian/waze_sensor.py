"""Read an explicitly selected local Waze duration without exposing its route."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .google_routes import StationAccessEstimate

MAX_SENSOR_AGE = timedelta(minutes=15)


class WazeSensorError(ValueError):
    """A stable category, never an entity ID, address or provider response."""


async def async_waze_estimate(
    hass: HomeAssistant, entity_id: str, *, now: datetime, force_refresh: bool = False
) -> StationAccessEstimate:
    """Use the HA sensor's minutes and bounded freshness, not a new Waze client."""
    if force_refresh:
        try:
            async with asyncio.timeout(20):
                await hass.services.async_call(
                    "homeassistant",
                    "update_entity",
                    {"entity_id": entity_id},
                    blocking=True,
                )
        except HomeAssistantError, TimeoutError:
            raise WazeSensorError("refresh_failed") from None
        now = dt_util.now()
    state = hass.states.get(entity_id)
    if state is None:
        raise WazeSensorError("sensor_missing")
    if state.state in {"unknown", "unavailable"} or state.attributes.get("restored"):
        raise WazeSensorError("sensor_unavailable")
    observed = state.last_reported
    if not timedelta(0) <= now - observed <= MAX_SENSOR_AGE:
        raise WazeSensorError("sensor_stale")
    if state.attributes.get("unit_of_measurement") != "min":
        raise WazeSensorError("sensor_invalid")
    try:
        minutes = float(state.state)
        if not math.isfinite(minutes) or not 0 < minutes <= 240:
            raise ValueError("invalid_duration")
    except TypeError, ValueError, OverflowError:
        raise WazeSensorError("sensor_invalid") from None
    return StationAccessEstimate(
        duration_minutes=math.ceil(minutes),
        distance_meters=None,
        mode="driving",
        observed_at=observed,
    )
