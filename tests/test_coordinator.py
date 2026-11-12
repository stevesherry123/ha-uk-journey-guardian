"""Tests for Journey Guardian coordinator polling."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.journey_guardian.const import (
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.journey_guardian.coordinator import JourneyGuardianCoordinator
from custom_components.journey_guardian.models import (
    BudgetSnapshot,
    JourneyEvent,
    JourneySnapshot,
    JourneyTiming,
    RailObservation,
)
from custom_components.journey_guardian.railinfo_booking_match import (
    BookingMatchProposal,
    BookingMatchRequest,
    BookingMatchResult,
)

CHECKED_AT = datetime(2026, 8, 28, 14, 15, tzinfo=UTC)
CALENDAR_ENTITY = ".".join(("calendar", "example_travel"))
BUDGET = BudgetSnapshot(
    date="2026-08-28",
    calls_used=0,
    daily_limit=30,
    urgent_reserve=3,
)


def _idle_snapshot() -> JourneySnapshot:
    return JourneySnapshot(
        status="idle",
        checked_at=CHECKED_AT,
        next_journey=None,
        budget=BUDGET,
    )


@pytest.mark.parametrize("state", ["current", "edited", "simulation", "changed"])
async def test_booking_match_is_read_only_and_rejects_changed_context(hass, state):
    booking = JourneyEvent(
        CHECKED_AT + timedelta(hours=1), CHECKED_AT + timedelta(hours=2),
        "Example Central to Sample Harbour", "", "EXC", "Example Central",
        "Sample Harbour", "calendar_route",
    )
    request = BookingMatchRequest(booking, "EXC", "SMP", "EXJ")
    snapshot = replace(
        _idle_snapshot(),
        next_journey=replace(booking, end=None) if state == "edited" else booking,
        simulation_active=state == "simulation",
    )
    engine = Mock()
    coordinator = JourneyGuardianCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), engine
    )
    coordinator.data = snapshot

    async def lookup(_request):
        if state == "changed":
            coordinator.data = _idle_snapshot()
        return BookingMatchResult("no_match")

    engine.async_booking_match = AsyncMock(side_effect=lookup)
    result = await coordinator.async_booking_match(request)
    if state in ("edited", "simulation"):
        engine.async_booking_match.assert_not_awaited()
        assert result.status == "booking_match_context_unavailable"
    elif state == "changed":
        assert result.status == "booking_match_context_changed"
        assert coordinator.data.next_journey is None
    else:
        engine.async_booking_match.assert_awaited_once_with(request)
        assert result.status == "no_match"
        assert coordinator.data is snapshot


@pytest.mark.parametrize("condition", ["current", "expired", "edited", "wrong_id"])
async def test_confirmation_applies_only_to_current_unexpired_proposal(hass, condition):
    booking = JourneyEvent(
        CHECKED_AT + timedelta(hours=1), CHECKED_AT + timedelta(hours=2),
        "Example Central to Sample Harbour", "", "EXC", "Example Central",
        "Sample Harbour", "calendar_route",
    )
    request = BookingMatchRequest(booking, "EXC", "SMP", "EXJ")
    proposal = BookingMatchProposal(
        booking.booking_fingerprint, "a" * 16, "EXC", "EXJ",
        booking.start, booking.end, CHECKED_AT, CHECKED_AT + timedelta(minutes=5),
    )
    engine = Mock(async_booking_match=AsyncMock(
        return_value=BookingMatchResult("proposal_available", proposal)
    ))
    coordinator = JourneyGuardianCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), engine
    )
    coordinator.data = replace(_idle_snapshot(), next_journey=booking)
    await coordinator.async_booking_match(request)
    if condition == "edited":
        coordinator.data = replace(
            coordinator.data, next_journey=replace(booking, end=None)
        )
    snapshot = coordinator.data
    proposal_id = "b" * 64 if condition == "wrong_id" else proposal.proposal_id
    with patch(
        "custom_components.journey_guardian.coordinator.dt_util.utcnow",
        return_value=proposal.valid_until if condition == "expired" else CHECKED_AT,
    ):
        result = coordinator.confirm_booking_match(proposal_id)
    if condition == "current":
        assert result.status == "proposal_confirmed"
        assert result.as_dict()["proposal"]["confirmation_required"] is False
    else:
        assert result.status == "booking_match_confirmation_unavailable"
        assert result.proposal is None
    assert coordinator.data is snapshot
    engine.async_booking_match.assert_awaited_once()


async def test_new_investigation_discards_older_in_flight_result(hass):
    booking = JourneyEvent(
        CHECKED_AT + timedelta(hours=1), CHECKED_AT + timedelta(hours=2),
        "Example Central to Sample Harbour", "", "EXC", "Example Central",
        "Sample Harbour", "calendar_route",
    )
    old_request = BookingMatchRequest(booking, "EXC", "SMP", "EXJ")
    new_request = BookingMatchRequest(booking, "EXC", "SMP", "EXO")
    started, finish = asyncio.Event(), asyncio.Event()
    proposal = BookingMatchProposal(
        booking.booking_fingerprint, "a" * 16, "EXC", "EXJ",
        booking.start, booking.end, CHECKED_AT, CHECKED_AT + timedelta(minutes=5),
    )

    async def lookup(request):
        if request == old_request:
            started.set()
            await finish.wait()
            return BookingMatchResult("proposal_available", proposal)
        return BookingMatchResult("no_match")

    coordinator = JourneyGuardianCoordinator(
        hass, MockConfigEntry(domain=DOMAIN),
        Mock(async_booking_match=AsyncMock(side_effect=lookup)),
    )
    coordinator.data = replace(_idle_snapshot(), next_journey=booking)
    async with asyncio.TaskGroup() as group:
        older = group.create_task(coordinator.async_booking_match(old_request))
        await started.wait()
        try:
            newer = await coordinator.async_booking_match(new_request)
            assert newer.status == "no_match"
        finally:
            finish.set()
    assert older.result().status == "booking_match_context_changed"
    with patch(
        "custom_components.journey_guardian.coordinator.dt_util.utcnow",
        return_value=CHECKED_AT,
    ):
        assert coordinator.confirm_booking_match(proposal.proposal_id).proposal is None


async def test_calendar_source_refresh_obeys_configured_interval(hass) -> None:
    """The upstream calendar is refreshed at startup and when next due."""
    hass.states.async_set(CALENDAR_ENTITY, "off")
    engine = Mock()
    engine.async_review = AsyncMock(return_value=_idle_snapshot())
    coordinator = JourneyGuardianCoordinator(
        hass,
        MockConfigEntry(domain=DOMAIN),
        engine,
        calendar_entity=CALENDAR_ENTITY,
        calendar_refresh_interval_minutes=1440,
    )
    update_entity = AsyncMock()
    hass.services.async_register("homeassistant", "update_entity", update_entity)

    with patch(
        "custom_components.journey_guardian.coordinator.dt_util.now",
        side_effect=(
            CHECKED_AT,
            CHECKED_AT + timedelta(hours=12),
            CHECKED_AT + timedelta(days=1),
        ),
    ):
        await coordinator._async_update_data()
        await coordinator._async_update_data()
        await coordinator._async_update_data()

    assert update_entity.await_count == 2
    assert update_entity.await_args.args[0].data == {"entity_id": CALENDAR_ENTITY}
    assert coordinator.last_calendar_source_refresh_at == CHECKED_AT + timedelta(days=1)


async def test_travel_review_forces_access_without_an_extra_calendar_review(hass):
    engine = Mock(async_review=AsyncMock(return_value=_idle_snapshot()))
    coordinator = JourneyGuardianCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), engine
    )
    coordinator.async_refresh_calendar_source = AsyncMock()
    result = await coordinator.async_refresh_calendar_and_review(
        force_station_access=True
    )
    engine.async_review.assert_awaited_once_with(force_station_access=True)
    assert result == coordinator.data == _idle_snapshot()


async def test_calendar_source_refresh_can_be_disabled(hass) -> None:
    """A zero interval leaves source polling to the calendar integration."""
    engine = Mock()
    engine.async_review = AsyncMock(return_value=_idle_snapshot())
    coordinator = JourneyGuardianCoordinator(
        hass,
        MockConfigEntry(domain=DOMAIN),
        engine,
        calendar_entity=CALENDAR_ENTITY,
        calendar_refresh_interval_minutes=0,
    )
    update_entity = AsyncMock()
    hass.services.async_register("homeassistant", "update_entity", update_entity)

    await coordinator._async_update_data()

    update_entity.assert_not_awaited()
    engine.async_review.assert_awaited_once_with()


async def test_forced_calendar_source_refresh_ignores_interval(hass) -> None:
    """The manual refresh path always updates the selected source calendar."""
    hass.states.async_set(CALENDAR_ENTITY, "off")
    coordinator = JourneyGuardianCoordinator(
        hass,
        MockConfigEntry(domain=DOMAIN),
        Mock(),
        calendar_entity=CALENDAR_ENTITY,
        calendar_refresh_interval_minutes=1440,
    )
    coordinator.last_calendar_source_refresh_at = CHECKED_AT
    update_entity = AsyncMock()
    hass.services.async_register("homeassistant", "update_entity", update_entity)

    with patch(
        "custom_components.journey_guardian.coordinator.dt_util.now",
        return_value=CHECKED_AT + timedelta(minutes=1),
    ):
        refreshed = await coordinator.async_refresh_calendar_source(force=True)

    assert refreshed is True
    update_entity.assert_awaited_once()


async def test_calendar_source_refresh_failure_uses_cached_calendar(hass) -> None:
    """A source update failure does not block the cached calendar review."""
    hass.states.async_set(CALENDAR_ENTITY, "off")
    engine = Mock()
    engine.async_review = AsyncMock(return_value=_idle_snapshot())
    coordinator = JourneyGuardianCoordinator(
        hass,
        MockConfigEntry(domain=DOMAIN),
        engine,
        calendar_entity=CALENDAR_ENTITY,
        calendar_refresh_interval_minutes=1440,
    )
    update_entity = AsyncMock(side_effect=HomeAssistantError("unavailable"))
    hass.services.async_register("homeassistant", "update_entity", update_entity)

    snapshot = await coordinator._async_update_data()

    assert snapshot.status == "idle"
    assert coordinator.last_calendar_source_refresh_error == "HomeAssistantError"
    engine.async_review.assert_awaited_once_with()


async def test_calendar_source_refresh_waits_for_entity(hass) -> None:
    """Startup cannot ask Home Assistant to update an unloaded calendar."""
    coordinator = JourneyGuardianCoordinator(
        hass,
        MockConfigEntry(domain=DOMAIN),
        Mock(),
        calendar_entity=CALENDAR_ENTITY,
        calendar_refresh_interval_minutes=1440,
    )
    update_entity = AsyncMock()
    hass.services.async_register("homeassistant", "update_entity", update_entity)

    assert await coordinator.async_refresh_calendar_source(force=True) is False
    assert coordinator.last_calendar_source_refresh_error == "calendar_unavailable"
    update_entity.assert_not_awaited()

    hass.states.async_set(CALENDAR_ENTITY, "off")

    assert await coordinator.async_refresh_calendar_source(force=True) is True
    assert coordinator.last_calendar_source_refresh_error is None
    update_entity.assert_awaited_once()


async def test_error_retains_normal_polling_interval(hass) -> None:
    """Temporary calendar failures do not create aggressive polling."""
    engine = Mock()
    engine.async_review = AsyncMock(
        return_value=JourneySnapshot(
            status="error",
            checked_at=CHECKED_AT,
            next_journey=None,
            budget=BUDGET,
            error="calendar_unavailable",
        )
    )
    coordinator = JourneyGuardianCoordinator(
        hass,
        MockConfigEntry(domain=DOMAIN),
        engine,
    )

    error_snapshot = await coordinator._async_update_data()

    assert error_snapshot.status == "error"
    assert coordinator.update_interval == DEFAULT_UPDATE_INTERVAL


async def test_active_refresh_retains_last_observation_as_historical(hass) -> None:
    """Departure refreshes preserve the final provider evidence."""
    departure = CHECKED_AT - timedelta(minutes=1)
    journey = JourneyEvent(
        start=departure,
        end=departure + timedelta(hours=2),
        summary="Example rail journey",
        location="Example Central",
        origin_code="CALENDAR",
        origin_name="Example Central",
        destination_confirmation="Sample Harbour",
        decision_path="calendar_route",
    )
    resolved_journey = JourneyEvent(
        start=departure,
        end=journey.end,
        summary=journey.summary,
        location=journey.location,
        origin_code="EXC",
        origin_name="Example Central",
        destination_confirmation="Sample Harbour",
        decision_path="transportapi_automatic",
    )
    observation = RailObservation(
        scenario="observed",
        source="transportapi",
        classification="provider_normalized",
        observed_at=CHECKED_AT - timedelta(minutes=10),
        scheduled_departure=departure,
        predicted_departure=None,
        delay_minutes=0,
        cancelled=False,
        leg_count=1,
        provider_available=True,
        service_identity="service-one",
        platform="15",
        match_quality="exact_schedule",
    )
    engine = Mock()
    engine.async_review = AsyncMock(
        return_value=JourneySnapshot(
            status="active",
            checked_at=CHECKED_AT,
            next_journey=journey,
            budget=BUDGET,
        )
    )
    coordinator = JourneyGuardianCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), engine
    )
    coordinator._last_live_snapshot = JourneySnapshot(
        status="planned",
        checked_at=observation.observed_at,
        next_journey=resolved_journey,
        budget=BUDGET,
        rail_observation=observation,
    )

    snapshot = await coordinator._async_update_data()

    assert snapshot.next_journey == resolved_journey
    assert snapshot.rail_observation is not None
    assert snapshot.rail_observation.freshness == "historical"
    assert snapshot.rail_observation.age_seconds == 600
    assert snapshot.rail_observation.retained is True
    assert snapshot.rail_observation.platform == "15"


async def test_planned_refresh_retains_live_observation(hass) -> None:
    """Routine calendar polling cannot erase pre-departure provider evidence."""
    departure = CHECKED_AT + timedelta(hours=2)
    journey = JourneyEvent(
        start=departure,
        end=departure + timedelta(hours=2),
        summary="Example rail journey",
        location="Example Central",
        origin_code="CALENDAR",
        origin_name="Example Central",
        destination_confirmation="Sample Harbour",
        decision_path="calendar_route",
    )
    timing = JourneyTiming(
        prepare_at=departure - timedelta(hours=2),
        leave_home_at=departure - timedelta(hours=1),
        station_arrival_at=departure - timedelta(minutes=15),
        preparation_minutes=30,
        early_warning_minutes=10,
        station_buffer_minutes=15,
        station_access_minutes=45,
        source="google_routes",
        classification="cached_driving",
    )
    observation = RailObservation(
        scenario="observed",
        source="transportapi",
        classification="provider_normalized",
        observed_at=CHECKED_AT - timedelta(minutes=10),
        scheduled_departure=departure,
        predicted_departure=None,
        delay_minutes=0,
        cancelled=False,
        leg_count=1,
        provider_available=True,
        service_identity="service-one",
        match_quality="exact_schedule",
    )
    engine = Mock()
    engine.async_review = AsyncMock(
        return_value=JourneySnapshot(
            status="planned",
            checked_at=CHECKED_AT,
            next_journey=journey,
            budget=BUDGET,
            timing=timing,
            operational_phase="waiting",
        )
    )
    coordinator = JourneyGuardianCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), engine
    )
    coordinator._last_live_snapshot = JourneySnapshot(
        status="planned",
        checked_at=observation.observed_at,
        next_journey=replace(
            journey,
            origin_code="EXC",
            decision_path="transportapi_automatic",
        ),
        budget=BUDGET,
        timing=timing,
        rail_observation=observation,
    )

    snapshot = await coordinator._async_update_data()

    assert snapshot.rail_observation is not None
    assert snapshot.rail_observation.freshness == "retained"
    assert snapshot.rail_observation.retained is True
    assert snapshot.rail_observation.age_seconds == 600
    assert snapshot.next_journey is not None
    assert snapshot.next_journey.decision_path == "transportapi_automatic"

    route_snapshot = await coordinator.async_test_station_access()

    assert route_snapshot.rail_observation is not None
    assert route_snapshot.rail_observation.freshness == "retained"


async def test_retained_delay_keeps_calendar_anchored_timing(hass) -> None:
    """A route refresh preserves a delay without relaxing the leave plan."""
    departure = CHECKED_AT + timedelta(hours=2)
    predicted = departure + timedelta(minutes=20)
    journey = JourneyEvent(
        start=departure,
        end=departure + timedelta(hours=2),
        summary="Example delayed rail journey",
        location="Example Central",
        origin_code="CALENDAR",
        origin_name="Example Central",
        destination_confirmation="Sample Harbour",
        decision_path="calendar_route",
    )
    timing = JourneyTiming(
        prepare_at=departure - timedelta(hours=2),
        leave_home_at=departure - timedelta(hours=1),
        station_arrival_at=departure - timedelta(minutes=15),
        preparation_minutes=30,
        early_warning_minutes=10,
        station_buffer_minutes=15,
        station_access_minutes=45,
        source="google_routes",
        classification="live_driving",
    )
    observation = RailObservation(
        scenario="observed",
        source="transportapi",
        classification="provider_normalized",
        observed_at=CHECKED_AT - timedelta(minutes=10),
        scheduled_departure=departure,
        predicted_departure=predicted,
        delay_minutes=20,
        cancelled=False,
        leg_count=1,
        provider_available=True,
        service_identity="service-delayed",
        match_quality="exact_schedule",
    )
    engine = Mock()
    engine.async_review = AsyncMock(
        return_value=JourneySnapshot(
            status="planned",
            checked_at=CHECKED_AT,
            next_journey=journey,
            budget=BUDGET,
            timing=timing,
            operational_phase="waiting",
        )
    )
    coordinator = JourneyGuardianCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), engine
    )
    coordinator._last_live_snapshot = JourneySnapshot(
        status="delayed",
        checked_at=observation.observed_at,
        next_journey=journey,
        budget=BUDGET,
        timing=timing,
        rail_observation=observation,
    )

    snapshot = await coordinator._async_update_data()

    assert snapshot.status == "delayed"
    assert snapshot.timing is not None
    assert snapshot.timing.leave_home_at == timing.leave_home_at
    assert snapshot.rail_observation is not None
    assert snapshot.rail_observation.freshness == "retained"


async def test_station_access_test_forces_provider_refresh(hass) -> None:
    """The explicit route test bypasses a previously valid cache entry."""
    snapshot = JourneySnapshot(
        status="planned",
        checked_at=CHECKED_AT,
        next_journey=None,
        budget=BUDGET,
    )
    engine = Mock()
    engine.async_review = AsyncMock(return_value=snapshot)
    coordinator = JourneyGuardianCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), engine
    )

    result = await coordinator.async_test_station_access()

    assert result == snapshot
    engine.async_review.assert_awaited_once_with(force_station_access=True)
    assert coordinator.last_station_access_test_at == CHECKED_AT
    assert coordinator.data == snapshot
    engine.reset_google_access_backoff.assert_called_once_with()


async def test_automatic_station_checkpoint_cannot_reset_access_backoff(hass):
    snapshot = JourneySnapshot(
        status="idle", checked_at=CHECKED_AT, next_journey=None, budget=BUDGET
    )
    engine = Mock(async_review=AsyncMock(return_value=snapshot))
    coordinator = JourneyGuardianCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), engine
    )
    await coordinator.async_test_station_access(automatic=True)
    engine.reset_google_access_backoff.assert_not_called()


async def test_google_denial_creates_repair_on_first_coordinator_review(hass):
    from homeassistant.helpers import issue_registry as ir

    from custom_components.journey_guardian.timing import calculate_fallback_timing

    journey = JourneyEvent(
        CHECKED_AT + timedelta(hours=2), CHECKED_AT + timedelta(hours=3),
        "Rail - Example Central to Sample Harbour", "Example Central",
        "CALENDAR", "Example Central", "Sample Harbour", "calendar_route",
    )
    timing = calculate_fallback_timing(
        journey, preparation_minutes=30, early_warning_minutes=15,
        station_buffer_minutes=25, station_access_minutes=60,
    )
    timing = replace(timing, station_access_error="google_routes_permission_denied")
    snapshot = replace(_idle_snapshot(), next_journey=journey, timing=timing)
    engine = Mock(async_review=AsyncMock(return_value=snapshot))
    coordinator = JourneyGuardianCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), engine
    )
    await coordinator._async_update_data()
    key = (DOMAIN, "google_routes_access")
    assert key in ir.async_get(hass).issues
    engine.async_review.return_value = _idle_snapshot()
    await coordinator._async_update_data()
    assert key in ir.async_get(hass).issues


async def test_sustained_calendar_repair_uses_real_review_results(hass):
    from homeassistant.helpers import issue_registry as ir

    engine = Mock()
    coordinator = JourneyGuardianCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), engine
    )
    for minute in (0, 15, 30):
        engine.async_review = AsyncMock(return_value=replace(
            _idle_snapshot(), checked_at=CHECKED_AT + timedelta(minutes=minute),
            error="calendar_unavailable", status="error",
        ))
        await coordinator._async_update_data()
    assert (DOMAIN, "sustained_calendar") in ir.async_get(hass).issues
    engine.async_review = AsyncMock(return_value=replace(
        _idle_snapshot(), checked_at=CHECKED_AT + timedelta(minutes=31)
    ))
    await coordinator._async_update_data()
    assert (DOMAIN, "sustained_calendar") not in ir.async_get(hass).issues
    assert coordinator.last_successful_calendar_review_at == (
        CHECKED_AT + timedelta(minutes=31)
    )


async def test_upstream_refresh_error_does_not_count_each_cached_read_as_retry(hass):
    coordinator = JourneyGuardianCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), Mock()
    )
    coordinator.last_calendar_source_refresh_error = "HomeAssistantError"
    coordinator._last_calendar_source_refresh_attempt_at = CHECKED_AT
    for minute in (0, 15, 30, 45):
        coordinator._update_health_issues(replace(
            _idle_snapshot(), checked_at=CHECKED_AT + timedelta(minutes=minute)
        ))
    assert coordinator.health_issues._counts["calendar"] == 1


@pytest.mark.parametrize("state", [None, "unavailable", "unknown"])
async def test_silent_failed_refresh_does_not_record_success(hass, state):
    hass.states.async_set(CALENDAR_ENTITY, "off")
    coordinator = JourneyGuardianCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), Mock(), calendar_entity=CALENDAR_ENTITY,
        calendar_refresh_interval_minutes=1440,
    )
    coordinator.last_calendar_source_refresh_at = CHECKED_AT - timedelta(hours=1)

    async def refresh(_call):
        if state is None:
            hass.states.async_remove(CALENDAR_ENTITY)
        else:
            hass.states.async_set(CALENDAR_ENTITY, state)

    hass.services.async_register("homeassistant", "update_entity", refresh)
    assert not await coordinator.async_refresh_calendar_source(force=True)
    assert coordinator.last_calendar_source_refresh_error == "calendar_unavailable"
    assert coordinator.last_calendar_source_refresh_at == (
        CHECKED_AT - timedelta(hours=1)
    )


async def test_failed_manual_refresh_retries_without_waiting_a_whole_day(hass):
    hass.states.async_set(CALENDAR_ENTITY, "off")
    coordinator = JourneyGuardianCoordinator(
        hass, MockConfigEntry(domain=DOMAIN), Mock(), calendar_entity=CALENDAR_ENTITY,
        calendar_refresh_interval_minutes=1440,
    )
    coordinator.last_calendar_source_refresh_at = CHECKED_AT - timedelta(hours=1)
    refresh = AsyncMock(side_effect=HomeAssistantError("private source details"))
    hass.services.async_register("homeassistant", "update_entity", refresh)
    with patch("custom_components.journey_guardian.coordinator.dt_util.now",
               return_value=CHECKED_AT):
        assert not await coordinator.async_refresh_calendar_source(force=True)
    refresh.side_effect = None
    with patch("custom_components.journey_guardian.coordinator.dt_util.now",
               return_value=CHECKED_AT + timedelta(minutes=14)):
        assert not await coordinator.async_refresh_calendar_source()
    assert refresh.await_count == 1
    with patch("custom_components.journey_guardian.coordinator.dt_util.now",
               return_value=CHECKED_AT + timedelta(minutes=15)):
        assert await coordinator.async_refresh_calendar_source()
    assert refresh.await_count == 2
    assert coordinator.last_calendar_source_refresh_error is None
    with patch("custom_components.journey_guardian.coordinator.dt_util.now",
               return_value=CHECKED_AT + timedelta(hours=1)):
        assert not await coordinator.async_refresh_calendar_source()
    assert refresh.await_count == 2
