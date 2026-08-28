"""Constants for Journey Guardian."""

from datetime import timedelta

DOMAIN = "journey_guardian"
NAME = "UK Journey Guardian"

CONF_CALENDAR_ENTITY = "calendar_entity"
CONF_PERSON_ENTITY = "person_entity"
CONF_HOME_ZONE = "home_zone"
CONF_DESTINATION_ZONES = "destination_zones"
CONF_PREPARATION_BUFFER_MINUTES = "preparation_buffer_minutes"
CONF_STATION_BUFFER_MINUTES = "station_buffer_minutes"
CONF_STATION_ACCESS_MODE = "station_access_mode"
CONF_TRANSPORTAPI_APP_ID = "transportapi_app_id"
CONF_TRANSPORTAPI_APP_KEY = "transportapi_app_key"
CONF_GOOGLE_ROUTES_API_KEY = "google_routes_api_key"
CONF_DAILY_API_LIMIT = "daily_api_limit"
CONF_URGENT_API_RESERVE = "urgent_api_reserve"

DEFAULT_HOME_ZONE = "zone.home"
DEFAULT_PREPARATION_BUFFER_MINUTES = 30
DEFAULT_STATION_BUFFER_MINUTES = 15
DEFAULT_STATION_ACCESS_MODE = "auto"
DEFAULT_DAILY_API_LIMIT = 30
DEFAULT_URGENT_API_RESERVE = 3
DEFAULT_LOOKAHEAD_HOURS = 30
DEFAULT_UPDATE_INTERVAL = timedelta(minutes=10)

SERVICE_REVIEW_NOW = "review_now"

STORAGE_KEY = f"{DOMAIN}.transportapi_budget"
STORAGE_VERSION = 1
