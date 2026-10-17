"""Evidence-led diversion selection, including missed GPS and return legs."""

from dataclasses import replace
from datetime import timedelta

import pytest
from test_progress import NOW, ZONES, snapshot

from custom_components.journey_guardian.progress import (
    StationProgress,
    StationZone,
    candidate_routes,
    parse_progress_alternatives,
)

EXTRA = StationZone("zone.example_branch", "zzz Branch", 51.03, 0, 250)
BRANCH = (ZONES[0], EXTRA, ZONES[2])


def fix(tracker, zone, *, reverse=False, **overrides):
    args = dict(
        now=NOW,
        latitude=zone.latitude,
        longitude=zone.longitude,
        accuracy=10,
        location_time=NOW,
        alternatives=(BRANCH,),
    )
    args.update(overrides)
    return tracker.update(snapshot(reverse), ZONES, **args)


def test_fork_selection_and_rejoin_preserve_evidence():
    tracker = StationProgress()
    result = fix(tracker, ZONES[0])
    assert result["candidate_route_count"] == 2
    assert result["next_waypoint"] is None
    assert result["next_waypoints"] == ["Example 1", "Branch"]
    assert result["route_selection"] == "ambiguous"
    result = fix(tracker, EXTRA)
    assert result["candidate_route_count"] == 1
    assert result["route_selection"] == "observed"
    assert result["next_waypoint"] == "Example 2"
    assert fix(tracker, ZONES[1])["status"] == "route_conflict"
    assert fix(tracker, ZONES[0])["status"] == "direction_conflict"
    result = fix(tracker, ZONES[2])
    assert result["candidate_route_count"] == 1
    assert result["rail_arrival_confirmed"] is False


def test_missing_branch_does_not_assume_direct():
    tracker = StationProgress()
    fix(tracker, ZONES[0])
    result = fix(tracker, ZONES[2])
    assert result["candidate_route_count"] == 2
    assert result["route_selection"] == "ambiguous"
    assert result["last_observed_station"] == "Example 2"
    assert result["next_waypoint"] is None


def test_return_and_direct_route_selection():
    tracker = StationProgress()
    assert fix(tracker, ZONES[2], reverse=True)["candidate_route_count"] == 2
    assert fix(tracker, EXTRA, reverse=True)["next_waypoint"] == "Example 0"
    assert fix(tracker, ZONES[0], reverse=True)["candidate_route_count"] == 1
    assert fix(tracker, ZONES[1])["route_selection"] == "observed"


@pytest.mark.parametrize(
    "overrides,status",
    [
        ({"location_time": NOW - timedelta(minutes=6)}, "location_stale"),
        ({"accuracy": 101}, "location_inaccurate"),
        ({"location_time": NOW - timedelta(seconds=1)}, "location_out_of_order"),
        ({"location_time": NOW + timedelta(minutes=1)}, "location_unavailable"),
    ],
)
def test_unreliable_fix_cannot_choose_branch(overrides, status):
    tracker = StationProgress()
    fix(tracker, ZONES[0])
    result = fix(tracker, EXTRA, **overrides)
    assert result["status"] == status
    assert result["candidate_route_count"] == 2
    assert result["last_observed_station"] == "Example 0"


def test_restored_choice_and_changed_geometry():
    original = StationProgress()
    fix(original, EXTRA)
    restored = StationProgress()
    restored.key = original.key
    restored.last_index = original.last_index
    restored.observed_at = original.observed_at
    restored.candidate_positions = dict(original.candidate_positions)
    assert fix(restored, ZONES[2])["candidate_route_count"] == 1
    changed = (ZONES[0], replace(EXTRA, radius=251), ZONES[2])
    assert (
        fix(restored, ZONES[2], alternatives=(changed,))["candidate_route_count"] == 2
    )
    restored.candidate_positions = {"invalid": 900}
    assert (
        fix(restored, ZONES[2], alternatives=(changed,))["candidate_route_count"] == 2
    )


def test_calendar_endpoint_on_branch_and_overlap():
    tracker = StationProgress()
    data = snapshot()
    data = replace(data, next_journey=replace(data.next_journey, origin_name="Branch"))
    result = tracker.update(data, ZONES, now=NOW, alternatives=(BRANCH,))
    assert result["next_waypoint"] == "Branch"
    overlapping = (ZONES[0], replace(EXTRA, latitude=ZONES[1].latitude), ZONES[2])
    assert (
        fix(tracker, ZONES[1], alternatives=(overlapping,))["status"]
        == "location_ambiguous"
    )


@pytest.mark.parametrize(
    "value",
    [
        "zone.example_0 > zone.extra > zone.example_0",
        "zone.example_2 > zone.extra > zone.example_0",
        "zone.unknown > zone.extra > zone.example_2",
        "zone.example_0 > zone.example_1 > zone.example_2",
        "zone.example_0 > sensor.extra > zone.example_2",
        "zone.example_0 > zone.example_2",
        "zone.example_0 > zone.extra > zone.example_2\n"
        "zone.example_0 > zone.extra > zone.example_2",
        "\n".join(
            f"zone.example_0 > zone.extra_{i} > zone.example_2" for i in range(5)
        ),
    ],
)
def test_invalid_alternative_configuration(value):
    with pytest.raises(ValueError, match="invalid_progress_alternatives"):
        parse_progress_alternatives(value, tuple(zone.entity_id for zone in ZONES))


def test_valid_configuration_and_no_base_guard():
    value = "zone.example_0 > zone.extra > zone.example_2"
    assert parse_progress_alternatives("", ()) == ()
    assert parse_progress_alternatives(
        value, tuple(zone.entity_id for zone in ZONES)
    ) == (("zone.example_0", "zone.extra", "zone.example_2"),)
    with pytest.raises(ValueError):
        parse_progress_alternatives(value, ())


def test_sequential_branches_and_common_next_waypoint():
    last = StationZone("zone.example_last", "zzz Last", 51.05, 0, 250)
    extra2 = StationZone("zone.example_branch_two", "zzz Branch Two", 51.06, 0, 250)
    base = (*ZONES, last)
    data = snapshot()
    data = replace(
        data, next_journey=replace(data.next_journey, destination_confirmation="Last")
    )
    tracker = StationProgress()
    result = tracker.update(
        data,
        base,
        now=NOW,
        alternatives=(BRANCH,),
        latitude=ZONES[2].latitude,
        longitude=0,
        accuracy=10,
        location_time=NOW,
    )
    assert result["candidate_route_count"] == 2
    assert result["next_waypoint"] == "Last"
    result = tracker.update(
        data, base, now=NOW, alternatives=(BRANCH, (ZONES[2], extra2, last))
    )
    assert result["candidate_route_count"] == 4


def test_maximum_network_is_bounded_and_station_limit_is_enforced():
    base = tuple(
        StationZone(f"zone.example_base_{i}", f"Base {i}", 51 + i * 0.01, 0, 250)
        for i in range(5)
    )
    branches = tuple(
        (
            base[i],
            StationZone(f"zone.example_alt_{i}", f"Alt {i}", 52 + i * 0.01, 0, 250),
            base[i + 1],
        )
        for i in range(4)
    )
    assert len(candidate_routes(base, branches, "Base 0", "Base 4")) == 16
    assert len(candidate_routes(base, branches, "Base 4", "Base 0")) == 16
    ids = tuple(f"zone.example_station_{i}" for i in range(100))
    with pytest.raises(ValueError):
        parse_progress_alternatives(f"{ids[0]} > zone.example_extra > {ids[-1]}", ids)
