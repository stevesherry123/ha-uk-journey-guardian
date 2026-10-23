"""Synthetic international bookings; no personal itineraries or booking URLs."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from custom_components.journey_guardian.flight import (
    airport_timezones,
    flight_projection,
    parse_flights,
    retain_connection_context,
)
from custom_components.journey_guardian.flight_calendar import FlightCalendarPreview


def instant(value):
    return datetime.fromisoformat(value)


NOW = instant("2026-10-24T00:00:00+00:00")


def booking(**changes):
    return {
        "summary": "ZZ1234 AAA to BBB",
        "start": "2026-10-24T08:00:00+01:00",
        "end": "2026-10-24T10:00:00+01:00",
        "description": (
            "[Flight] AAA to BBB\nExample Air 4321, Terminal 2, Gate \n"
            "Arrive Example Airport (BBB)\nTerminal 4S, Gate \n"
            "Booking reference: PRIVATE-TEST-VALUE\nhttps://example.invalid/private"
        ),
        **changes,
    }


def test_projection_uses_instants_not_calendar_wall_clock():
    legs, rejected = parse_flights([booking()], NOW)
    assert rejected == 0
    assert legs[0].departure.isoformat() == "2026-10-24T07:00:00+00:00"
    zones = airport_timezones("AAA=Europe/London\nBBB=Europe/Madrid")
    data = flight_projection(legs, NOW, zones)
    assert data["legs"][0]["duration_minutes"] == 120
    assert data["legs"][0]["operating_service"] == "Example Air 4321"
    assert data["legs"][0]["arrival_terminal"] == "4S"
    assert data["local_timezones_complete"]
    assert data["source"] == "calendar_only"
    assert not data["live_tracking"] and not data["alerts_enabled"]
    assert "PRIVATE-TEST-VALUE" not in str(data)
    assert "example.invalid" not in str(data)


@pytest.mark.parametrize(
    "changes",
    [
        {"start": "2026-10-24"},
        {"start": "2026-10-24T08:00:00"},
        {"end": "2026-10-24T10:00:00"},
        {"end": None},
        {"end": "not-a-time"},
        {"end": "2026-10-24T06:00:00+00:00"},
        {"end": "2026-10-26T10:00:00+00:00"},
        {"summary": "AAA to AAA"},
        {"summary": "Flight with no readable route"},
    ],
)
def test_unsafe_records_are_counted_not_guessed(changes):
    legs, rejected = parse_flights([booking(**changes)], NOW)
    assert not legs
    assert rejected == 1


def test_no_rail_or_parking_record_enters_flight_preview():
    legs, rejected = parse_flights(
        [
            booking(
                summary="Example Rail - AAA to BBB", description="[Rail] AAA to BBB"
            ),
            booking(summary="Airport parking", description="[Parking] Airport"),
        ],
        NOW,
    )
    assert not legs and rejected == 0


def test_flight_number_title_supported_without_description():
    legs, rejected = parse_flights([booking(description="")], NOW)
    assert len(legs) == 1 and rejected == 0
    assert legs[0].operating_service is None
    assert legs[0].departure_terminal is None


def test_duplicate_records_and_tagged_route_without_flight_number():
    event = booking(summary="[Flight] AAA to BBB")
    legs, rejected = parse_flights([event, event], NOW)
    assert len(legs) == 1 and rejected == 0
    assert legs[0].service is None


@pytest.mark.parametrize(
    "value",
    [
        "AAA=Invalid/Zone",
        "AAA=Europe/London\nAAA=Europe/Madrid",
        "AA=Europe/London",
        "AAA",
        {},
    ],
)
def test_invalid_timezone_profiles_rejected(value):
    with pytest.raises(ValueError, match="invalid_airport_timezones"):
        airport_timezones(value)


def test_unknown_airport_zone_not_inferred():
    legs, _ = parse_flights([booking()], NOW)
    data = flight_projection(legs, NOW, {})
    assert not data["local_timezones_complete"]
    assert data["legs"][0]["origin_timezone"] is None


def test_overnight_across_different_dst_change_dates():
    legs, _ = parse_flights(
        [
            booking(
                start="2026-10-31T23:00:00-04:00",
                end="2026-11-01T10:00:00+00:00",
            )
        ],
        instant("2026-10-31T00:00:00+00:00"),
    )
    leg = legs[0]
    assert leg.arrival - leg.departure == timedelta(hours=7)
    assert leg.departure.astimezone(ZoneInfo("America/New_York")).hour == 23
    assert leg.arrival.astimezone(ZoneInfo("Europe/London")).hour == 10


def test_connection_context_survives_first_leg_leaving_calendar():
    second = booking(
        summary="ZZ5678 BBB to CCC",
        start="2026-10-24T13:00:00+01:00",
        end="2026-10-24T17:00:00+01:00",
    )
    first_legs, _ = parse_flights([booking(), second], NOW)
    now = instant("2026-10-24T10:00:00+00:00")
    current, _ = parse_flights([second], now)
    retained = retain_connection_context(current, first_legs, now)
    assert len(retained) == 2
    data = flight_projection(retained, now, {})
    assert data["state"] == "connection_window"
    assert data["connections"][0]["gap_minutes"] == 180
    assert data["connections"][0]["viability"] == "not_assessed"
    assert data["connections"][0]["ticket_and_baggage"] == "not_read_from_calendar"
    assert data["legs"][0]["phase"] == "scheduled_time_passed"
    assert not retain_connection_context((), retained, now)


def test_overlap_and_airport_change_not_called_connection():
    legs, _ = parse_flights(
        [
            booking(),
            booking(summary="ZZ5678 BBB to CCC"),
            booking(
                summary="ZZ9999 DDD to EEE",
                start="2026-10-24T14:00:00Z",
                end="2026-10-24T17:00:00Z",
            ),
        ],
        NOW,
    )
    assert not flight_projection(legs, NOW, {})["connections"]


async def test_connection_context_persisted_privately_and_cleared(hass, freezer):
    freezer.move_to(NOW)
    preview = FlightCalendarPreview(hass, "synthetic-entry", {})
    second = booking(
        summary="ZZ5678 BBB to CCC",
        start="2026-10-24T13:00:00Z",
        end="2026-10-24T16:00:00Z",
    )
    await preview.async_review([booking(), second], NOW)
    replacement = FlightCalendarPreview(hass, "synthetic-entry", {})
    await replacement.async_load()
    data = await replacement.async_review([second], instant("2026-10-24T11:00:00Z"))
    assert len(data["legs"]) == 2
    assert data["legs"][0]["operating_service"] == "Example Air 4321"
    assert data["legs"][0]["arrival_terminal"] == "4S"
    assert "PRIVATE-TEST-VALUE" not in str(data)
    data = await replacement.async_review([], instant("2026-10-24T17:00:00Z"))
    assert data["state"] == "no_flights" and not data["legs"]


async def test_storage_failure_is_visible_and_retried_without_affecting_calendar(hass):
    preview = FlightCalendarPreview(hass, "synthetic-entry", {})
    preview._store.async_load = AsyncMock(side_effect=OSError("private error"))
    preview._store.async_save = AsyncMock(side_effect=OSError("private error"))
    await preview.async_load()
    data = await preview.async_review([booking()], NOW)
    assert len(data["legs"]) == 1
    assert data["context_persistence_error"]
    assert "private error" not in str(data)
    preview._store.async_save = AsyncMock()
    data = await preview.async_review([booking()], NOW)
    assert not data["context_persistence_error"]
    preview._store.async_save.assert_awaited_once()
