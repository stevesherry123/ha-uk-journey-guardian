"""Tests for calendar normalization and decision selection."""

from datetime import UTC, datetime

from custom_components.journey_guardian.journey import select_next_journey

NOW = datetime(2026, 1, 15, 8, 0, tzinfo=UTC)


def test_generic_route_uses_calendar_origin_and_time() -> None:
    event = {
        "start": "2026-01-15T09:12:00+00:00",
        "summary": "Rail operator - Example Central to Example Junction",
        "location": "Example Central",
    }

    result = select_next_journey([event], NOW)

    assert result is not None
    assert result.origin_code == "CALENDAR"
    assert result.origin_name == "Example Central"
    assert result.decision_path == "calendar_route"
    assert result.destination_confirmation == "Example Junction"


def test_multiple_destinations_are_parsed_without_known_station_list() -> None:
    events = [
        {
            "start": "2026-01-15T10:00:00+00:00",
            "summary": "Rail - Example Central to Example North",
            "location": "Example Central",
        },
        {
            "start": "2026-01-15T18:00:00+00:00",
            "summary": "Rail - Example Central to Example South",
            "location": "Example Central",
        },
    ]

    first = select_next_journey(events, NOW)
    second = select_next_journey(events[1:], NOW)

    assert first is not None
    assert first.destination_confirmation == "Example North"
    assert second is not None
    assert second.destination_confirmation == "Example South"


def test_earliest_future_timed_event_wins() -> None:
    events = [
        {
            "start": "2026-01-15T12:00:00+00:00",
            "summary": "Rail - Example West to Example North",
            "location": "Example West",
        },
        {
            "start": "2026-01-15T09:00:00+00:00",
            "summary": "Rail - Example East to Example South",
            "location": "Example East",
        },
    ]

    result = select_next_journey(events, NOW)

    assert result is not None
    assert result.origin_name == "Example East"


def test_all_day_past_and_non_journey_events_are_ignored() -> None:
    events = [
        {"start": "2026-01-15", "summary": "City visit"},
        {
            "start": "2026-01-15T07:00:00+00:00",
            "summary": "Rail - Example West to Example North",
        },
        {
            "start": "2026-01-15T09:00:00+00:00",
            "summary": "Hotel check-in",
        },
    ]

    assert select_next_journey(events, NOW) is None


def test_active_timed_event_is_retained_until_its_end() -> None:
    event = {
        "start": "2026-01-15T07:45:00+00:00",
        "end": "2026-01-15T08:30:00+00:00",
        "summary": "Rail - Example Central to Example Junction",
        "location": "Example Central",
    }

    result = select_next_journey([event], NOW)

    assert result is not None
    assert result.start == datetime(2026, 1, 15, 7, 45, tzinfo=UTC)
    assert result.end == datetime(2026, 1, 15, 8, 30, tzinfo=UTC)
    assert result.as_dict()["end"] == "2026-01-15T08:30:00+00:00"


def test_completed_timed_event_is_ignored() -> None:
    event = {
        "start": "2026-01-15T07:00:00+00:00",
        "end": "2026-01-15T07:45:00+00:00",
        "summary": "Rail - Example Central to Example Junction",
        "location": "Example Central",
    }

    assert select_next_journey([event], NOW) is None


def test_active_event_precedes_a_later_planned_event() -> None:
    events = [
        {
            "start": "2026-01-15T09:00:00+00:00",
            "end": "2026-01-15T10:00:00+00:00",
            "summary": "Rail - Example Junction to Example Terminal",
            "location": "Example Junction",
        },
        {
            "start": "2026-01-15T07:45:00+00:00",
            "end": "2026-01-15T08:30:00+00:00",
            "summary": "Rail - Example Central to Example Junction",
            "location": "Example Central",
        },
    ]

    result = select_next_journey(events, NOW)

    assert result is not None
    assert result.origin_name == "Example Central"


def test_split_legs_remain_independent_calendar_events() -> None:
    events = [
        {
            "start": "2026-01-15T09:00:00+00:00",
            "summary": "Rail - Example Central to Example Junction",
            "location": "Example Central",
        },
        {
            "start": "2026-01-15T09:45:00+00:00",
            "summary": "Rail - Example Junction to Example Terminal",
            "location": "Example Junction",
        },
    ]

    result = select_next_journey(events, NOW)

    assert result is not None
    assert result.origin_name == "Example Central"
    assert result.destination_confirmation == "Example Junction"
