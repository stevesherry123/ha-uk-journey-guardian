"""Journey Guardian integration setup."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .budget import TransportAPIBudget
from .const import (
    ATTR_ACCELERATED,
    ATTR_DELAY_MINUTES,
    ATTR_DEPARTURE_IN_MINUTES,
    ATTR_DURATION_MINUTES,
    ATTR_SCENARIO,
    CONF_CALENDAR_ENTITY,
    CONF_DAILY_API_LIMIT,
    CONF_EARLY_WARNING_MINUTES,
    CONF_GOOGLE_ROUTES_API_KEY,
    CONF_LIVE_NOTIFICATIONS_ENABLED,
    CONF_PREPARATION_BUFFER_MINUTES,
    CONF_STATION_ACCESS_FALLBACK_MINUTES,
    CONF_STATION_BUFFER_MINUTES,
    CONF_TRANSPORTAPI_APP_ID,
    CONF_TRANSPORTAPI_APP_KEY,
    CONF_URGENT_API_RESERVE,
    DEFAULT_DAILY_API_LIMIT,
    DEFAULT_EARLY_WARNING_MINUTES,
    DEFAULT_LIVE_NOTIFICATIONS_ENABLED,
    DEFAULT_PREPARATION_BUFFER_MINUTES,
    DEFAULT_SIMULATION_DEPARTURE_MINUTES,
    DEFAULT_STATION_ACCESS_FALLBACK_MINUTES,
    DEFAULT_STATION_BUFFER_MINUTES,
    DEFAULT_URGENT_API_RESERVE,
    DOMAIN,
    SERVICE_CLEAR_SIMULATION,
    SERVICE_REVIEW_NOW,
    SERVICE_SIMULATE_JOURNEY,
    SIMULATION_SCENARIOS,
)
from .coordinator import JourneyGuardianCoordinator
from .engine import JourneyGuardianEngine
from .notification import JourneyNotificationScheduler, NotificationLedger
from .runtime import JourneyGuardianRuntimeData
from .simulation import JourneySimulation

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
    simulation = JourneySimulation()
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
        simulation=simulation,
    )
    coordinator = JourneyGuardianCoordinator(hass, entry, engine)
    notification_ledger = NotificationLedger(hass)
    await notification_ledger.async_load()
    notification_scheduler = JourneyNotificationScheduler(
        hass,
        coordinator,
        notification_ledger,
        live_notifications_enabled=settings.get(
            CONF_LIVE_NOTIFICATIONS_ENABLED,
            DEFAULT_LIVE_NOTIFICATIONS_ENABLED,
        ),
    )
    entry.runtime_data = JourneyGuardianRuntimeData(
        coordinator=coordinator,
        budget=budget,
        simulation=simulation,
        notification_scheduler=notification_scheduler,
    )
    await coordinator.async_config_entry_first_refresh()
    notification_scheduler.start()
    entry.async_on_unload(notification_scheduler.stop)
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
    async def async_review_now(call: ServiceCall) -> dict:
        runtime = _runtime(hass)
        await runtime.coordinator.async_request_refresh()
        return runtime.coordinator.data.as_dict()

    async def async_simulate_journey(call: ServiceCall) -> dict:
        runtime = _runtime(hass)
        runtime.simulation.activate(
            scenario=call.data[ATTR_SCENARIO],
            now=dt_util.now(),
            departure_in_minutes=call.data[ATTR_DEPARTURE_IN_MINUTES],
            delay_minutes=call.data[ATTR_DELAY_MINUTES],
            duration_minutes=call.data[ATTR_DURATION_MINUTES],
            accelerated=call.data[ATTR_ACCELERATED],
        )
        await runtime.coordinator.async_request_refresh()
        return runtime.coordinator.data.as_dict()

    async def async_clear_simulation(call: ServiceCall) -> dict:
        runtime = _runtime(hass)
        runtime.simulation.clear()
        await runtime.coordinator.async_request_refresh()
        return runtime.coordinator.data.as_dict()

    if not hass.services.has_service(DOMAIN, SERVICE_REVIEW_NOW):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REVIEW_NOW,
            async_review_now,
            schema=vol.Schema({}),
            supports_response=SupportsResponse.OPTIONAL,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SIMULATE_JOURNEY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SIMULATE_JOURNEY,
            async_simulate_journey,
            schema=vol.Schema(
                {
                    vol.Required(ATTR_SCENARIO): vol.In(SIMULATION_SCENARIOS),
                    vol.Optional(
                        ATTR_DEPARTURE_IN_MINUTES,
                        default=DEFAULT_SIMULATION_DEPARTURE_MINUTES,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
                    vol.Optional(ATTR_DELAY_MINUTES, default=15): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=240)
                    ),
                    vol.Optional(ATTR_DURATION_MINUTES, default=60): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=720)
                    ),
                    vol.Optional(ATTR_ACCELERATED, default=False): cv.boolean,
                }
            ),
            supports_response=SupportsResponse.OPTIONAL,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_CLEAR_SIMULATION):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CLEAR_SIMULATION,
            async_clear_simulation,
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
