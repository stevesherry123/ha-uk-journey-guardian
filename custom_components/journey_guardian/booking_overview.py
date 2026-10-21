"""Read-only calendar-leg overview; never changes selection or sends alerts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from .journey import select_next_journey
from .models import JourneyEvent

MAX_LEGS = 16
MAX_POSSIBLE_CONNECTION_MINUTES = 120


def upcoming_bookings(
    events: Iterable[Mapping[str, Any]], now: datetime
) -> tuple[tuple[JourneyEvent, ...], int]:
    """Keep independently booked legs, deduplicating only identical events."""
    unique: dict[tuple, JourneyEvent] = {}
    for raw in events:
        if not isinstance(raw, Mapping):
            continue
        leg = select_next_journey((raw,), now)
        if leg is None or (leg.end is not None and leg.end <= leg.start):
            continue
        unique[(leg.start, leg.end, leg.summary, leg.location)] = leg
    legs = sorted(
        unique.values(), key=lambda leg: (leg.start, leg.end or leg.start, leg.summary)
    )
    return tuple(legs[:MAX_LEGS]), len(legs)


def _station(value: str) -> str:
    return " ".join(value.casefold().split()).removeprefix("zzz ")


def render_bookings(legs: tuple[JourneyEvent, ...], now: datetime) -> list[dict]:
    """Describe schedule continuity without inferring a ticket or viable transfer."""
    result = []
    previous = None
    for leg in legs:
        relationship = "first_booking"
        gap = None
        if previous is not None:
            if previous.end is None:
                relationship = "arrival_unknown"
            else:
                gap = int((leg.start - previous.end).total_seconds() // 60)
                if gap < 0:
                    relationship = "overlapping_bookings"
                elif _station(previous.destination_confirmation) != _station(
                    leg.origin_name
                ):
                    relationship = "different_station"
                elif gap <= MAX_POSSIBLE_CONNECTION_MINUTES:
                    relationship = "possible_connection"
                else:
                    relationship = "separate_booking"
        result.append(
            {
                "booked_departure": leg.start.isoformat(),
                "booked_arrival": leg.end.isoformat() if leg.end else None,
                "origin": leg.origin_name,
                "destination": leg.destination_confirmation,
                "booked_window": "underway" if leg.start <= now else "upcoming",
                "relationship_to_previous": relationship,
                "scheduled_gap_minutes": gap,
                "evidence": "calendar_only",
            }
        )
        previous = leg
    return result
