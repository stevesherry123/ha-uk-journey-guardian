"""Binary sensors exposed by Journey Guardian."""

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    """Set up Journey Guardian binary sensors."""
    async_add_entities(
        [
            DataHealthyBinarySensor(
                entry.runtime_data.coordinator, entry, "data_healthy"
            ),
            SimulationActiveBinarySensor(
                entry.runtime_data.coordinator, entry, "simulation_active"
            ),
        ]
    )


class DataHealthyBinarySensor(JourneyGuardianEntity, BinarySensorEntity):
    """Whether the most recent review completed successfully."""

    _attr_translation_key = "data_healthy"
    _attr_icon = "mdi:cloud-check"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.data_healthy


class SimulationActiveBinarySensor(JourneyGuardianEntity, BinarySensorEntity):
    """Whether live inputs are isolated by an explicit simulation."""

    _attr_translation_key = "simulation_active"
    _attr_icon = "mdi:test-tube"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.simulation_active
