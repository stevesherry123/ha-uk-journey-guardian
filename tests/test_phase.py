"""Tests for operational journey phases and exact boundaries."""

from datetime import UTC, datetime, timedelta

from custom_components.journey_guardian.models import JourneyTiming
from custom_components.journey_guardian.phase import (
    calculate_operational_phase,
    future_phase_boundaries,
)

DEPARTURE = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
TIMING = JourneyTiming(
    prepare_at=DEPARTURE - timedelta(minutes=115),
    leave_home_at=DEPARTURE - timedelta(minutes=75),
    station_arrival_at=DEPARTURE - timedelta(minutes=15),
    preparation_minutes=30,
    early_warning_minutes=10,
    station_buffer_minutes=15,
    station_access_minutes=60,
    source="simulation",
    classification="simulated_scheduled",
)


def test_operational_phase_changes_at_each_exact_boundary() -> None:
    """Each calculated point produces one unambiguous actionable phase."""
    cases = (
        (TIMING.prepare_at - timedelta(seconds=1), "waiting"),
        (TIMING.prepare_at, "prepare_now"),
        (TIMING.leave_home_at, "leave_now"),
        (TIMING.station_arrival_at, "at_station"),
        (DEPARTURE, "active"),
    )

    for now, expected in cases:
        assert (
            calculate_operational_phase(
                status="planned",
                timing=TIMING,
                departure=DEPARTURE,
                now=now,
            )
            == expected
        )


def test_cancelled_and_provider_outage_override_clock_phase() -> None:
    """Safety conditions take priority over otherwise valid timing."""
    assert (
        calculate_operational_phase(
            status="cancelled",
            timing=None,
            departure=DEPARTURE,
            now=TIMING.prepare_at,
        )
        == "cancelled"
    )
    assert (
        calculate_operational_phase(
            status="error",
            timing=TIMING,
            departure=DEPARTURE,
            now=TIMING.prepare_at,
            error="simulated_provider_unavailable",
        )
        == "provider_unavailable"
    )


def test_only_future_boundaries_are_scheduled() -> None:
    """Restart recovery does not recreate already-passed timers."""
    boundaries = future_phase_boundaries(
        TIMING, DEPARTURE, TIMING.leave_home_at
    )

    assert boundaries == (
        ("at_station", TIMING.station_arrival_at),
        ("active", DEPARTURE),
    )
