"""Tests for Journey Guardian entity presentation."""

from datetime import UTC, datetime
from unittest.mock import Mock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.journey_guardian.const import DOMAIN
from custom_components.journey_guardian.models import JourneyTiming
from custom_components.journey_guardian.sensor import JourneyTimingSensor


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
