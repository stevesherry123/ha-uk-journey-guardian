"""Tests for Journey Guardian entity presentation."""

from datetime import UTC, datetime
from unittest.mock import Mock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.journey_guardian.const import DOMAIN
from custom_components.journey_guardian.models import (
    BudgetSnapshot,
    JourneyEvent,
    JourneySnapshot,
    JourneyTiming,
    RailObservation,
)
from custom_components.journey_guardian.sensor import (
    JourneyStatusSensor,
    JourneyTimingSensor,
    NextDepartureSensor,
    OperationalPhaseSensor,
    RailDataFreshnessSensor,
)


def test_timing_sensor_exposes_provenance() -> None:
    """A calculated timestamp cannot be mistaken for live routing data."""
    timing = JourneyTiming(
        prepare_at=datetime(2026, 8, 29, 14, 35, tzinfo=UTC),
        leave_home_at=datetime(2026, 8, 29, 15, 15, tzinfo=UTC),
        station_arrival_at=datetime(2026, 8, 29, 16, 15, tzinfo=UTC),
        preparation_minutes=30,
        early_warning_minutes=10,
        station_buffer_minutes=15,
        station_access_minutes=60,
        source="configured_fallback",
        classification="inferred",
    )
    coordinator = Mock()
    coordinator.data.timing = timing
    entry = MockConfigEntry(domain=DOMAIN)
    sensor = JourneyTimingSensor(
        coordinator,
        entry,
        "leave_home_at",
        timing_attribute="leave_home_at",
        icon="mdi:home-export-outline",
    )

    assert sensor.native_value == timing.leave_home_at
    assert sensor.extra_state_attributes == {
        "source": "configured_fallback",
        "classification": "inferred",
        "preparation_minutes": 30,
        "early_warning_minutes": 10,
        "station_buffer_minutes": 15,
        "station_access_minutes": 60,
    }


def test_simulated_delay_is_visible_without_overwriting_schedule() -> None:
    """Entities expose the prediction while retaining its simulated provenance."""
    scheduled = datetime(2026, 9, 3, 10, 30, tzinfo=UTC)
    predicted = datetime(2026, 9, 3, 10, 50, tzinfo=UTC)
    journey = JourneyEvent(
        start=scheduled,
        end=datetime(2026, 9, 3, 11, 50, tzinfo=UTC),
        summary="Rail simulation - Simulation Origin to Simulation Destination",
        location="Simulation Origin",
        origin_code="SIM",
        origin_name="Simulation Origin",
        destination_confirmation="Simulation Destination",
        decision_path="simulation_delayed",
    )
    observation = RailObservation(
        scenario="delayed",
        source="simulation",
        classification="simulated",
        observed_at=datetime(2026, 9, 3, 9, 0, tzinfo=UTC),
        scheduled_departure=scheduled,
        predicted_departure=predicted,
        delay_minutes=20,
        cancelled=False,
        leg_count=1,
        provider_available=True,
        service_identity="0123456789abcdef",
        platform="4",
        match_quality="exact_schedule",
        schedule_offset_minutes=0,
    )
    coordinator = Mock()
    coordinator.data = JourneySnapshot(
        status="delayed",
        checked_at=datetime(2026, 9, 3, 9, 0, tzinfo=UTC),
        next_journey=journey,
        budget=BudgetSnapshot("2026-09-03", 0, 30, 3),
        rail_observation=observation,
        simulation_active=True,
        operational_phase="prepare_now",
    )
    entry = MockConfigEntry(domain=DOMAIN)

    next_departure = NextDepartureSensor(
        coordinator, entry, "next_departure"
    )
    status = JourneyStatusSensor(coordinator, entry, "status")
    phase = OperationalPhaseSensor(coordinator, entry, "operational_phase")
    freshness = RailDataFreshnessSensor(
        coordinator, entry, "rail_data_freshness"
    )

    assert next_departure.native_value == predicted
    assert phase.native_value == "prepare_now"
    assert freshness.native_value == "current"
    assert freshness.extra_state_attributes == {
        "age_seconds": 0,
        "source": "simulation",
        "classification": "simulated",
        "match_quality": "exact_schedule",
        "schedule_offset_minutes": 0,
    }
    assert status.extra_state_attributes["scheduled_departure"] == (
        scheduled.isoformat()
    )
    assert status.extra_state_attributes["predicted_departure"] == (
        predicted.isoformat()
    )
    assert status.extra_state_attributes["rail_source"] == "simulation"
    assert status.extra_state_attributes["rail_service_identity"] == (
        "0123456789abcdef"
    )
    assert status.extra_state_attributes["rail_platform"] == "4"
    assert status.extra_state_attributes["rail_match_quality"] == "exact_schedule"
    assert status.extra_state_attributes["rail_schedule_offset_minutes"] == 0
    assert status.extra_state_attributes["last_live_rail_error"] is None
    assert status.extra_state_attributes["simulation_active"] is True
