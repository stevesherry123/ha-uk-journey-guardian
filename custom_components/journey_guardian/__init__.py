"""Journey Guardian integration setup."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .budget import TransportAPIBudget
from .const import (
    CONF_CALENDAR_ENTITY,
    CONF_DAILY_API_LIMIT,
    CONF_EARLY_WARNING_MINUTES,
    CONF_GOOGLE_ROUTES_API_KEY,
    CONF_PREPARATION_BUFFER_MINUTES,
    CONF_STATION_ACCESS_FALLBACK_MINUTES,
    CONF_STATION_BUFFER_MINUTES,
    CONF_TRANSPORTAPI_APP_ID,
    CONF_TRANSPORTAPI_APP_KEY,
    CONF_URGENT_API_RESERVE,
    DEFAULT_DAILY_API_LIMIT,
    DEFAULT_EARLY_WARNING_MINUTES,
    DEFAULT_PREPARATION_BUFFER_MINUTES,
    DEFAULT_STATION_ACCESS_FALLBACK_MINUTES,
    DEFAULT_STATION_BUFFER_MINUTES,
    DEFAULT_URGENT_API_RESERVE,
    DOMAIN,
    SERVICE_REVIEW_NOW,
)
from .coordinator import JourneyGuardianCoordinator
from .engine import JourneyGuardianEngine
from .runtime import JourneyGuardianRuntimeData

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Journey Guardian integration namespace."""
    _async_register_services(hass)
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

    settings = {**entry.data, **entry.options}
    engine = JourneyGuardianEngine(
        hass,
        calendar_entity=entry.data[CONF_CALENDAR_ENTITY],
        budget=budget,
        preparation_buffer_minutes=settings.get(
            CONF_PREPARATION_BUFFER_MINUTES,
            DEFAULT_PREPARATION_BUFFER_MINUTES,
        ),
        early_warning_minutes=settings.get(
            CONF_EARLY_WARNING_MINUTES, DEFAULT_EARLY_WARNING_MINUTES
        ),
        station_buffer_minutes=settings.get(
            CONF_STATION_BUFFER_MINUTES, DEFAULT_STATION_BUFFER_MINUTES
        ),
        station_access_fallback_minutes=settings.get(
            CONF_STATION_ACCESS_FALLBACK_MINUTES,
            DEFAULT_STATION_ACCESS_FALLBACK_MINUTES,
        ),
    )
    coordinator = JourneyGuardianCoordinator(hass, entry, engine)
    entry.runtime_data = JourneyGuardianRuntimeData(
        coordinator=coordinator, budget=budget
    )
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Journey Guardian config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _runtime(hass: HomeAssistant) -> JourneyGuardianRuntimeData:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED:
            return entry.runtime_data
    raise HomeAssistantError("Journey Guardian is not loaded")


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_REVIEW_NOW):
        return

    async def async_review_now(call: ServiceCall) -> dict:
        runtime = _runtime(hass)
        await runtime.coordinator.async_request_refresh()
        return runtime.coordinator.data.as_dict()

    hass.services.async_register(
        DOMAIN,
        SERVICE_REVIEW_NOW,
        async_review_now,
        schema=vol.Schema({}),
        supports_response=SupportsResponse.OPTIONAL,
    )


def configured_provider_credentials(entry: ConfigEntry) -> dict[str, str]:
    """Return provider credentials for future clients without logging them."""
    return {
        CONF_TRANSPORTAPI_APP_ID: entry.data.get(CONF_TRANSPORTAPI_APP_ID, ""),
        CONF_TRANSPORTAPI_APP_KEY: entry.data.get(CONF_TRANSPORTAPI_APP_KEY, ""),
        CONF_GOOGLE_ROUTES_API_KEY: entry.data.get(CONF_GOOGLE_ROUTES_API_KEY, ""),
    }
