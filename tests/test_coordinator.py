"""Tests for Journey Guardian coordinator polling."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

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

CHECKED_AT = datetime(2026, 8, 28, 14, 15, tzinfo=UTC)
BUDGET = BudgetSnapshot(
    date="2026-08-28",
    calls_used=0,
    daily_limit=30,
    urgent_reserve=3,
)


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
