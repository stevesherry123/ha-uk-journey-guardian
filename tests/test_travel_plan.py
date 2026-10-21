"""Retained multi-leg intent cannot silently become operational rail evidence."""

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.journey_guardian.const import DOMAIN
from custom_components.journey_guardian.coordinator import JourneyGuardianCoordinator
from custom_components.journey_guardian.models import (
    BudgetSnapshot,
    JourneyEvent,
    JourneySnapshot,
)
from custom_components.journey_guardian.sensor import JourneyStatusSensor
from custom_components.journey_guardian.travel_plan import MAX_RECORDS, TravelPlanStore

NOW = datetime(2026, 10, 22, 6, tzinfo=UTC)


def leg(hour, origin="Example Central", destination="Example Junction"):
    start = NOW.replace(hour=hour)
    return JourneyEvent(
        start,
        start + timedelta(minutes=40),
        f"Private booking reference - {origin} to {destination}",
        "Private street address",
        "CALENDAR",
        origin,
        destination,
        "calendar_route",
    )


LEGS = (
    leg(8),
    leg(9, "Example Junction", "Sample Harbour"),
    leg(17, "Sample Harbour", "Example Junction"),
    leg(18, "Example Junction", "Example Central"),
)


def snapshot(legs=LEGS, now=NOW, **changes):
    return JourneySnapshot(
        "planned" if legs else "idle",
        now,
        legs[0] if legs else None,
        BudgetSnapshot("2026-10-22", 0, 30, 3),
        booked_legs=legs,
        booked_leg_count=len(legs),
        **changes,
    )


def store(hass, scope="fictional-entry|example-calendar"):
    result = TravelPlanStore(hass, scope=scope)
    result._store.async_save = AsyncMock()
    return result


async def restart(hass, original, now=NOW):
    restored = store(hass)
    saved = deepcopy(original._store.async_save.call_args.args[0])
    restored._store.async_load = AsyncMock(return_value=saved)
    await restored.async_load(now)
    return restored


async def test_four_bookings_survive_each_refresh_and_fresh_instance(hass):
    plan = store(hass)
    await plan.async_update(snapshot())
    ids = [x["booking_id"] for x in plan.attributes(NOW)["retained_booked_legs"]]
    for index, hour in enumerate((8, 9, 17, 18)):
        now = NOW.replace(hour=hour, minute=50)
        await plan.async_update(snapshot(LEGS[index + 1 :], now))
        plan = await restart(hass, plan, now)
        attrs = plan.attributes(now)
        assert attrs["retained_plan_source"] == "retained_after_restart"
        assert [x["booking_id"] for x in attrs["retained_booked_legs"]] == ids
        assert attrs["retained_booked_leg_count"] == 4
    assert all(
        x["booked_window"] == "booked_window_elapsed"
        and x["outcome"] == "unconfirmed"
        and x["evidence"] == "calendar_only"
        for x in attrs["retained_booked_legs"]
    )


async def test_outage_keeps_future_bookings_but_never_promotes_them_to_alarms(hass):
    engine = Mock(async_review=AsyncMock(return_value=snapshot()))
    entry = MockConfigEntry(domain=DOMAIN)
    coordinator = JourneyGuardianCoordinator(hass, entry, engine)
    coordinator.travel_plan._store.async_save = AsyncMock()
    assert await coordinator._async_review_data() == snapshot()
    outage = replace(
        snapshot(),
        error="calendar_unavailable",
        status="error",
        next_journey=None,
        booked_legs=(),
        booked_leg_count=0,
    )
    engine.async_review.return_value = outage
    result = await coordinator._async_review_data()
    assert result == outage
    assert result.next_journey is None
    attrs = JourneyStatusSensor(coordinator, entry, "status")
    coordinator.async_set_updated_data(result)
    assert attrs.extra_state_attributes["retained_booked_leg_count"] == 4
    assert (
        attrs.extra_state_attributes["retained_plan_source"] == "calendar_unavailable"
    )
    assert attrs.extra_state_attributes["error"] == "calendar_unavailable"
    assert attrs.extra_state_attributes["upcoming_booked_legs"] == []
    assert engine.async_review.await_count == 2


