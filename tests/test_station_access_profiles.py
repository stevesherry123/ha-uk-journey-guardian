"""Tests for deterministic station-specific access preferences."""

import pytest

from custom_components.journey_guardian.models import JourneyEvent
from custom_components.journey_guardian.station_access_profiles import (
    StationAccessProfileError,
    mode_for_journey,
    parse_station_access_profiles,
)


def _journey(origin_name: str, *, location: str = "") -> JourneyEvent:
    from datetime import UTC, datetime

    return JourneyEvent(
        start=datetime(2026, 9, 9, 12, 0, tzinfo=UTC),
        end=None,
        summary="Example journey",
        location=location,
        origin_code="CALENDAR",
        origin_name=origin_name,
        destination_confirmation="Example destination",
        decision_path="calendar_route",
    )


def test_profiles_select_a_known_station_by_crs() -> None:
    profiles = parse_station_access_profiles("CTR=driving\nCRE=driving\nEUS=transit")

    assert mode_for_journey(_journey("Crewe"), profiles) == "driving"
    assert mode_for_journey(_journey("Euston Station"), profiles) == "transit"


def test_unknown_station_uses_default_policy() -> None:
    profiles = parse_station_access_profiles("CRE=driving")

    assert mode_for_journey(_journey("Unfamiliar Junction"), profiles) is None


def test_profiles_reject_invalid_or_duplicate_lines() -> None:
    with pytest.raises(StationAccessProfileError):
        parse_station_access_profiles("CRE=horseback")
    with pytest.raises(StationAccessProfileError):
        parse_station_access_profiles("CRE=driving\nCRE=walking")
