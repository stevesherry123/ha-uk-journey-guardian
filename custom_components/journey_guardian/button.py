"""Buttons exposed by Journey Guardian."""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import JourneyGuardianEntity
from .manual_review import ManualTravelReview


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Journey Guardian buttons."""
    async_add_entities(
        [
            TravelReviewNowButton(
                entry.runtime_data.coordinator, entry, entry.runtime_data.manual_review
            ),
            ReviewNowButton(entry.runtime_data.coordinator, entry, "review_now"),
            LiveRailReviewButton(
                entry.runtime_data.coordinator, entry, "review_rail_now"
            ),
            StationAccessTestButton(
                entry.runtime_data.coordinator, entry, "test_station_access"
            ),
        ]
    )


class TravelReviewNowButton(JourneyGuardianEntity, ButtonEntity):
    """Run the same briefing as the public travel-review action."""

    _attr_translation_key = "travel_review_now"
    _attr_icon = "mdi:train-car-passenger"

    def __init__(self, coordinator, entry, review: ManualTravelReview) -> None:
        super().__init__(coordinator, entry, "travel_review_now")
        self._review = review

    async def async_press(self) -> None:
        await self._review.async_run()


class ReviewNowButton(JourneyGuardianEntity, ButtonEntity):
    """Request an immediate calendar and decision-path review."""

    _attr_translation_key = "review_now"
    _attr_icon = "mdi:map-search"

    async def async_press(self) -> None:
        await self.coordinator.async_refresh_calendar_and_review()


class LiveRailReviewButton(JourneyGuardianEntity, ButtonEntity):
    """Explicitly spend quota on one live rail review."""

    _attr_translation_key = "review_rail_now"
    _attr_icon = "mdi:train-clock"

    async def async_press(self) -> None:
        await self.coordinator.async_review_live_rail(force_calendar_refresh=True)


class StationAccessTestButton(JourneyGuardianEntity, ButtonEntity):
    """Force an immediate live route to the selected journey station."""

    _attr_translation_key = "test_station_access"
    _attr_icon = "mdi:routes-clock"

    async def async_press(self) -> None:
        await self.coordinator.async_test_station_access()
