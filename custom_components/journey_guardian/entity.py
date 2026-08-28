"""Base entity for Journey Guardian."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import JourneyGuardianCoordinator


class JourneyGuardianEntity(CoordinatorEntity[JourneyGuardianCoordinator]):
    """Entity tied to the shared Journey Guardian coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: JourneyGuardianCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        """Initialize a Journey Guardian entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=NAME,
            manufacturer="Journey Guardian",
            model="Travel decision engine",
        )
