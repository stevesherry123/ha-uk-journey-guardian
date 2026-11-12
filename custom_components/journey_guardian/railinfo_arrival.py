"""Conservative arrival mapping from observed Railinfo direct-journey fields.

The mapper is not wired into monitoring. Unsupported/ambiguous records return no
live evidence. Field provenance and provider limitations are documented separately.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .connection_evidence import ServiceReference, StationTimeEvidence
from .rail import service_identity


def _clock(value: Any) -> time | None:
    if not isinstance(value, str) or len(value) != 4 or not value.isascii():
        return None
    if not value.isdigit():
        return None
    try:
        return time(int(value[:2]), int(value[2:]))
    except ValueError:
        return None


def _instant(day: date, clock: time, zone) -> datetime | None:
    """Reject repeated/nonexistent local clocks without explicit provider offsets."""
    first = datetime.combine(day, clock, tzinfo=zone)
    second = first.replace(fold=1)
    if first.utcoffset() != second.utcoffset():
        return None
    if first.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != (
        first.replace(tzinfo=None)
    ):
        return None
    return first


def normalize_railinfo_prediction(
    payload: Mapping[str, Any],
    *,
    origin_code: str,
    destination_code: str,
    expected_service: ServiceReference,
    booked_departure: datetime,
    booked_arrival: datetime,
    observed_at: datetime,
    event: str,
) -> StationTimeEvidence | None:
    """Match one direct service and its explicit Darwin expected arrival.

    The original broker observation time must be passed unchanged. Neither
    departure delay nor scheduled arrival is promoted to an arrival prediction.
    """
    if event not in ("arrival", "departure"):
        raise ValueError("invalid_station_event")
    if any(
        value.utcoffset() is None
        for value in (booked_departure, booked_arrival, observed_at)
    ):
        raise ValueError("timezone_required")
    if expected_service.provider != "railinfo":
        return None
    zone = ZoneInfo("Europe/London")
    departure = booked_departure.astimezone(zone)
    arrival = booked_arrival.astimezone(zone)
    service_date = departure.date()
    if (
        payload.get("date") != service_date.isoformat()
        or payload.get("is_today") is not True
        or service_date != observed_at.astimezone(zone).date()
        or booked_arrival.astimezone(UTC) <= booked_departure.astimezone(UTC)
    ):
        return None
    journeys = payload.get("journeys")
    if not isinstance(journeys, list):
        return None
    candidates = []
    matched_records = 0
    for journey in journeys:
        if not isinstance(journey, Mapping) or type(journey.get("changes")) is not int:
            continue
        legs = journey.get("legs")
        if journey["changes"] != 0 or not isinstance(legs, list) or len(legs) != 1:
            continue
        leg = legs[0]
        if not isinstance(leg, Mapping):
            continue
        if (
            leg.get("from_crs") != origin_code
            or leg.get("to_crs") != destination_code
            or leg.get("mode") != "train"
        ):
            continue
        headcode = leg.get("headcode")
        if not isinstance(headcode, str) or not headcode.strip():
            continue
        if service_identity(headcode, service_date) != expected_service.identity:
            continue
        matched_records += 1
        if (
            "cancel" in str(journey.get("status", "")).casefold()
            or leg.get("status_source") != "darwin"
            or leg.get("status") not in ("on_time", "late")
            or (leg.get("cancelled") is not None and leg.get("cancelled") is not False)
        ):
            continue
        departure_clock = _clock(leg.get("dep"))
        arrival_clock = _clock(leg.get("arr"))
        expected_clock = _clock(
            leg.get("expected_arr" if event == "arrival" else "expected_dep")
        )
        if None in (departure_clock, arrival_clock, expected_clock):
            continue
        scheduled_departure = _instant(service_date, departure_clock, zone)
        scheduled_arrival = _instant(arrival.date(), arrival_clock, zone)
        if (
            scheduled_departure is None
            or scheduled_arrival is None
            or scheduled_departure.astimezone(UTC) != booked_departure.astimezone(UTC)
            or scheduled_arrival.astimezone(UTC) != booked_arrival.astimezone(UTC)
        ):
            continue
        anchor = scheduled_arrival if event == "arrival" else scheduled_departure
        possible = []
        for offset in (-1, 0, 1):
            expected = _instant(
                anchor.date() + timedelta(days=offset), expected_clock, zone
            )
            if expected is None:
                continue
            delta = expected.astimezone(UTC) - anchor.astimezone(UTC)
            if abs(delta) < timedelta(hours=12) and expected.astimezone(
                UTC
            ) >= booked_departure.astimezone(UTC):
                possible.append(expected)
        if len(possible) != 1:
            continue
        candidates.append(
            StationTimeEvidence(
                expected_service,
                destination_code if event == "arrival" else origin_code,
                event,
                "predicted",
                possible[0],
                observed_at,
            )
        )
    # Duplicate matching records are ambiguous even if their clock values agree.
    return candidates[0] if matched_records == 1 and len(candidates) == 1 else None


def normalize_railinfo_arrival(
    payload: Mapping[str, Any], **kwargs
) -> StationTimeEvidence | None:
    """Preserve the arrival-specific adapter entry point."""
    return normalize_railinfo_prediction(payload, event="arrival", **kwargs)
