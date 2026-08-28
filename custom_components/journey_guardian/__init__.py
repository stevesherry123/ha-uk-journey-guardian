"""Journey Guardian integration setup."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .budget import TransportAPIBudget
from .const import (
    CONF_CALENDAR_ENTITY,
    CONF_DAILY_API_LIMIT,
    CONF_GOOGLE_ROUTES_API_KEY,
    CONF_TRANSPORTAPI_APP_ID,
    CONF_TRANSPORTAPI_APP_KEY,
    CONF_URGENT_API_RESERVE,
    DEFAULT_DAILY_API_LIMIT,
    DEFAULT_URGENT_API_RESERVE,
    DOMAIN,
    SERVICE_RESET_API_BUDGET,
    SERVICE_REVIEW_NOW,
)
from .coordinator import JourneyGuardianCoordinator
from .engine import JourneyGuardianEngine
from .runtime import JourneyGuardianRuntimeData

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Journey Guardian integration namespace."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Journey Guardian from a UI config entry."""
    budget = TransportAPIBudget(
        hass,
        daily_limit=entry.data.get(
            CONF_DAILY_API_LIMIT, DEFAULT_DAILY_API_LIMIT
        ),
        urgent_reserve=entry.data.get(
            CONF_URGENT_API_RESERVE, DEFAULT_URGENT_API_RESERVE
        ),
    )
    await budget.async_load()

    engine = JourneyGuardianEngine(
        hass,
        calendar_entity=entry.data[CONF_CALENDAR_ENTITY],
        budget=budget,
    )
    coordinator = JourneyGuardianCoordinator(hass, entry, engine)
    entry.runtime_data = JourneyGuardianRuntimeData(
        coordinator=coordinator, budget=budget
    )
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Journey Guardian config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.services.async_remove(DOMAIN, SERVICE_REVIEW_NOW)
        hass.services.async_remove(DOMAIN, SERVICE_RESET_API_BUDGET)
    return unloaded


def _runtime(hass: HomeAssistant) -> JourneyGuardianRuntimeData:
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries or not hasattr(entries[0], "runtime_data"):
        raise HomeAssistantError("Journey Guardian is not configured")
    return entries[0].runtime_data


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_REVIEW_NOW):
        return

    async def async_review_now(call: ServiceCall) -> dict:
        runtime = _runtime(hass)
        await runtime.coordinator.async_request_refresh()
        return runtime.coordinator.data.as_dict()

    async def async_reset_api_budget(call: ServiceCall) -> dict:
        runtime = _runtime(hass)
        await runtime.budget.async_reset()
        await runtime.coordinator.async_request_refresh()
        return runtime.budget.snapshot().as_dict()

    hass.services.async_register(
        DOMAIN,
        SERVICE_REVIEW_NOW,
        async_review_now,
        schema=vol.Schema({}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_API_BUDGET,
        async_reset_api_budget,
        schema=vol.Schema({}),
        supports_response=SupportsResponse.OPTIONAL,
    )


def configured_provider_credentials(entry: ConfigEntry) -> dict[str, str]:
    """Return provider credentials for future clients without logging them."""
    return {
        CONF_TRANSPORTAPI_APP_ID: entry.data[CONF_TRANSPORTAPI_APP_ID],
        CONF_TRANSPORTAPI_APP_KEY: entry.data[CONF_TRANSPORTAPI_APP_KEY],
        CONF_GOOGLE_ROUTES_API_KEY: entry.data[CONF_GOOGLE_ROUTES_API_KEY],
    }
