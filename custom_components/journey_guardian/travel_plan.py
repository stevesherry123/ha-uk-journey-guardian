"""Bounded, read-only retention of independently booked calendar legs."""

from __future__ import annotations

import hashlib
import json
import logging
from asyncio import Lock
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store

from .journey import is_rail_candidate
from .models import JourneyEvent, JourneySnapshot

_LOGGER = logging.getLogger(__name__)
MAX_RECORDS = 64
RETENTION = timedelta(hours=48)
LOOKAHEAD = timedelta(hours=30)
CHECKPOINT_INTERVAL = timedelta(minutes=30)


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("timezone_required")
    return parsed.astimezone(UTC)


def _label(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError("invalid_station")
    return value


@dataclass(frozen=True, slots=True)
class RetainedLeg:
    """Calendar intent only: elapsed booking time is not arrival evidence."""

    booking_id: str
    departure: str
    arrival: str | None
    origin: str
    destination: str
    first_seen_at: str
    last_seen_at: str
    in_latest_response: bool = True

    @property
    def expiry(self) -> datetime:
        return _instant(self.arrival or self.departure) + RETENTION


class TravelPlanStore:
    """Retain local intent without replacing the operational next-journey path."""

    def __init__(self, hass: HomeAssistant, *, scope: str) -> None:
        self._scope = hashlib.sha256(scope.encode()).hexdigest()
        self._store: Store[dict[str, Any]] = Store(
            hass, 1, f"journey_guardian.travel_plan.{self._scope[:24]}"
        )
        self._legs: dict[str, RetainedLeg] = {}
        self._last_review: datetime | None = None
        self._last_saved_at: datetime | None = None
        self._saved_records: list[dict] = []
        self._saved_truncated = False
        self._source = "not_reviewed"
        self._truncated = False
        self.persistence_error = False
        self._load_failed = False
        self._lock = Lock()

    async def async_load(self, now: datetime) -> None:
        """Restore only this calendar's well-formed and unexpired records."""
        try:
            loaded = await self._store.async_load()
        except (HomeAssistantError, OSError) as err:
            self.persistence_error = True
            self._load_failed = True
            _LOGGER.warning(
                "Unable to load retained travel plan (%s)", type(err).__name__
            )
            return
        self._load_failed = False
        if not isinstance(loaded, dict) or (
            type(loaded.get("schema")) is not int
            or loaded.get("schema") != 1
            or loaded.get("scope") != self._scope
        ):
            return
        records = loaded.get("records")
        if not isinstance(records, list):
            return
        self._truncated = loaded.get("truncated") is True
        for raw in records[:MAX_RECORDS]:
            try:
                if not isinstance(raw, dict):
                    continue
                leg = RetainedLeg(**raw)
                if (
                    not isinstance(leg.booking_id, str)
                    or len(leg.booking_id) != 64
                    or any(c not in "0123456789abcdef" for c in leg.booking_id)
                    or type(leg.in_latest_response) is not bool
                ):
                    continue
                _label(leg.origin)
                _label(leg.destination)
                if not is_rail_candidate(
                    {"summary": f"{leg.origin} to {leg.destination}"}
                ):
                    continue
                start = _instant(leg.departure)
                end = _instant(leg.arrival) if leg.arrival is not None else None
                first, last = _instant(leg.first_seen_at), _instant(leg.last_seen_at)
                if (
                    not first <= last <= now
                    or start > now + LOOKAHEAD
                    or (
                        end is not None
                        and not timedelta(0) < end - start <= timedelta(hours=24)
                    )
                    or now >= leg.expiry
                ):
                    continue
                self._legs[leg.booking_id] = leg
            except TypeError, ValueError, OverflowError:
                continue
        self._saved_records = self._records()
        self._saved_truncated = self._truncated
        self._last_saved_at = now
        if self._saved_records != records:
            await self._async_persist(self._saved_records, now)
        if self._legs:
            self._source = "retained_after_restart"

    def _booking(self, leg: JourneyEvent, now: datetime) -> RetainedLeg:
        start = leg.start.astimezone(UTC).isoformat()
        end = leg.end.astimezone(UTC).isoformat() if leg.end else None
        # No reliable calendar UID is exposed by all sources. Exact identity
        # avoids silently merging edited or competing bookings into one train.
        identity = json.dumps(
            [self._scope, start, end, leg.summary, leg.location],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return RetainedLeg(
            hashlib.sha256(identity.encode()).hexdigest(),
            start,
            end,
            _label(leg.origin_name),
            _label(leg.destination_confirmation),
            now.isoformat(),
            now.isoformat(),
        )

    async def async_update(self, snapshot: JourneySnapshot) -> None:
        """Record calendar reviews only; never generate an operational snapshot."""
        async with self._lock:
            await self._async_update(snapshot)

    async def _async_update(self, snapshot: JourneySnapshot) -> None:
        if snapshot.simulation_active:
            return
        now = snapshot.checked_at.astimezone(UTC)
        previous = self._legs
        self._legs = {key: leg for key, leg in previous.items() if now < leg.expiry}
        if snapshot.error is None:
            seen: dict[str, RetainedLeg] = {}
            for leg in snapshot.booked_legs:
                if (
                    leg.start.utcoffset() is None
                    or leg.start > now + LOOKAHEAD
                    or (
                        leg.end is not None
                        and (
                            leg.end.utcoffset() is None
                            or not timedelta(0)
                            < leg.end - leg.start
                            <= timedelta(hours=24)
                        )
                    )
                ):
                    continue
                try:
                    record = self._booking(leg, now)
                except ValueError:
                    continue
                if now >= record.expiry:
                    continue
                old = self._legs.get(record.booking_id)
                seen[record.booking_id] = replace(
                    record,
                    first_seen_at=old.first_seen_at if old else record.first_seen_at,
                )
            for key, leg in self._legs.items():
                if key not in seen:
                    seen[key] = replace(leg, in_latest_response=False)
            self._truncated = bool(self._legs) and self._truncated
            self._truncated |= snapshot.booked_leg_count > len(snapshot.booked_legs)
            self._truncated |= len(seen) > MAX_RECORDS
            # Prioritize currently returned legs, then the most recent history.
            retained = sorted(
                seen.values(),
                key=lambda leg: (
                    leg.in_latest_response,
                    _instant(leg.departure),
                    leg.booking_id,
                ),
                reverse=True,
            )[:MAX_RECORDS]
            self._legs = {leg.booking_id: leg for leg in retained}
            self._last_review = now
            self._source = "calendar"
        else:
            self._source = "calendar_unavailable"
        records = self._records()
        if (
            records == self._saved_records
            and self._truncated == self._saved_truncated
            and not self.persistence_error
        ):
            return
        structural_change = [
            {k: v for k, v in record.items() if k != "last_seen_at"}
            for record in records
        ] != [
            {k: v for k, v in record.items() if k != "last_seen_at"}
            for record in self._saved_records
        ]
        if (
            not structural_change
            and self._truncated == self._saved_truncated
            and (
                not records
                or (
                    self._last_saved_at is not None
                    and now - self._last_saved_at < CHECKPOINT_INTERVAL
                )
            )
            and not self.persistence_error
        ):
            return
        await self._async_persist(records, now)

    async def _async_persist(self, records: list[dict], now: datetime) -> None:
        # An unreadable store may still contain valuable original intent.
        # Keep live reviews useful, but require a successful reload before writes.
        if self._load_failed:
            return
        try:
            await self._store.async_save(
                {
                    "schema": 1,
                    "scope": self._scope,
                    "records": records,
                    "truncated": self._truncated,
                }
            )
        except (HomeAssistantError, OSError) as err:
            self.persistence_error = True
            _LOGGER.warning(
                "Unable to save retained travel plan (%s)", type(err).__name__
            )
            return
        self.persistence_error = False
        self._last_saved_at = now
        self._saved_records = records
        self._saved_truncated = self._truncated

    def _records(self) -> list[dict]:
        return [
            asdict(leg)
            for leg in sorted(
                self._legs.values(),
                key=lambda leg: (_instant(leg.departure), leg.booking_id),
            )
        ]

    def attributes(self, now: datetime, *, simulation: bool = False) -> dict:
        """Expose private local intent, explicitly separate from arrival evidence."""
        rendered = []
        if not simulation:
            for record in self._records():
                leg = RetainedLeg(**record)
                if now >= leg.expiry:
                    continue
                end = _instant(leg.arrival) if leg.arrival else None
                window = (
                    "upcoming"
                    if now < _instant(leg.departure)
                    else "booked_window_elapsed"
                    if end and now >= end
                    else "booked_underway"
                    if end
                    else "arrival_unknown"
                )
                rendered.append(
                    {
                        **record,
                        "booked_window": window,
                        "evidence": "calendar_only",
                        "outcome": "unconfirmed",
                    }
                )
        return {
            "retained_plan_source": "simulation_excluded"
            if simulation
            else self._source,
            "retained_booked_legs": rendered,
            "retained_booked_leg_count": len(rendered),
            "retained_plan_truncated": self._truncated if not simulation else False,
            "retained_plan_last_calendar_review_at": (
                self._last_review.isoformat()
                if self._last_review and not simulation
                else None
            ),
            "retained_plan_persistence_error": self.persistence_error,
        }
