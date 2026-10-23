"""Bounded local flight context, separate from rail evidence and automation."""

from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .flight import (
    FlightLeg,
    flight_projection,
    parse_flights,
    restore_flight,
    retain_connection_context,
)


class FlightCalendarPreview:
    """Keep a connection's earlier scheduled leg through a Home Assistant reload."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, zones: dict[str, str]
    ) -> None:
        self._store = Store(
            hass, 1, f"journey_guardian.flight_preview.{entry_id}", private=True
        )
        self._zones = zones
        self._legs: tuple[FlightLeg, ...] = ()
        self._storage_error = False

    async def async_load(self) -> None:
        try:
            data = await self._store.async_load()
        except Exception:
            # An optional shadow module must not prevent rail startup.
            self._storage_error = True
            return
        if not isinstance(data, dict) or not isinstance(data.get("legs"), list):
            return
        self._legs = tuple(
            leg
            for row in data["legs"][:12]
            if isinstance(row, dict)
            and (leg := restore_flight(row, dt_util.now())) is not None
        )

    async def async_review(self, events: list[dict], now: datetime) -> dict:
        current, rejected = parse_flights(events, now)
        legs = retain_connection_context(current, self._legs, now)
        projection = flight_projection(legs, now, self._zones, rejected)
        bounded = legs[:12]
        if bounded != self._legs or self._storage_error:
            try:
                await self._store.async_save(
                    {"legs": [leg.as_dict() for leg in bounded]}
                )
                self._storage_error = False
            except Exception:
                self._storage_error = True
            self._legs = bounded
        projection["context_persistence_error"] = self._storage_error
        return projection
