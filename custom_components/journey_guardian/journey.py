"""Pure, provider-neutral journey parsing and decision selection."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from .models import JourneyEvent


def parse_datetime(value: str, reference: datetime) -> datetime | None:
    """Parse a timed calendar value and reject all-day dates."""
    if not value or len(value) == 10:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=reference.tzinfo or UTC)
    return parsed


def _route_parts(summary: str) -> tuple[str, str] | None:
    """Extract generic origin and destination names from a calendar title."""
    route_text = summary.rsplit(" - ", 1)[-1].strip()
    separator = route_text.casefold().find(" to ")
    if separator < 1:
        return None
    origin = route_text[:separator].strip()
    destination = route_text[separator + 4 :].strip()
    if not origin or not destination:
        return None
    return origin, destination


def select_next_journey(
    events: Iterable[Mapping[str, Any]], reference: datetime
) -> JourneyEvent | None:
    """Return the next timed event and its Journey Guardian decision path."""
    candidates: list[JourneyEvent] = []
    for raw_event in events:
        start = parse_datetime(str(raw_event.get("start", "")), reference)
        if start is None or start <= reference:
            continue
        summary = str(raw_event.get("summary", "")).strip()
        location = str(raw_event.get("location", "")).strip()
        route = _route_parts(summary)
        if route is None:
            continue
        origin_name, destination_name = route
        candidates.append(
            JourneyEvent(
                start=start,
                summary=summary,
                location=location,
                origin_code="CALENDAR",
                origin_name=origin_name,
                destination_confirmation=destination_name,
                decision_path="calendar_route",
            )
        )
    return min(candidates, key=lambda event: event.start) if candidates else None
