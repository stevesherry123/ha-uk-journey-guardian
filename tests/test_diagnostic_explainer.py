"""Tests for privacy-safe diagnostic explanations."""

from custom_components.journey_guardian.diagnostic_explainer import (
    explain_live_checks,
)


def test_explainer_describes_signed_timetable_offset() -> None:
    notes = explain_live_checks(
        [{"error_category": "rail_schedule_mismatch", "schedule_offset_minutes": 14}]
    )

    assert notes == [
        "Provider candidate was 14 minutes later than the calendar departure."
    ]


def test_explainer_ignores_unrelated_live_checks() -> None:
    assert explain_live_checks([{"error_category": "station_not_found"}]) == []
