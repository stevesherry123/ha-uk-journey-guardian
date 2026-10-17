"""Bounded GPS-only monitoring, separate from next-train scheduling."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timedelta

from .models import JourneyEvent, JourneySnapshot
from .progress import station_label

EXTENSION = timedelta(hours=3)


def _station_key(name: str) -> str:
    return " ".join(station_label(name).casefold().split())


def _fingerprint(name: str) -> str:
    return hashlib.sha256(_station_key(name).encode()).hexdigest()


def _same(left: JourneyEvent | None, right: JourneyEvent | None) -> bool:
    return bool(
        left
        and right
        and left.start == right.start
        and _station_key(left.origin_name) == _station_key(right.origin_name)
        and _station_key(left.destination_confirmation)
        == _station_key(right.destination_confirmation)
    )


class ProgressRetention:
    """Retain observed intent without changing calendar or provider decisions."""

    def __init__(self) -> None:
        self.journey: JourneyEvent | None = None
        self.eligible = False
        self.destination_observed = False
        self.next_departure: datetime | None = None

    def reset(self) -> None:
        self.journey = None
        self.eligible = False
        self.destination_observed = False
        self.next_departure = None

    @property
    def deadline(self) -> datetime | None:
        if not self.journey or not self.journey.end:
            return None
        end = self.journey.end + EXTENSION
        return min(end, self.next_departure) if self.next_departure else end

    def select(
        self, snapshot: JourneySnapshot, now: datetime
    ) -> tuple[JourneySnapshot, bool]:
        """Select only the GPS leg; an already-started next booking takes priority."""
        if snapshot.simulation_active:
            self.reset()
            return snapshot, False
        current = snapshot.next_journey
        if _same(self.journey, current):
            self.journey = current
        old = self.journey
        if old and current and not _same(old, current):
            self.next_departure = current.start
        elif current is None and snapshot.error != "calendar_unavailable":
            self.next_departure = None
        if current and current.end and current.end <= now:
            current = None
        if (
            old
            and old.end
            and self.eligible
            and not self.destination_observed
            and old.start <= now < self.deadline
            and (now >= old.end or snapshot.error == "calendar_unavailable")
            and not (current and current.start <= now and not _same(old, current))
        ):
            return replace(snapshot, next_journey=old), True
        if not _same(old, current):
            self.reset()
        self.journey = current
        return replace(snapshot, next_journey=current), False

    def observe(self, result: dict) -> None:
        """Eligibility requires a positively observed non-origin fix after start."""
        if result["status"] in {"route_unavailable", "route_unmatched"}:
            self.reset()
            return
        journey = self.journey
        if not journey or result["status"] != "near_station":
            return
        observed = datetime.fromisoformat(result["last_observed_at"])
        if observed < journey.start:
            return
        station = _station_key(result["current_station"])
        if station != _station_key(journey.origin_name):
            self.eligible = True
        if station == _station_key(journey.destination_confirmation):
            self.destination_observed = True

    def dump(self) -> dict | None:
        """Store endpoint fingerprints and times, never names or calendar titles."""
        journey = self.journey
        if (
            not journey
            or not journey.end
            or not self.eligible
            or self.destination_observed
        ):
            return None
        saved = {
            "start": journey.start.isoformat(),
            "end": journey.end.isoformat(),
            "origin": _fingerprint(journey.origin_name),
            "destination": _fingerprint(journey.destination_confirmation),
        }
        if self.next_departure:
            saved["next_departure"] = self.next_departure.isoformat()
        return saved

    def restore(self, saved: object, names: list[str], now: datetime) -> None:
        """Resolve stored fingerprints uniquely against current configured zones."""
        self.reset()
        if not isinstance(saved, dict):
            return
        try:
            start = datetime.fromisoformat(saved["start"])
            end = datetime.fromisoformat(saved["end"])
            if (
                start.tzinfo is None
                or end.tzinfo is None
                or not timedelta(0) < end - start <= timedelta(days=1)
                or not start <= now < end + EXTENSION
            ):
                return
            origin = [name for name in names if _fingerprint(name) == saved["origin"]]
            destination = [
                name for name in names if _fingerprint(name) == saved["destination"]
            ]
            if len(origin) != 1 or len(destination) != 1 or origin == destination:
                return
            next_departure = None
            if "next_departure" in saved:
                next_departure = datetime.fromisoformat(saved["next_departure"])
                if next_departure.tzinfo is None or not start <= now < next_departure:
                    return
            self.journey = JourneyEvent(
                start=start,
                end=end,
                summary="Retained GPS monitoring",
                location="",
                origin_code="CALENDAR",
                origin_name=station_label(origin[0]),
                destination_confirmation=station_label(destination[0]),
                decision_path="gps_retained_intent",
            )
            self.eligible = True
            self.next_departure = next_departure
        except KeyError, ValueError, TypeError, OverflowError:
            return
