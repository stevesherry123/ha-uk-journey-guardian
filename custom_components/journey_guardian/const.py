"""Constants for Journey Guardian."""

from datetime import timedelta

DOMAIN = "journey_guardian"
NAME = "UK Journey Guardian"

CONF_CALENDAR_ENTITY = "calendar_entity"
CONF_PERSON_ENTITY = "person_entity"
CONF_HOME_ZONE = "home_zone"
CONF_DESTINATION_ZONES = "destination_zones"
CONF_PREPARATION_BUFFER_MINUTES = "preparation_buffer_minutes"
CONF_EARLY_WARNING_MINUTES = "early_warning_minutes"
CONF_STATION_BUFFER_MINUTES = "station_buffer_minutes"
CONF_STATION_ACCESS_MODE = "station_access_mode"
CONF_STATION_ACCESS_FALLBACK_MINUTES = "station_access_fallback_minutes"
CONF_TRANSPORTAPI_APP_ID = "transportapi_app_id"
CONF_TRANSPORTAPI_APP_KEY = "transportapi_app_key"
CONF_GOOGLE_ROUTES_API_KEY = "google_routes_api_key"
CONF_DAILY_API_LIMIT = "daily_api_limit"
CONF_URGENT_API_RESERVE = "urgent_api_reserve"
CONF_LIVE_NOTIFICATIONS_ENABLED = "live_notifications_enabled"

DEFAULT_HOME_ZONE = "zone.home"
DEFAULT_PREPARATION_BUFFER_MINUTES = 30
DEFAULT_EARLY_WARNING_MINUTES = 10
DEFAULT_STATION_BUFFER_MINUTES = 15
DEFAULT_STATION_ACCESS_MODE = "auto"
DEFAULT_STATION_ACCESS_FALLBACK_MINUTES = 60
DEFAULT_DAILY_API_LIMIT = 30
DEFAULT_URGENT_API_RESERVE = 3
DEFAULT_LIVE_NOTIFICATIONS_ENABLED = False
DEFAULT_LOOKAHEAD_HOURS = 30
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=10)
DEFAULT_SIMULATION_DEPARTURE_MINUTES = 180

SERVICE_REVIEW_NOW = "review_now"
SERVICE_SIMULATE_JOURNEY = "simulate_journey"
SERVICE_CLEAR_SIMULATION = "clear_simulation"

ATTR_SCENARIO = "scenario"
ATTR_DEPARTURE_IN_MINUTES = "departure_in_minutes"
ATTR_DELAY_MINUTES = "delay_minutes"
ATTR_DURATION_MINUTES = "duration_minutes"
ATTR_ACCELERATED = "accelerated"

SIMULATION_SCENARIOS = (
    "on_time",
    "delayed",
    "cancelled",
    "split_on_time",
    "stale_data",
    "provider_unavailable",
)

STORAGE_KEY = f"{DOMAIN}.transportapi_budget"
STORAGE_VERSION = 1
NOTIFICATION_STORAGE_KEY = f"{DOMAIN}.notification_ledger"
NOTIFICATION_STORAGE_VERSION = 1