async def test_empty_response_is_not_cancellation_and_new_booking_does_not_erase_old(
    hass,
):
    plan = store(hass)
    await plan.async_update(snapshot())
    await plan.async_update(snapshot((), NOW + timedelta(minutes=1)))
    records = plan.attributes(NOW)["retained_booked_legs"]
    assert all(not x["in_latest_response"] for x in records)
    assert all(x["outcome"] == "unconfirmed" for x in records)
    changed = replace(LEGS[0], end=LEGS[0].end + timedelta(minutes=5))
    await plan.async_update(snapshot((changed,), NOW + timedelta(minutes=2)))
    assert plan.attributes(NOW)["retained_booked_leg_count"] == 5
    assert (
        sum(
            x["in_latest_response"]
            for x in plan.attributes(NOW)["retained_booked_legs"]
        )
        == 1
    )


async def test_duplicates_collapse_but_competing_bookings_do_not(hass):
    plan = store(hass)
    competing = replace(
        LEGS[0], summary="Other Rail - Example Central to Example Junction"
    )
    await plan.async_update(snapshot((LEGS[0], LEGS[0], competing)))
    assert plan.attributes(NOW)["retained_booked_leg_count"] == 2


async def test_identity_is_independent_of_event_order_and_timezone_representation(hass):
    plan = store(hass)
    await plan.async_update(snapshot())
    ids = list(plan._legs)
    london = ZoneInfo("Europe/London")
    changed = tuple(
        replace(x, start=x.start.astimezone(london), end=x.end.astimezone(london))
        for x in reversed(LEGS)
    )
    await plan.async_update(snapshot(changed, NOW + timedelta(minutes=1)))
    assert set(plan._legs) == set(ids)


async def test_simulation_neither_mutates_nor_exposes_real_plan(hass):
    plan = store(hass)
    await plan.async_update(snapshot())
    before = deepcopy(plan._legs)
    calls = plan._store.async_save.await_count
    await plan.async_update(
        snapshot((), NOW + timedelta(days=7), simulation_active=True)
    )
    assert plan._legs == before
    assert plan._store.async_save.await_count == calls
    attrs = plan.attributes(NOW, simulation=True)
    assert attrs["retained_booked_legs"] == []
    assert attrs["retained_plan_source"] == "simulation_excluded"


async def test_local_minimum_data_no_raw_title_address_and_distinct_scope(hass):
    plan = store(hass)
    await plan.async_update(snapshot())
    saved = deepcopy(plan._store.async_save.call_args.args[0])
    assert "Private" not in str(saved)
    assert "Example Central" in str(saved)
    other = store(hass, scope="different-entry|other-calendar")
    assert other._store.key != plan._store.key
    other._store.async_load = AsyncMock(return_value=saved)
    await other.async_load(NOW)
    assert other.attributes(NOW)["retained_booked_legs"] == []


async def test_expiry_purges_local_storage_even_during_calendar_outage(hass):
    plan = store(hass)
    await plan.async_update(snapshot((LEGS[0],)))
    expired = LEGS[0].end + timedelta(hours=48)
    await plan.async_update(snapshot((), expired, error="calendar_unavailable"))
    assert plan.attributes(expired)["retained_booked_legs"] == []
    assert plan._store.async_save.call_args.args[0]["records"] == []


async def test_restart_purges_expired_records_and_does_not_rewrite_valid_data(hass):
    plan = store(hass)
    await plan.async_update(snapshot())
    restored = await restart(hass, plan)
    restored._store.async_save.assert_not_awaited()
    restored = await restart(hass, plan, NOW + timedelta(days=4))
    assert restored.attributes(NOW + timedelta(days=4))["retained_booked_legs"] == []
    assert restored._store.async_save.call_args.args[0]["records"] == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("booking_id", "wrong"),
        ("departure", "2026-10-22T08:00:00"),
        ("arrival", "broken"),
        ("arrival", NOW.isoformat()),
        ("origin", []),
        ("destination", "x" * 201),
        ("first_seen_at", (NOW + timedelta(days=1)).isoformat()),
        ("last_seen_at", None),
        ("in_latest_response", "false"),
    ],
)
async def test_corrupt_persisted_leg_is_rejected_without_losing_valid_peers(
    hass, field, value
):
    plan = store(hass)
    await plan.async_update(snapshot())
    data = deepcopy(plan._store.async_save.call_args.args[0])
    data["records"][0][field] = value
    restored = store(hass)
    restored._store.async_load = AsyncMock(return_value=data)
    await restored.async_load(NOW)
    assert restored.attributes(NOW)["retained_booked_leg_count"] == 3


