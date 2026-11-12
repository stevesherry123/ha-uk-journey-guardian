"""Bounded restart recovery for booked intent and earlier rail evidence."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .journey import is_rail_candidate
from .models import JourneyEvent, JourneySnapshot, RailObservation

STORAGE_KEY = "journey_guardian.live_evidence"
STORAGE_VERSION = 1
# Keep the HA envelope readable by older releases; migrate the inner schema.
SCHEMA_VERSION = 2
MAX_OBSERVATION_AGE = timedelta(hours=6)
MAX_JOURNEY_DURATION = timedelta(hours=24)


def _datetime(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.utcoffset() is None:
        raise ValueError("timezone_required")
    return parsed


def _label(value: Any, limit: int = 200) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("invalid_label")
    return value


class LiveEvidenceStore:
    """Persist minimal local intent, never raw calendar titles or locations."""

    def __init__(
        self, hass: HomeAssistant, *, scope: str = "", provider: str = ""
    ) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._scope = _hash(scope)
        self._provider = provider
        self._data: dict[str, Any] | None = None

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        self._data = stored if isinstance(stored, dict) else None

    def _matches(self, snapshot: JourneySnapshot) -> bool:
        journey, data = snapshot.next_journey, self._data
        if journey is None or data is None or snapshot.simulation_active:
            return False
        raw_journey = data.get("journey")
        return bool(
            data.get("schema", 1) in (1, SCHEMA_VERSION)
            and (data.get("schema", 1) == 1 or data.get("scope") == self._scope)
            and data.get("departure") == journey.start.isoformat()
            and data.get("journey_hash") == _hash(journey.summary)
            and (
                data.get("schema", 1) == 1
                or (
                    isinstance(raw_journey, dict)
                    and raw_journey.get("end")
                    == (journey.end.isoformat() if journey.end else None)
                )
            )
        )

    async def async_save(self, snapshot: JourneySnapshot) -> None:
        if snapshot.simulation_active or snapshot.error is not None:
            return
        journey, observation = snapshot.next_journey, snapshot.rail_observation
        if journey is None:
            if self._data is not None:
                await self._store.async_save({})
                self._data = None
            return
        if journey.end is None or not (
            timedelta(0) < journey.end - journey.start <= MAX_JOURNEY_DURATION
        ):
            return
        saved_observation = (
            self._data.get("observation") if self._matches(snapshot) else None
        )
        if observation is not None and not observation.retained:
            saved_observation = observation.as_dict()
        data = {
            "schema": SCHEMA_VERSION,
            "scope": self._scope,
            "departure": journey.start.isoformat(),
            "journey_hash": _hash(journey.summary),
            "journey": {
                "end": journey.end.isoformat(),
                "origin_code": journey.origin_code,
                "origin_name": journey.origin_name,
                "destination": journey.destination_confirmation,
            },
            "observation": saved_observation,
        }
        if data != self._data:
            await self._store.async_save(data)
            self._data = data

    def restore_journey(self, snapshot: JourneySnapshot) -> JourneyEvent | None:
        """Recover an underway booking only while its calendar is unavailable."""
        data = self._data
        if (
            snapshot.simulation_active
            or snapshot.error != "calendar_unavailable"
            or data is None
            or data.get("schema") != SCHEMA_VERSION
            or data.get("scope") != self._scope
        ):
            return None
        try:
            raw = data["journey"]
            start, end = _datetime(data["departure"]), _datetime(raw["end"])
            if not (
                start <= snapshot.checked_at < end
                and timedelta(0) < end - start <= MAX_JOURNEY_DURATION
            ):
                return None
            origin = _label(raw["origin_name"])
            destination = _label(raw["destination"])
            if not is_rail_candidate({"summary": f"{origin} to {destination}"}):
                return None
            code = _label(raw["origin_code"], 8)
            if not re.fullmatch(r"[A-Z]{3}|CALENDAR", code):
                return None
            return JourneyEvent(
                start=start,
                end=end,
                summary=f"{origin} to {destination}",
                location="",
                origin_code=code,
                origin_name=origin,
                destination_confirmation=destination,
                decision_path="calendar_recovered",
            )
        except KeyError, TypeError, ValueError:
            return None

    def restore(
        self, snapshot: JourneySnapshot, *, recovered: bool = False
    ) -> RailObservation | None:
        journey, data = snapshot.next_journey, self._data
        if journey is None or data is None or snapshot.simulation_active:
            return None
        if not self._matches(snapshot) and not (
            recovered and journey == self.restore_journey(snapshot)
        ):
            return None
        raw = data.get("observation")
        if not isinstance(raw, dict):
            return None
        try:
            observed = _datetime(raw["observed_at"])
            scheduled = _datetime(raw["scheduled_departure"])
            predicted = (
                _datetime(raw["predicted_departure"])
                if raw.get("predicted_departure")
                else None
            )
            source = raw["source"]
            if (
                source not in {"railinfo", "transportapi"}
                or (self._provider and source != self._provider)
                or not timedelta(0)
                <= snapshot.checked_at - observed
                <= MAX_OBSERVATION_AGE
                or abs(scheduled - journey.start) > timedelta(minutes=5)
                or (
                    predicted is not None
                    and not (scheduled <= predicted <= scheduled + timedelta(hours=6))
                )
            ):
                return None
            for key in ("cancelled", "provider_available"):
                if type(raw[key]) is not bool:
                    return None
            for key, maximum in (("delay_minutes", 360), ("leg_count", 20)):
                if type(raw[key]) is not int or not 0 <= raw[key] <= maximum:
                    return None
            if raw["leg_count"] < 1:
                return None
            for key, limit in (
                ("service_identity", 64), ("platform", 32), ("destination_code", 3)
            ):
                if raw.get(key) is not None:
                    _label(raw[key], limit)
            if type(raw.get("schedule_offset_minutes", 0)) is not int:
                return None
            return RailObservation(
                scenario=_label(raw["scenario"], 64),
                source=source,
                classification=_label(raw["classification"], 64),
                observed_at=observed,
                scheduled_departure=scheduled,
                predicted_departure=predicted,
                delay_minutes=raw["delay_minutes"],
                cancelled=raw["cancelled"],
                leg_count=raw["leg_count"],
                provider_available=raw["provider_available"],
                freshness="historical"
                if journey.start <= snapshot.checked_at
                else "retained",
                retained=True,
                age_seconds=int((snapshot.checked_at - observed).total_seconds()),
                service_identity=raw.get("service_identity"),
                platform=raw.get("platform"),
                match_quality=str(raw.get("match_quality", "not_applicable")),
                schedule_offset_minutes=int(raw.get("schedule_offset_minutes", 0)),
                destination_code=raw.get("destination_code"),
            )
        except KeyError, TypeError, ValueError:
            return None


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:24]
