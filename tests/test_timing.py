"""Tests for privacy-safe journey timing calculations."""

from datetime import UTC, datetime

from custom_components.journey_guardian.models import JourneyEvent
from custom_components.journey_guardian.timing import calculate_fallback_timing


def test_conservative_fallback_timing_matches_decision_formula() -> None:
    """Preparation, leave, and station arrival retain their exact boundaries."""
    journey = JourneyEvent(
        start=datetime(2026, 8, 29, 16, 30, tzinfo=UTC),
        end=datetime(2026, 8, 29, 18, 30, tzinfo=UTC),
        summary="Rail - Example Central to Example Junction",
        location="Example Central",
        origin_code="CALENDAR",
        origin_name="Example Central",
        destination_confirmation="Example Junction",
        decision_path="calendar_route",
    )

    timing = calculate_fallback_timing(
        journey,
        preparation_minutes=30,
        early_warning_minutes=10,
        station_buffer_minutes=15,
        station_access_minutes=60,
    )

    assert timing.station_arrival_at == datetime(
        2026, 8, 29, 16, 15, tzinfo=UTC
    )
    assert timing.leave_home_at == datetime(2026, 8, 29, 15, 15, tzinfo=UTC)
    assert timing.prepare_at == datetime(2026, 8, 29, 14, 35, tzinfo=UTC)
    assert timing.source == "configured_fallback"
    assert timing.classification == "inferred"
    assert timing.as_dict()["leave_home_at"] == "2026-08-29T15:15:00+00:00"
