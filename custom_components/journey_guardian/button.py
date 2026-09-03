"""Buttons exposed by Journey Guardian."""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import JourneyGuardianEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Journey Guardian buttons."""
    async_add_entities(
        [
            ReviewNowButton(entry.runtime_data.coordinator, entry, "review_now"),
            LiveRailReviewButton(
                entry.runtime_data.coordinator, entry, "review_rail_now"
            ),
        ]
    )


class ReviewNowButton(JourneyGuardianEntity, ButtonEntity):
    """Request an immediate calendar and decision-path review."""

    _attr_translation_key = "review_now"
    _attr_icon = "mdi:map-search"

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()


class LiveRailReviewButton(JourneyGuardianEntity, ButtonEntity):
    """Explicitly spend quota on one live rail review."""

    _attr_translation_key = "review_rail_now"
    _attr_icon = "mdi:train-clock"

    async def async_press(self) -> None:
        await self.coordinator.async_review_live_rail()
