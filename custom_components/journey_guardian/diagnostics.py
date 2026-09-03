"""Privacy-preserving diagnostics for Journey Guardian."""

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CALENDAR_ENTITY,
    CONF_DESTINATION_ZONES,
    CONF_EARLY_WARNING_MINUTES,
    CONF_GOOGLE_ROUTES_API_KEY,
    CONF_HOME_ZONE,
    CONF_PERSON_ENTITY,
    CONF_PREPARATION_BUFFER_MINUTES,
    CONF_STATION_ACCESS_FALLBACK_MINUTES,
    CONF_STATION_ACCESS_MODE,
    CONF_STATION_BUFFER_MINUTES,
    CONF_TRANSPORTAPI_APP_ID,
    CONF_TRANSPORTAPI_APP_KEY,
)

TO_REDACT = {
    CONF_CALENDAR_ENTITY,
    CONF_PERSON_ENTITY,
    CONF_HOME_ZONE,
    CONF_DESTINATION_ZONES,
    CONF_EARLY_WARNING_MINUTES,
    CONF_PREPARATION_BUFFER_MINUTES,
    CONF_STATION_BUFFER_MINUTES,
    CONF_STATION_ACCESS_MODE,
    CONF_STATION_ACCESS_FALLBACK_MINUTES,
    CONF_TRANSPORTAPI_APP_ID,
    CONF_TRANSPORTAPI_APP_KEY,
    CONF_GOOGLE_ROUTES_API_KEY,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics with credentials and personal entities removed."""
    runtime = entry.runtime_data
    snapshot = runtime.coordinator.data
    return {
        "config_entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "engine": {
            "status": snapshot.status,
            "data_healthy": snapshot.data_healthy,
            "error": snapshot.error,
            "simulation_active": snapshot.simulation_active,
            "rail_observation": (
                {
                    "scenario": snapshot.rail_observation.scenario,
                    "source": snapshot.rail_observation.source,
                    "classification": snapshot.rail_observation.classification,
                    "delay_minutes": snapshot.rail_observation.delay_minutes,
                    "cancelled": snapshot.rail_observation.cancelled,
                    "leg_count": snapshot.rail_observation.leg_count,
                    "provider_available": (
                        snapshot.rail_observation.provider_available
                    ),
                }
                if snapshot.rail_observation
                else None
            ),
            "next_journey": "REDACTED" if snapshot.next_journey else None,
            "timing": (
                {
                    "source": snapshot.timing.source,
                    "classification": snapshot.timing.classification,
                }
                if snapshot.timing
                else None
            ),
        },
        "budget": snapshot.budget.as_dict(),
    }
