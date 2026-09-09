"""Restart-safe storage for the latest privacy-safe rail observation."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .models import JourneySnapshot, RailObservation

STORAGE_KEY = "journey_guardian.live_evidence"
STORAGE_VERSION = 1


class LiveEvidenceStore:
    """Persist one provider observation without calendar text."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] | None = None

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        self._data = stored if isinstance(stored, dict) else None

    async def async_save(self, snapshot: JourneySnapshot) -> None:
        journey, observation = snapshot.next_journey, snapshot.rail_observation
        if journey is None or observation is None or observation.retained:
            return
        await self._store.async_save(
            {
                "departure": journey.start.isoformat(),
                "journey_hash": _hash(journey.summary),
                "observation": observation.as_dict(),
            }
        )
        self._data = None

    def restore(self, snapshot: JourneySnapshot) -> RailObservation | None:
        journey, data = snapshot.next_journey, self._data
        if (
            journey is None
            or data is None
            or data.get("departure") != journey.start.isoformat()
            or data.get("journey_hash") != _hash(journey.summary)
        ):
            return None
        raw = data.get("observation")
        if not isinstance(raw, dict):
            return None
        try:
            return RailObservation(
                scenario=str(raw["scenario"]),
                source=str(raw["source"]),
                classification=str(raw["classification"]),
                observed_at=datetime.fromisoformat(str(raw["observed_at"])),
                scheduled_departure=datetime.fromisoformat(
                    str(raw["scheduled_departure"])
                ),
                predicted_departure=(
                    datetime.fromisoformat(str(raw["predicted_departure"]))
                    if raw.get("predicted_departure")
                    else None
                ),
                delay_minutes=int(raw["delay_minutes"]),
                cancelled=bool(raw["cancelled"]),
                leg_count=int(raw["leg_count"]),
                provider_available=bool(raw["provider_available"]),
                freshness=str(raw.get("freshness", "current")),
                age_seconds=int(raw.get("age_seconds", 0)),
                service_identity=raw.get("service_identity"),
                platform=raw.get("platform"),
                match_quality=str(raw.get("match_quality", "not_applicable")),
                schedule_offset_minutes=int(raw.get("schedule_offset_minutes", 0)),
            )
        except KeyError, TypeError, ValueError:
            return None


def _hash(summary: str) -> str:
    return hashlib.sha256(summary.encode()).hexdigest()[:24]
