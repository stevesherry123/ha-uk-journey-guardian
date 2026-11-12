"""Tests for review-only split-journey connection assessment."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from custom_components.journey_guardian.connection import (
    assess_connection,
    resolve_transfer_allowance,
)

ARRIVAL = datetime(2026, 9, 9, 14, 8, tzinfo=UTC)


def test_connection_is_viable_at_the_required_margin() -> None:
    risk = assess_connection(
        inbound_arrival=ARRIVAL,
        outbound_departure=ARRIVAL + timedelta(minutes=12),
        minimum_minutes=12,
    )

    assert risk.classification == "viable"
    assert risk.minutes_available == 12


def test_connection_is_at_risk_when_delay_erodes_margin() -> None:
    risk = assess_connection(
        inbound_arrival=ARRIVAL + timedelta(minutes=8),
        outbound_departure=ARRIVAL + timedelta(minutes=12),
        minimum_minutes=12,
    )

    assert risk.classification == "at_risk"
    assert risk.minutes_available == 4


def test_predicted_arrival_after_departure_is_at_risk_not_confirmed_missed() -> None:
    risk = assess_connection(
        inbound_arrival=ARRIVAL + timedelta(minutes=13),
        outbound_departure=ARRIVAL + timedelta(minutes=12),
        minimum_minutes=12,
    )

    assert risk.classification == "at_risk"
    assert risk.minutes_available == -1


def test_allowance_precedence_and_visible_fallback() -> None:
    override = resolve_transfer_allowance(connection_minutes=0, station_minutes=15)
    assert (override.minutes, override.source) == (0, "connection_override")
    station = resolve_transfer_allowance(station_minutes=15, global_minutes=20)
    assert (station.minutes, station.source) == (15, "station_default")
    fallback = resolve_transfer_allowance()
    assert (fallback.minutes, fallback.source) == (10, "global_fallback")


def test_invalid_allowances_are_rejected() -> None:
    for value in (-1, True, 1.5, "10"):
        try:
            resolve_transfer_allowance(station_minutes=value)
        except ValueError:
            continue
        raise AssertionError(f"Accepted invalid allowance: {value!r}")


def test_connection_uses_elapsed_time_across_autumn_clock_change() -> None:
    london = ZoneInfo("Europe/London")
    risk = assess_connection(
        inbound_arrival=datetime(2026, 10, 25, 1, 50, tzinfo=london, fold=0),
        outbound_departure=datetime(2026, 10, 25, 1, 10, tzinfo=london, fold=1),
        minimum_minutes=10,
    )
    assert risk.minutes_available == 20
    assert risk.classification == "viable"


def test_naive_connection_times_are_rejected() -> None:
    try:
        assess_connection(
            inbound_arrival=ARRIVAL.replace(tzinfo=None),
            outbound_departure=ARRIVAL,
            minimum_minutes=10,
        )
    except ValueError as error:
        assert str(error) == "timezone_required"
    else:
        raise AssertionError("Accepted timezone-free arrival")
