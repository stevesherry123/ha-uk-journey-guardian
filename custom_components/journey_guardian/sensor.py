"""Sensors exposed by Journey Guardian."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import JourneyGuardianEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Journey Guardian sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            JourneyStatusSensor(coordinator, entry, "status"),
            NextDepartureSensor(coordinator, entry, "next_departure"),
            JourneyTimingSensor(
                coordinator,
                entry,
                "prepare_at",
                timing_attribute="prepare_at",
                icon="mdi:alarm",
            ),
            JourneyTimingSensor(
                coordinator,
                entry,
                "leave_home_at",
                timing_attribute="leave_home_at",
                icon="mdi:home-export-outline",
            ),
            JourneyTimingSensor(
                coordinator,
                entry,
                "station_arrival_at",
                timing_attribute="station_arrival_at",
                icon="mdi:train-car-clock",
            ),
            DecisionPathSensor(coordinator, entry, "decision_path"),
            TransportAPICallsSensor(coordinator, entry, "transportapi_calls"),
        ]
    )


class JourneyStatusSensor(JourneyGuardianEntity, SensorEntity):
    """Overall engine state."""

    _attr_translation_key = "status"
    _attr_icon = "mdi:shield-check"

    @property
    def native_value(self) -> str:
        return self.coordinator.data.status

    @property
    def extra_state_attributes(self) -> dict:
        journey = self.coordinator.data.next_journey
        observation = self.coordinator.data.rail_observation
        return {
            "checked_at": self.coordinator.data.checked_at.isoformat(),
            "simulation_active": self.coordinator.data.simulation_active,
            "journey_end": (
                journey.end.isoformat() if journey and journey.end else None
            ),
            "origin_code": journey.origin_code if journey else None,
            "origin_name": journey.origin_name if journey else None,
            "destination_confirmation": (
                journey.destination_confirmation if journey else None
            ),
            "error": self.coordinator.data.error,
            "rail_source": observation.source if observation else None,
            "rail_classification": (
                observation.classification if observation else None
            ),
            "rail_scenario": observation.scenario if observation else None,
            "scheduled_departure": (
                observation.scheduled_departure.isoformat()
                if observation
                else None
            ),
            "predicted_departure": (
                observation.predicted_departure.isoformat()
                if observation and observation.predicted_departure
                else None
            ),
            "delay_minutes": observation.delay_minutes if observation else None,
            "cancelled": observation.cancelled if observation else None,
            "leg_count": observation.leg_count if observation else None,
            "provider_available": (
                observation.provider_available if observation else None
            ),
        }


class NextDepartureSensor(JourneyGuardianEntity, SensorEntity):
    """Next recognized calendar departure."""

    _attr_translation_key = "next_departure"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:train-clock"

    @property
    def native_value(self):
        observation = self.coordinator.data.rail_observation
        if observation and observation.predicted_departure:
            return observation.predicted_departure
        journey = self.coordinator.data.next_journey
        return journey.start if journey else None


class JourneyTimingSensor(JourneyGuardianEntity, SensorEntity):
    """One actionable timestamp from the normalized journey timing."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        key: str,
        *,
        timing_attribute: str,
        icon: str,
    ) -> None:
        """Initialize a journey timing sensor."""
        super().__init__(coordinator, entry, key)
        self._attr_translation_key = key
        self._attr_icon = icon
        self._timing_attribute = timing_attribute

    @property
    def native_value(self):
        timing = self.coordinator.data.timing
        return getattr(timing, self._timing_attribute) if timing else None

    @property
    def extra_state_attributes(self) -> dict:
        timing = self.coordinator.data.timing
        if timing is None:
            return {"source": None, "classification": None}
        return {
            "source": timing.source,
            "classification": timing.classification,
            "preparation_minutes": timing.preparation_minutes,
            "early_warning_minutes": timing.early_warning_minutes,
            "station_buffer_minutes": timing.station_buffer_minutes,
            "station_access_minutes": timing.station_access_minutes,
        }


class DecisionPathSensor(JourneyGuardianEntity, SensorEntity):
    """Review branch selected by the engine."""

    _attr_translation_key = "decision_path"
    _attr_icon = "mdi:source-branch"

    @property
    def native_value(self) -> str:
        journey = self.coordinator.data.next_journey
        return journey.decision_path if journey else "none"


class TransportAPICallsSensor(JourneyGuardianEntity, SensorEntity):
    """Daily shared TransportAPI call count."""

    _attr_translation_key = "transportapi_calls"
    _attr_icon = "mdi:counter"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> int:
        return self.coordinator.data.budget.calls_used

    @property
    def extra_state_attributes(self) -> dict:
        return self.coordinator.data.budget.as_dict()
