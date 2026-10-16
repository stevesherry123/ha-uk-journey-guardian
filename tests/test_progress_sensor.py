"""Home Assistant GPS source freshness and restart persistence."""

from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from test_progress import NOW, ZONES, snapshot

from custom_components.journey_guardian.const import DOMAIN
from custom_components.journey_guardian.progress_sensor import JourneyProgressSensor


async def test_sensor_uses_source_freshness_and_restores(hass, freezer):
    freezer.move_to(NOW)
    person_id = ".".join(("person", "example_traveller"))
    source_id = ".".join(("device_tracker", "example_phone"))
    for zone in ZONES:
        hass.states.async_set(
            zone.entity_id,
            "0",
            {
                "friendly_name": zone.name,
                "latitude": zone.latitude,
                "longitude": zone.longitude,
                "radius": zone.radius,
            },
        )
    hass.states.async_set(
        source_id,
        "not_home",
        {
            "latitude": 51,
            "longitude": 0,
            "gps_accuracy": 10,
            "source_type": "gps",
        },
    )
    hass.states.async_set(person_id, "not_home", {"source": source_id})
    coordinator = Mock(hass=hass, data=snapshot())
    entry = MockConfigEntry(domain=DOMAIN)
    zones = "\n".join(zone.entity_id for zone in ZONES)
    sensor = JourneyProgressSensor(coordinator, entry, person_id, zones)
    sensor.hass = hass
    sensor.entity_id = "sensor.example_station_progress"
    sensor.async_write_ha_state = Mock()
    sensor._store = Mock(async_load=AsyncMock(return_value=None))
    with patch(
        "custom_components.journey_guardian.progress_sensor."
        "JourneyGuardianEntity.async_added_to_hass",
        new_callable=AsyncMock,
    ):
        await sensor.async_added_to_hass()
        assert sensor.native_value == "near_station"
        saved = sensor._saved_data()
        assert set(saved) == {"key", "last_index", "observed_at"}
        assert "latitude" not in str(saved)
        freezer.tick(timedelta(minutes=6))
        # A fresh person state cannot make an old GPS fix fresh again.
        hass.states.async_set(person_id, "home", {"source": source_id})
        sensor._update()
        assert sensor.native_value == "location_stale"
        assert sensor.extra_state_attributes["last_observed_station"] == "Example 0"
        await sensor.async_remove()
        restored = JourneyProgressSensor(coordinator, entry, person_id, zones)
        restored.hass = hass
        restored.entity_id = sensor.entity_id
        restored.async_write_ha_state = Mock()
        restored._store = Mock(async_load=AsyncMock(return_value=saved))
        await restored.async_added_to_hass()
        assert restored.native_value == "location_stale"
        assert restored.extra_state_attributes["next_waypoint"] == "Example 1"
        hass.states.async_set(
            source_id,
            "not_home",
            {
                "latitude": 51.01,
                "longitude": 0,
                "gps_accuracy": 10,
                "source_type": "router",
            },
        )
        restored._update()
        assert restored.native_value == "location_unavailable"
        assert restored.extra_state_attributes["last_observed_station"] == "Example 0"
        hass.states.async_set(
            source_id,
            "not_home",
            {
                "latitude": 51.01,
                "longitude": 0,
                "gps_accuracy": 10,
                "source_type": "gps",
            },
        )
        restored._handle_coordinator_update()
        assert restored.native_value == "near_station"
        assert restored.extra_state_attributes["last_observed_station"] == "Example 1"
        assert (
            restored.extra_state_attributes["last_observed_at"]
            == dt_util.utcnow().isoformat()
        )
        await restored.async_remove()
