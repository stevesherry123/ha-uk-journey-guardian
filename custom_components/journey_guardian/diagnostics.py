"""Privacy-preserving diagnostics for Journey Guardian."""

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ANNOUNCEMENT_SCRIPT_ENTITY,
    CONF_ANNOUNCEMENT_TEXT_ENTITY,
    CONF_CALENDAR_ENTITY,
    CONF_DESTINATION_ZONES,
    CONF_EARLY_WARNING_MINUTES,
    CONF_GOOGLE_ROUTES_API_KEY,
    CONF_HOME_WAKE_AWAKE_ENTITY,
    CONF_HOME_ZONE,
    CONF_LIVE_NOTIFICATIONS_ENABLED,
    CONF_PERSON_ENTITY,
    CONF_PREPARATION_BUFFER_MINUTES,
    CONF_PROGRESS_ALTERNATIVES,
    CONF_PROGRESS_ZONES,
    CONF_STATION_ACCESS_FALLBACK_MINUTES,
    CONF_STATION_ACCESS_MINIMUM_MINUTES,
    CONF_STATION_ACCESS_MODE,
    CONF_STATION_ACCESS_PROFILES,
    CONF_STATION_BUFFER_MINUTES,
    CONF_TRANSPORTAPI_APP_ID,
    CONF_TRANSPORTAPI_APP_KEY,
)

TO_REDACT = {
    "entry_id",
    "unique_id",
    CONF_ANNOUNCEMENT_SCRIPT_ENTITY,
    CONF_ANNOUNCEMENT_TEXT_ENTITY,
    CONF_CALENDAR_ENTITY,
    CONF_PERSON_ENTITY,
    CONF_PROGRESS_ZONES,
    CONF_PROGRESS_ALTERNATIVES,
    CONF_HOME_ZONE,
    CONF_HOME_WAKE_AWAKE_ENTITY,
    CONF_DESTINATION_ZONES,
    CONF_EARLY_WARNING_MINUTES,
    CONF_PREPARATION_BUFFER_MINUTES,
    CONF_STATION_BUFFER_MINUTES,
    CONF_STATION_ACCESS_MODE,
    CONF_STATION_ACCESS_PROFILES,
    CONF_STATION_ACCESS_FALLBACK_MINUTES,
    CONF_STATION_ACCESS_MINIMUM_MINUTES,
    CONF_LIVE_NOTIFICATIONS_ENABLED,
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
            "last_live_rail_error": snapshot.last_live_rail_error,
            "simulation_active": snapshot.simulation_active,
            "operational_phase": snapshot.operational_phase,
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
                    "freshness": snapshot.rail_observation.freshness,
                    "age_seconds": snapshot.rail_observation.age_seconds,
                    "match_quality": snapshot.rail_observation.match_quality,
                    "schedule_offset_minutes": (
                        snapshot.rail_observation.schedule_offset_minutes
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
        "recent_live_checks": [
            _redact_live_check(record)
            for record in runtime.check_history.records()
        ],
        "last_travel_day_review": runtime.end_of_day_review.diagnostics(),
        "arrival_collector": runtime.arrival_collector.diagnostics(),
        "home_wake_alarm": runtime.notification_scheduler.diagnostics(),
    }


def _redact_live_check(record: dict) -> dict:
    """Keep diagnostic outcomes while removing journey-identifying evidence."""
    safe_keys = {
        "trigger",
        "operation",
        "stage",
        "outcome",
        "error_category",
        "schedule_offset_minutes",
        "match_quality",
        "calls_used",
        "status",
        "arrival_delay_minutes",
        "completion_status",
        "cancelled",
        "evidence_source",
        "evidence_freshness",
    }
    return {key: record.get(key) for key in safe_keys}
