"""Tests for deterministic station identity resolution."""

import pytest

from custom_components.journey_guardian.station import (
    StationResolutionError,
    resolve_station,
)


def test_explicit_calendar_crs_is_preferred() -> None:
    """An explicit calendar code needs no provider lookup."""
    result = resolve_station(
        origin_name="Example Central [EXC]",
        location="Example Central",
    )

    assert result.code == "EXC"
    assert result.name == "Example Central"
    assert result.source == "calendar"
    assert result.confidence == "explicit"


def test_explicit_calendar_crs_is_case_insensitive() -> None:
    """Human-entered lowercase codes normalize to canonical CRS form."""
    result = resolve_station(origin_name="Example Central [exc]")

    assert result.code == "EXC"


def test_configured_crs_is_accepted() -> None:
    """A validated configured code remains deterministic."""
    result = resolve_station(origin_name="Example Central", origin_code="EXC")

    assert result.code == "EXC"
    assert result.source == "configured"


def test_saved_places_fixture_resolves_one_exact_station() -> None:
    """An exact normalized station name can resolve from saved data."""
    result = resolve_station(
        origin_name="Example Central",
        places_payload={
            "member": [
                {
                    "type": "train_station",
                    "name": "Example Central Station",
                    "station_code": "EXC",
                },
                {"type": "bus_stop", "name": "Example Central", "code": "BUS"},
            ]
        },
    )

    assert result.code == "EXC"


def test_provider_rail_station_suffix_matches_calendar_name() -> None:
    """Common provider suffixes do not prevent an exact station match."""
    result = resolve_station(
        origin_name="Example Central",
        places_payload={
            "member": [
                {
                    "type": "train_station",
                    "name": "Example Central Rail Station",
                    "station_code": "EXC",
                }
            ]
        },
    )

    assert result.code == "EXC"
    assert result.source == "provider_places"
    assert result.confidence == "exact_name"


def test_supported_station_resolves_without_provider_payload() -> None:
    """Supported routes use deterministic CRS identities without API quota."""
    result = resolve_station(origin_name="London Euston")

    assert result.code == "EUS"
    assert result.source == "known_station"
    assert result.confidence == "deterministic"


def test_places_fixture_rejects_ambiguous_exact_matches() -> None:
    """Two station codes with the same name cannot be guessed between."""
    with pytest.raises(StationResolutionError, match="station_match_ambiguous"):
        resolve_station(
            origin_name="Example",
            places_payload={
                "places": [
                    {"type": "station", "name": "Example", "code": "EXA"},
                    {"type": "station", "name": "Example", "code": "EXB"},
                ]
            },
        )


def test_conflicting_explicit_codes_are_rejected() -> None:
    """Contradictory calendar evidence cannot silently pick a station."""
    with pytest.raises(StationResolutionError, match="station_code_conflict"):
        resolve_station(
            origin_name="Example [EXA]",
            location="Example (EXB)",
        )


def test_malformed_places_fixture_has_stable_error() -> None:
    """Malformed provider data exposes no raw payload details."""
    with pytest.raises(StationResolutionError, match="places_response_malformed"):
        resolve_station(
            origin_name="Example",
            places_payload={"member": "not-a-list"},
        )


def test_empty_origin_cannot_match_empty_provider_name() -> None:
    """Missing calendar identity cannot become a false exact match."""
    with pytest.raises(StationResolutionError, match="station_not_found"):
        resolve_station(
            origin_name="",
            places_payload={
                "member": [{"name": "", "station_code": "EXC"}]
            },
        )
