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
        return {
            "checked_at": self.coordinator.data.checked_at.isoformat(),
            "journey_end": (
                journey.end.isoformat() if journey and journey.end else None
            ),
            "origin_code": journey.origin_code if journey else None,
            "origin_name": journey.origin_name if journey else None,
            "destination_confirmation": (
                journey.destination_confirmation if journey else None
            ),
            "error": self.coordinator.data.error,
        }


class NextDepartureSensor(JourneyGuardianEntity, SensorEntity):
    """Next recognized calendar departure."""

    _attr_translation_key = "next_departure"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:train-clock"

    @property
    def native_value(self):
        journey = self.coordinator.data.next_journey
        return journey.start if journey else None


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
