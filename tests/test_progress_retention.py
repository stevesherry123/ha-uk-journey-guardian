"""GPS monitoring extension never changes next-train calendar decisions."""

import json
from dataclasses import replace
from datetime import timedelta

import pytest
from test_progress import NOW, ZONES, snapshot

from custom_components.journey_guardian.progress import StationProgress
from custom_components.journey_guardian.progress_retention import (
    EXTENSION,
    ProgressRetention,
)


def update(retention, progress, data, index, now=NOW, **fix):
    effective, extended = retention.select(data, now)
    args = dict(
        latitude=ZONES[index].latitude, longitude=0, accuracy=10, location_time=now
    )
    args.update(fix)
    result = progress.update(effective, ZONES, now=now, **args)
    retention.observe(result)
    return result, extended


def observed():
    retention, progress = ProgressRetention(), StationProgress()
    update(retention, progress, snapshot(), 1)
    return retention, progress


def test_late_destination_can_be_observed_then_extension_ends():
    retention, progress = observed()
    later = snapshot().next_journey.end + timedelta(minutes=25)
    idle = replace(snapshot(), next_journey=None)
    result, extended = update(retention, progress, idle, 2, later)
    assert extended and result["current_station"] == "Example 2"
    assert result["rail_arrival_confirmed"] is False
    assert retention.dump() is None
    result, extended = update(
        retention, progress, idle, 2, later + timedelta(minutes=1)
    )
    assert not extended and result["status"] == "idle"


def test_next_departure_keeps_priority_without_mutating_snapshot():
    retention, progress = observed()
    old = snapshot().next_journey
    next_leg = replace(
        old,
        start=old.end + timedelta(minutes=30),
        end=old.end + timedelta(hours=2),
        origin_name="Example 2",
        destination_confirmation="Example 0",
    )
    following = replace(snapshot(), next_journey=next_leg)
    result, extended = update(retention, progress, following, 1, old.end)
    assert extended and result["next_waypoint"] == "Example 2"
    assert following.next_journey is next_leg
    result, extended = update(retention, progress, following, 2, next_leg.start)
    assert not extended and result["next_waypoint"] == "Example 1"


def test_extension_has_hard_deadline():
    retention, progress = observed()
    deadline = snapshot().next_journey.end + EXTENSION
    result, extended = update(
        retention, progress, replace(snapshot(), next_journey=None), 1, deadline
    )
    assert not extended and result["status"] == "idle"
    assert retention.dump() is None


def test_known_next_departure_still_ends_extension_during_calendar_outage():
    retention, progress = observed()
    old = snapshot().next_journey
    next_leg = replace(
        old,
        start=old.end + timedelta(minutes=30),
        end=old.end + timedelta(hours=2),
        origin_name="Example 2",
        destination_confirmation="Example 0",
    )
    update(retention, progress, replace(snapshot(), next_journey=next_leg), 1, old.end)
    saved = retention.dump()
    assert saved["next_departure"] == next_leg.start.isoformat()
    assert retention.deadline == next_leg.start
    outage = replace(snapshot(), next_journey=None, error="calendar_unavailable")
    assert update(retention, progress, outage, 1, old.end + timedelta(minutes=1))[1]
    assert not update(retention, progress, outage, 1, next_leg.start)[1]
    retention.restore(saved, [zone.name for zone in ZONES], next_leg.start)
    assert retention.journey is None


def test_destination_seen_before_booked_end_is_not_retained():
    retention, progress = observed()
    update(retention, progress, snapshot(), 2)
    result, extended = update(
        retention,
        progress,
        replace(snapshot(), next_journey=None),
        2,
        snapshot().next_journey.end,
    )
    assert not extended and result["status"] == "idle"


@pytest.mark.parametrize("kind", ["origin", "before_start", "stale", "inaccurate"])
def test_no_extension_without_valid_non_origin_observation(kind):
    retention, progress = ProgressRetention(), StationProgress()
    now = NOW
    index = 0 if kind == "origin" else 1
    options = {}
    if kind == "before_start":
        now = snapshot().next_journey.start - timedelta(minutes=1)
    elif kind == "stale":
        options["location_time"] = now - timedelta(minutes=6)
    elif kind == "inaccurate":
        options["accuracy"] = 150
    update(retention, progress, snapshot(), index, now, **options)
    assert retention.dump() is None
    later = snapshot().next_journey.end + timedelta(minutes=1)
    result, extended = update(
        retention, progress, replace(snapshot(), next_journey=None), 1, later
    )
    assert not extended and result["status"] == "idle"


def test_calendar_outage_preserves_observed_leg_but_removal_does_not():
    retention, progress = observed()
    absent = replace(snapshot(), next_journey=None, error="calendar_unavailable")
    result, extended = update(retention, progress, absent, 1)
    assert extended and result["current_station"] == "Example 1"
    result, extended = update(retention, progress, replace(absent, error=None), 1)
    assert not extended and result["status"] == "idle"


def test_simulation_and_invalid_route_clear_retained_intent():
    retention, progress = observed()
    result, extended = update(
        retention, progress, replace(snapshot(), simulation_active=True), 1
    )
    assert not extended and result["status"] == "idle"
    assert retention.dump() is None
    retention, progress = observed()
    retention.observe({"status": "route_unavailable"})
    assert retention.dump() is None


def test_restart_uses_only_fingerprints_and_times():
    retention, progress = observed()
    saved = json.loads(json.dumps(retention.dump()))
    assert set(saved) == {"start", "end", "origin", "destination"}
    assert "Example" not in str(saved) and "zone." not in str(saved)
    restored = ProgressRetention()
    later = snapshot().next_journey.end + timedelta(minutes=5)
    restored.restore(saved, [zone.name for zone in ZONES], later)
    result, extended = update(
        restored, progress, replace(snapshot(), next_journey=None), 1, later
    )
    assert extended and result["last_observed_station"] == "Example 1"
    restored.restore(saved, [zone.name for zone in ZONES], later + EXTENSION)
    assert restored.journey is None


@pytest.mark.parametrize(
    "change",
    [
        {"start": "bad"},
        {"end": None},
        {"origin": "missing"},
        {"start": "2026-10-15T09:50:00"},
        {"end": "2026-10-15T09:00:00+00:00"},
        {"end": "2026-10-18T09:00:00+00:00"},
    ],
)
def test_corrupt_saved_intent_is_discarded(change):
    retention, _progress = observed()
    saved = {**retention.dump(), **change}
    retention.restore(saved, [zone.name for zone in ZONES], NOW)
    assert retention.journey is None


def test_ambiguous_or_removed_configured_endpoint_is_not_restored():
    retention, _progress = observed()
    saved = retention.dump()
    for names in (
        [zone.name for zone in ZONES[1:]],
        [zone.name for zone in ZONES] + [ZONES[0].name],
    ):
        retention.restore(saved, names, NOW)
        assert retention.journey is None
