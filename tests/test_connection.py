"""Tests for review-only split-journey connection assessment."""

from datetime import UTC, datetime, timedelta

from custom_components.journey_guardian.connection import assess_connection

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


def test_connection_is_missed_after_the_next_departure() -> None:
    risk = assess_connection(
        inbound_arrival=ARRIVAL + timedelta(minutes=13),
        outbound_departure=ARRIVAL + timedelta(minutes=12),
        minimum_minutes=12,
    )

    assert risk.classification == "missed"
