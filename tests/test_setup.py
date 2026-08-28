"""Tests for integration-wide Journey Guardian setup."""

from homeassistant.setup import async_setup_component

from custom_components.journey_guardian.const import (
    DOMAIN,
    SERVICE_REVIEW_NOW,
)


async def test_review_action_registered_without_entry(hass) -> None:
    """The integration action exists independently of config-entry reloads."""
    assert await async_setup_component(hass, DOMAIN, {})

    assert hass.services.has_service(DOMAIN, SERVICE_REVIEW_NOW)
    assert not hass.services.has_service(DOMAIN, "reset_api_budget")
