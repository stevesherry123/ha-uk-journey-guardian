"""Validate private, bounded booked-intent and observation recovery."""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from custom_components.journey_guardian.live_evidence import LiveEvidenceStore
from custom_components.journey_guardian.models import (
    BudgetSnapshot,
    JourneyEvent,
    JourneySnapshot,
    RailObservation,
)

NOW = datetime(2026, 10, 22, 9, 10, tzinfo=UTC)


def snapshot():
    journey = JourneyEvent(
        NOW - timedelta(minutes=10),
        NOW + timedelta(hours=1),
        "Private booking reference - Example Central to Sample Harbour",
        "Private street address",
        "EXC",
        "Example Central",
        "Sample Harbour",
        "railinfo_manual",
    )
    observation = RailObservation(
        "observed",
        "railinfo",
        "provider_normalized",
        NOW - timedelta(minutes=5),
        journey.start,
        journey.start + timedelta(minutes=20),
        20,
        False,
        1,
        True,
        service_identity="example-service",
        destination_code="SMP",
    )
    return JourneySnapshot(
        "delayed",
        NOW,
        journey,
        BudgetSnapshot("2026-10-22", 0, 30, 3),
        rail_observation=observation,
    )


def outage():
    return replace(
        snapshot(),
        status="error",
        next_journey=None,
        rail_observation=None,
        error="calendar_unavailable",
        operational_phase="error",
    )


async def saved_store(hass):
    store = LiveEvidenceStore(hass, scope="example-entry", provider="railinfo")
    store._store.async_save = AsyncMock()
    await store.async_save(snapshot())
    return store


async def test_round_trip_recovery_does_not_store_raw_title_or_address(hass):
    original = await saved_store(hass)
    saved = deepcopy(original._data)
    assert "Private" not in str(saved)
    assert "Example Central" in str(saved)  # Local minimal station labels.
    restored = LiveEvidenceStore(hass, scope="example-entry", provider="railinfo")
    restored._store.async_load = AsyncMock(return_value=saved)
    await restored.async_load()
    journey = restored.restore_journey(outage())
    assert journey is not None
    assert journey.summary == "Example Central to Sample Harbour"
    recovered = replace(outage(), next_journey=journey)
    observation = restored.restore(recovered, recovered=True)
    assert observation is not None
    assert observation.retained
    assert observation.freshness == "historical"
    assert observation.age_seconds == 300


@pytest.mark.parametrize(
    "change",
    [
        {"error": None},
        {"simulation_active": True},
        {"checked_at": NOW + timedelta(hours=2)},
        {"checked_at": NOW - timedelta(hours=1)},
    ],
)
async def test_intent_never_revives_deleted_future_completed_or_simulated_leg(
    hass, change
):
    store = await saved_store(hass)
    assert store.restore_journey(replace(outage(), **change)) is None


async def test_scope_change_and_unknown_schema_fail_closed(hass):
    store = await saved_store(hass)
    store._scope = "different-calendar-entry"
    assert store.restore_journey(outage()) is None
    assert store.restore(snapshot()) is None
    store = await saved_store(hass)
    store._data["schema"] = 999
    assert store.restore_journey(outage()) is None
    assert store.restore(snapshot()) is None


@pytest.mark.parametrize(
    "key,value",
    [
        ("observed_at", (NOW - timedelta(hours=7)).isoformat()),
        ("observed_at", (NOW + timedelta(seconds=1)).isoformat()),
        ("observed_at", "2026-10-22T09:00:00"),
        ("scheduled_departure", "2026-10-22T09:00:00"),
        ("cancelled", "false"),
        ("delay_minutes", True),
        ("source", "simulation"),
        ("predicted_departure", "broken"),
    ],
)
async def test_invalid_or_expired_observations_are_not_restored(hass, key, value):
    store = await saved_store(hass)
    store._data["observation"][key] = value
    assert store.restore(snapshot()) is None


async def test_changed_end_and_provider_do_not_reuse_old_rail_evidence(hass):
    store = await saved_store(hass)
    current = snapshot()
    changed = replace(
        current,
        next_journey=replace(current.next_journey, end=NOW + timedelta(hours=2)),
    )
    assert store.restore(changed) is None
    store._provider = "transportapi"
    assert store.restore(current) is None


async def test_legacy_schema_restores_only_matching_valid_observation(hass):
    store = await saved_store(hass)
    store._data = {
        key: value
        for key, value in store._data.items()
        if key in {"departure", "journey_hash", "observation"}
    }
    assert store.restore(snapshot()) is not None
    assert store.restore_journey(outage()) is None
    await store.async_save(snapshot())
    assert store._data["schema"] == 2


async def test_simulation_and_outage_do_not_overwrite_but_healthy_idle_clears(hass):
    store = await saved_store(hass)
    saved = deepcopy(store._data)
    await store.async_save(replace(snapshot(), simulation_active=True))
    await store.async_save(outage())
    assert store._data == saved
    await store.async_save(replace(outage(), error=None, status="idle"))
    assert store._data is None


@pytest.mark.parametrize("bad", [None, [], "bad", {"end": "bad"}])
async def test_malformed_intent_never_raises(hass, bad):
    store = await saved_store(hass)
    store._data["journey"] = bad
    assert store.restore(snapshot()) is None
    assert store.restore_journey(outage()) is None
