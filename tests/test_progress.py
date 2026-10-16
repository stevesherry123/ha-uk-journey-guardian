"""Conservative station proximity, independent of rail evidence."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.journey_guardian.models import (
    BudgetSnapshot,
    JourneyEvent,
    JourneySnapshot,
)
from custom_components.journey_guardian.progress import (
    StationProgress,
    StationZone,
    parse_progress_zones,
    station_label,
)

NOW = datetime(2026, 10, 15, 10, tzinfo=UTC)
ZONES = tuple(
    StationZone(f"zone.example_{i}", f"zzz Example {i}", 51 + i * 0.01, 0, 250)
    for i in range(3)
)


def snapshot(reverse=False):
    return JourneySnapshot(
        status="scheduled",
        checked_at=NOW,
        next_journey=JourneyEvent(
            start=NOW - timedelta(minutes=10),
            end=NOW + timedelta(hours=1),
            summary="Example rail journey",
            location="",
            origin_code="CALENDAR",
            origin_name="Example 2" if reverse else "Example 0",
            destination_confirmation="Example 0" if reverse else "Example 2",
            decision_path="calendar_route",
        ),
        budget=BudgetSnapshot("2026-10-15", 0, 30, 3),
    )


def observe(tracker, index, **overrides):
    args = dict(
        now=NOW,
        latitude=ZONES[index].latitude,
        longitude=0,
        accuracy=10,
        location_time=NOW,
    )
    args.update(overrides)
    return tracker.update(snapshot(), ZONES, **args)


def test_forward_observations_do_not_infer_passage_or_arrival():
    tracker = StationProgress()
    first = observe(tracker, 0)
    assert first["current_station"] == "Example 0"
    assert first["next_waypoint"] == "Example 1"
    between = observe(tracker, 0, latitude=51.005)
    assert between["status"] == "between_observations"
    assert between["last_observed_station"] == "Example 0"
    assert between["current_station"] is None
    end = observe(tracker, 2)
    assert end["last_observed_station"] == "Example 2"
    assert end["next_waypoint"] is None
    assert end["rail_arrival_confirmed"] is False
    assert observe(tracker, 1)["status"] == "direction_conflict"


def test_reverse_and_leg_change_reset():
    tracker = StationProgress()
    observe(tracker, 2)
    result = tracker.update(
        snapshot(True),
        ZONES,
        now=NOW,
        latitude=51.02,
        longitude=0,
        accuracy=10,
        location_time=NOW,
    )
    assert result["current_station"] == "Example 2"
    assert result["next_waypoint"] == "Example 1"
    assert tracker.last_index == 0


@pytest.mark.parametrize(
    ("overrides", "status"),
    [
        ({"location_time": NOW - timedelta(minutes=6)}, "location_stale"),
        ({"location_time": NOW + timedelta(minutes=1)}, "location_unavailable"),
        ({"accuracy": 101}, "location_inaccurate"),
        ({"accuracy": -1}, "location_unavailable"),
        ({"latitude": float("nan")}, "location_unavailable"),
        ({"latitude": True}, "location_unavailable"),
        ({"longitude": 200}, "location_unavailable"),
        ({"location_time": None}, "location_unavailable"),
    ],
)
def test_unreliable_location_cannot_advance(overrides, status):
    tracker = StationProgress()
    observe(tracker, 0)
    result = observe(tracker, 2, **overrides)
    assert result["status"] == status
    assert result["last_observed_station"] == "Example 0"


def test_out_of_order_and_ambiguous_location():
    tracker = StationProgress()
    observe(tracker, 0)
    assert (
        observe(tracker, 1, location_time=NOW - timedelta(seconds=1))["status"]
        == "location_out_of_order"
    )
    overlapping = (ZONES[0], replace(ZONES[1], latitude=51), ZONES[2])
    result = tracker.update(
        snapshot(),
        overlapping,
        now=NOW,
        latitude=51,
        longitude=0,
        accuracy=10,
        location_time=NOW,
    )
    assert result["status"] == "location_ambiguous"
    assert result["last_observed_station"] is None


def test_corrupt_restored_index_and_idle_reset():
    tracker = StationProgress()
    observe(tracker, 0)
    tracker.last_index = 50
    assert observe(tracker, 1)["last_observed_station"] == "Example 1"
    assert (
        tracker.update(replace(snapshot(), next_journey=None), ZONES, now=NOW)["status"]
        == "idle"
    )
    assert tracker.last_index is None
    assert (
        tracker.update(replace(snapshot(), simulation_active=True), ZONES, now=NOW)[
            "status"
        ]
        == "idle"
    )


def test_route_and_time_guards():
    tracker = StationProgress()
    assert tracker.update(snapshot(), (), now=NOW)["status"] == "route_unavailable"
    assert tracker.update(snapshot(), ZONES[:2], now=NOW)["status"] == "route_unmatched"
    assert (
        tracker.update(snapshot(), ZONES, now=NOW - timedelta(hours=3))["status"]
        == "waiting"
    )
    assert (
        tracker.update(snapshot(), ZONES, now=NOW + timedelta(days=1))["status"]
        == "idle"
    )


@pytest.mark.parametrize(
    "value", ["zone.a", "zone.a\nzone.a", "sensor.a\nzone.b", "zone.a\nzone.b bad"]
)
def test_invalid_route_configuration(value):
    with pytest.raises(ValueError):
        parse_progress_zones(value)


def test_route_configuration_and_prefix():
    assert parse_progress_zones(" \n") == ()
    assert parse_progress_zones("zone.example_a\n\n zone.example_b ") == (
        "zone.example_a",
        "zone.example_b",
    )
    assert station_label("zzz Example") == "Example"
    assert station_label("Example zzz") == "Example zzz"
