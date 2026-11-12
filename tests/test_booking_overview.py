"""Calendar continuity hints are read-only, not ticket or live-train evidence."""

from datetime import UTC, datetime, timedelta

from custom_components.journey_guardian.booking_overview import (
    render_bookings,
    upcoming_bookings,
)
from custom_components.journey_guardian.journey import select_next_journey

NOW = datetime(2026, 10, 22, 7, 0, tzinfo=UTC)


def event(hour, origin, destination, *, minutes=40):
    start = NOW.replace(hour=hour)
    return {
        "start": start.isoformat(),
        "end": (start + timedelta(minutes=minutes)).isoformat(),
        "summary": f"Example Rail - {origin} to {destination}",
        "location": origin,
    }


def test_four_booking_commute_has_two_possible_connections_not_one_ticket():
    events = [
        event(8, "Example Central", "Example Junction"),
        event(9, "Example Junction", "Sample Harbour"),
        event(17, "Sample Harbour", "Example Junction"),
        event(18, "Example Junction", "Example Central"),
    ]
    legs, count = upcoming_bookings(reversed(events), NOW)
    assert count == 4
    assert legs[0] == select_next_journey(events, NOW)
    rendered = render_bookings(legs, NOW)
    assert [leg["relationship_to_previous"] for leg in rendered] == [
        "first_booking",
        "possible_connection",
        "separate_booking",
        "possible_connection",
    ]
    assert [leg["scheduled_gap_minutes"] for leg in rendered] == [None, 20, 440, 20]
    assert all(leg["evidence"] == "calendar_only" for leg in rendered)
    assert "ticket" not in str(rendered)


def test_overlap_and_different_station_are_not_connections():
    events = [
        event(8, "Example Central", "Example Junction", minutes=90),
        event(9, "Example Junction", "Sample Harbour"),
        event(10, "Different Station", "Example Central"),
    ]
    legs, _count = upcoming_bookings(events, NOW)
    assert [leg["relationship_to_previous"] for leg in render_bookings(legs, NOW)] == [
        "first_booking",
        "overlapping_bookings",
        "different_station",
    ]


def test_missing_arrival_does_not_create_connection_evidence():
    first = event(8, "Example Central", "Example Junction")
    first.pop("end")
    second = event(9, "Example Junction", "Sample Harbour")
    legs, _count = upcoming_bookings([first, second], NOW)
    rendered = render_bookings(legs, NOW)
    assert rendered[1]["relationship_to_previous"] == "arrival_unknown"
    assert rendered[1]["scheduled_gap_minutes"] is None


def test_only_exact_duplicates_collapse_and_changed_bookings_remain_visible():
    first = event(8, "Example Central", "Example Junction")
    other = {**first, "summary": "Another Rail - Example Central to Example Junction"}
    legs, count = upcoming_bookings([first, first.copy(), other], NOW)
    assert len(legs) == count == 2
    assert render_bookings(legs, NOW)[1]["relationship_to_previous"] == (
        "overlapping_bookings"
    )


def test_bounded_overview_reports_total_and_ignores_finished_or_invalid_events():
    events = [event(hour, "Example Central", "Sample Harbour") for hour in range(8, 24)]
    events += [event(6, "Example Central", "Sample Harbour"), {}, None]
    events += [event(8, "Example Central", "Sample Harbour", minutes=-1)]
    next_day = event(8, "Sample Harbour", "Example Central")
    next_day["start"] = (NOW + timedelta(days=1, hours=1)).isoformat()
    next_day["end"] = (NOW + timedelta(days=1, hours=2)).isoformat()
    events.append(next_day)
    legs, count = upcoming_bookings(events, NOW)
    assert len(legs) == 16
    assert count == 17


def test_station_normalization_does_not_fuzzy_match_different_station_names():
    events = [
        event(8, "Example Central", "zzz EXAMPLE   JUNCTION"),
        event(9, "Example Junction", "Sample Harbour"),
        event(10, "Sample Harbour East", "Example Central"),
    ]
    legs, _ = upcoming_bookings(events, NOW)
    rendered = render_bookings(legs, NOW)
    assert rendered[1]["relationship_to_previous"] == "possible_connection"
    assert rendered[2]["relationship_to_previous"] == "different_station"


def test_non_rail_events_never_appear_as_other_booked_rail_legs():
    flight = {
        **event(8, "Example Airport", "Other Airport"),
        "description": "[Flight] Example Airport to Other Airport",
    }
    rail = event(9, "Example Central", "Sample Harbour")
    legs, count = upcoming_bookings([flight, rail], NOW)
    assert count == 1
    assert legs[0].summary == rail["summary"]