@pytest.mark.parametrize("bad", [None, [], "bad", {"schema": 99}, {"records": []}])
async def test_unknown_or_malformed_store_fails_closed(hass, bad):
    plan = store(hass)
    plan._store.async_load = AsyncMock(return_value=bad)
    await plan.async_load(NOW)
    assert plan.attributes(NOW)["retained_booked_legs"] == []


async def test_unchanged_reviews_checkpoint_instead_of_writing_each_minute(hass):
    plan = store(hass)
    for minute in range(30):
        await plan.async_update(snapshot(now=NOW + timedelta(minutes=minute)))
    assert plan._store.async_save.await_count == 1
    await plan.async_update(snapshot(now=NOW + timedelta(minutes=30)))
    assert plan._store.async_save.await_count == 2


async def test_storage_failure_is_visible_but_does_not_break_review_and_retries(hass):
    plan = store(hass)
    plan._store.async_save.side_effect = OSError("private path must not be logged")
    await plan.async_update(snapshot())
    assert plan.attributes(NOW)["retained_plan_persistence_error"]
    assert plan.attributes(NOW)["retained_booked_leg_count"] == 4
    plan._store.async_save.side_effect = None
    await plan.async_update(snapshot(now=NOW + timedelta(minutes=1)))
    assert not plan.persistence_error


async def test_record_cap_and_overview_truncation_are_explicit(hass):
    plan = store(hass)
    many = tuple(
        replace(LEGS[0], summary=f"Fictional Rail {i}") for i in range(MAX_RECORDS + 2)
    )
    await plan.async_update(snapshot(many))
    attrs = plan.attributes(NOW)
    assert attrs["retained_booked_leg_count"] == MAX_RECORDS
    assert attrs["retained_plan_truncated"]
    await plan.async_update(snapshot((), NOW + timedelta(minutes=1)))
    assert plan.attributes(NOW)["retained_plan_truncated"]
    smaller = store(hass)
    await smaller.async_update(replace(snapshot(), booked_leg_count=17))
    assert smaller.attributes(NOW)["retained_plan_truncated"]


async def test_unknown_arrival_never_becomes_arrived_and_invalid_long_leg_is_ignored(
    hass,
):
    plan = store(hass)
    unknown = replace(LEGS[0], end=None)
    too_long = replace(LEGS[1], end=LEGS[1].start + timedelta(days=2))
    await plan.async_update(snapshot((unknown, too_long)))
    attrs = plan.attributes(NOW.replace(hour=10))
    assert attrs["retained_booked_leg_count"] == 1
    assert attrs["retained_booked_legs"][0]["booked_window"] == "arrival_unknown"


async def test_overnight_leg_survives_local_date_rollover_and_dst_offset_change(hass):
    london = ZoneInfo("Europe/London")
    start = datetime(2026, 10, 24, 23, 30, tzinfo=london)
    arrival = datetime(2026, 10, 25, 2, 30, tzinfo=london)
    overnight = replace(LEGS[0], start=start, end=arrival)
    before = start - timedelta(hours=1)
    plan = store(hass)
    await plan.async_update(snapshot((overnight,), before))
    between = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
    restored = await restart(hass, plan, between)
    attrs = restored.attributes(between)
    assert attrs["retained_booked_leg_count"] == 1
    assert attrs["retained_booked_legs"][0]["booked_window"] == "booked_underway"
    expiry = arrival.astimezone(UTC) + timedelta(hours=48)
    assert restored.attributes(expiry)["retained_booked_legs"] == []


async def test_load_error_does_not_block_operational_startup(hass, caplog):
    plan = store(hass)
    plan._store.async_load = AsyncMock(side_effect=OSError("private path"))
    await plan.async_load(NOW)
    assert plan.persistence_error
    assert "private path" not in caplog.text
    await plan.async_update(snapshot())
    assert plan.persistence_error
    assert plan.attributes(NOW)["retained_booked_leg_count"] == 4
    plan._store.async_save.assert_not_awaited()


async def test_live_rail_snapshot_without_overview_does_not_erase_plan(hass):
    engine = Mock(async_review=AsyncMock(return_value=snapshot()))
    coordinator = JourneyGuardianCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), engine
    )
    coordinator.travel_plan._store.async_save = AsyncMock()
    await coordinator._async_review_data()
    before = deepcopy(coordinator.travel_plan._legs)
    engine.async_review_live_rail = AsyncMock(
        return_value=replace(
            snapshot(),
            booked_legs=(),
            booked_leg_count=0,
        )
    )
    await coordinator.async_review_live_rail()
    assert coordinator.travel_plan._legs == before
