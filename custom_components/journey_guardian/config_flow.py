"""Config flow for Journey Guardian."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CALENDAR_REFRESH_INTERVAL_OPTIONS,
    CONF_ANNOUNCEMENT_SCRIPT_ENTITY,
    CONF_ANNOUNCEMENT_TEXT_ENTITY,
    CONF_AUTOMATIC_LIVE_RAIL_ENABLED,
    CONF_CALENDAR_ENTITY,
    CONF_CALENDAR_REFRESH_INTERVAL_MINUTES,
    CONF_DAILY_API_LIMIT,
    CONF_DELAY_REPAY_THRESHOLD_MINUTES,
    CONF_DESTINATION_ZONES,
    CONF_EARLY_WARNING_MINUTES,
    CONF_GOOGLE_ROUTES_API_KEY,
    CONF_HOME_WAKE_AWAKE_ENTITY,
    CONF_HOME_WAKE_AWAKE_STATE,
    CONF_HOME_WAKE_ENABLED,
    CONF_HOME_WAKE_MAX_MINUTES,
    CONF_HOME_WAKE_REPEAT_SECONDS,
    CONF_HOME_ZONE,
    CONF_LIVE_NOTIFICATIONS_ENABLED,
    CONF_LIVE_RAIL_PROVIDER,
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
    CONF_URGENT_API_RESERVE,
    DEFAULT_AUTOMATIC_LIVE_RAIL_ENABLED,
    DEFAULT_CALENDAR_REFRESH_INTERVAL_MINUTES,
    DEFAULT_DAILY_API_LIMIT,
    DEFAULT_DELAY_REPAY_THRESHOLD_MINUTES,
    DEFAULT_EARLY_WARNING_MINUTES,
    DEFAULT_HOME_WAKE_AWAKE_STATE,
    DEFAULT_HOME_WAKE_ENABLED,
    DEFAULT_HOME_WAKE_MAX_MINUTES,
    DEFAULT_HOME_WAKE_REPEAT_SECONDS,
    DEFAULT_HOME_ZONE,
    DEFAULT_LIVE_NOTIFICATIONS_ENABLED,
    DEFAULT_LIVE_RAIL_PROVIDER,
    DEFAULT_PREPARATION_BUFFER_MINUTES,
    DEFAULT_STATION_ACCESS_FALLBACK_MINUTES,
    DEFAULT_STATION_ACCESS_MINIMUM_MINUTES,
    DEFAULT_STATION_ACCESS_MODE,
    DEFAULT_STATION_BUFFER_MINUTES,
    DEFAULT_URGENT_API_RESERVE,
    DOMAIN,
)
from .progress import parse_progress_alternatives, parse_progress_zones
from .station_access_profiles import (
    StationAccessProfileError,
    parse_station_access_profiles,
)


class JourneyGuardianConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure Journey Guardian through the Home Assistant UI."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> JourneyGuardianOptionsFlow:
        """Create the timing options flow."""
        return JourneyGuardianOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                parse_station_access_profiles(
                    user_input.get(CONF_STATION_ACCESS_PROFILES)
                )
            except StationAccessProfileError as err:
                errors[CONF_STATION_ACCESS_PROFILES] = str(err)
            if user_input[CONF_URGENT_API_RESERVE] >= user_input[CONF_DAILY_API_LIMIT]:
                errors[CONF_URGENT_API_RESERVE] = "reserve_must_be_lower"
            if not errors:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="UK Journey Guardian", data=user_input
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_CALENDAR_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="calendar")
                ),
                vol.Required(
                    CONF_CALENDAR_REFRESH_INTERVAL_MINUTES,
                    default=DEFAULT_CALENDAR_REFRESH_INTERVAL_MINUTES,
                ): vol.In(CALENDAR_REFRESH_INTERVAL_OPTIONS),
                vol.Required(CONF_PERSON_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="person")
                ),
                vol.Required(
                    CONF_HOME_ZONE, default=DEFAULT_HOME_ZONE
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="zone")
                ),
                vol.Optional(
                    CONF_DESTINATION_ZONES, default=[]
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="zone", multiple=True)
                ),
                vol.Required(
                    CONF_PREPARATION_BUFFER_MINUTES,
                    default=DEFAULT_PREPARATION_BUFFER_MINUTES,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=180)),
                vol.Required(
                    CONF_EARLY_WARNING_MINUTES,
                    default=DEFAULT_EARLY_WARNING_MINUTES,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
                vol.Required(
                    CONF_STATION_BUFFER_MINUTES,
                    default=DEFAULT_STATION_BUFFER_MINUTES,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=120)),
                vol.Required(
                    CONF_STATION_ACCESS_FALLBACK_MINUTES,
                    default=DEFAULT_STATION_ACCESS_FALLBACK_MINUTES,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=240)),
                vol.Required(
                    CONF_STATION_ACCESS_MINIMUM_MINUTES,
                    default=DEFAULT_STATION_ACCESS_MINIMUM_MINUTES,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=240)),
                vol.Required(
                    CONF_STATION_ACCESS_MODE,
                    default=DEFAULT_STATION_ACCESS_MODE,
                ): vol.In(
                    {
                        "auto": "Automatic",
                        "walking": "Walking",
                        "driving": "Driving",
                        "bicycling": "Cycling",
                        "transit": "Public transport",
                    }
                ),
                vol.Optional(CONF_STATION_ACCESS_PROFILES): selector.TextSelector(
                    selector.TextSelectorConfig(multiline=True)
                ),
                vol.Optional(CONF_TRANSPORTAPI_APP_ID): selector.TextSelector(),
                vol.Optional(CONF_TRANSPORTAPI_APP_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    CONF_LIVE_RAIL_PROVIDER,
                    default=DEFAULT_LIVE_RAIL_PROVIDER,
                ): vol.In(
                    {
                        "transportapi": "TransportAPI (uses configured daily limit)",
                        "railinfo": "Railinfo (no key; separate fair-use limit)",
                    }
                ),
                vol.Optional(CONF_GOOGLE_ROUTES_API_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    CONF_DAILY_API_LIMIT, default=DEFAULT_DAILY_API_LIMIT
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                vol.Required(
                    CONF_DELAY_REPAY_THRESHOLD_MINUTES,
                    default=DEFAULT_DELAY_REPAY_THRESHOLD_MINUTES,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=120)),
                vol.Required(
                    CONF_URGENT_API_RESERVE,
                    default=DEFAULT_URGENT_API_RESERVE,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=20)),
                vol.Required(
                    CONF_AUTOMATIC_LIVE_RAIL_ENABLED,
                    default=DEFAULT_AUTOMATIC_LIVE_RAIL_ENABLED,
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_LIVE_NOTIFICATIONS_ENABLED,
                    default=DEFAULT_LIVE_NOTIFICATIONS_ENABLED,
                ): selector.BooleanSelector(),
                vol.Optional(CONF_ANNOUNCEMENT_TEXT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="input_text")
                ),
                vol.Optional(CONF_ANNOUNCEMENT_SCRIPT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="script")
                ),
                vol.Required(
                    CONF_HOME_WAKE_ENABLED,
                    default=DEFAULT_HOME_WAKE_ENABLED,
                ): selector.BooleanSelector(),
                vol.Optional(CONF_HOME_WAKE_AWAKE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["binary_sensor", "input_boolean"]
                    )
                ),
                vol.Required(
                    CONF_HOME_WAKE_AWAKE_STATE,
                    default=DEFAULT_HOME_WAKE_AWAKE_STATE,
                ): vol.In({"on": "On", "off": "Off"}),
                vol.Required(
                    CONF_HOME_WAKE_REPEAT_SECONDS,
                    default=DEFAULT_HOME_WAKE_REPEAT_SECONDS,
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=60)),
                vol.Required(
                    CONF_HOME_WAKE_MAX_MINUTES,
                    default=DEFAULT_HOME_WAKE_MAX_MINUTES,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=30)),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class JourneyGuardianOptionsFlow(OptionsFlowWithReload):
    """Edit Journey Guardian timing settings without reinstalling."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Manage timing options."""
        current = {**self.config_entry.data, **self.config_entry.options}
        errors = {}
        if user_input is not None:
            try:
                base = parse_progress_zones(user_input.get(CONF_PROGRESS_ZONES))
                try:
                    parse_progress_alternatives(
                        user_input.get(CONF_PROGRESS_ALTERNATIVES), base
                    )
                except ValueError:
                    errors[CONF_PROGRESS_ALTERNATIVES] = "invalid_progress_alternatives"
            except ValueError:
                errors[CONF_PROGRESS_ZONES] = "invalid_progress_zones"
            try:
                parse_station_access_profiles(
                    user_input.get(CONF_STATION_ACCESS_PROFILES)
                )
            except StationAccessProfileError as err:
                errors[CONF_STATION_ACCESS_PROFILES] = str(err)
            if not errors:
                updated = dict(user_input)
                for key in (
                    CONF_TRANSPORTAPI_APP_ID,
                    CONF_TRANSPORTAPI_APP_KEY,
                    CONF_GOOGLE_ROUTES_API_KEY,
                ):
                    if str(updated.get(key, "")).strip():
                        continue
                    if current.get(key):
                        updated[key] = current[key]
                    else:
                        updated.pop(key, None)
                return self.async_create_entry(title="", data=updated)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CALENDAR_REFRESH_INTERVAL_MINUTES,
                        default=current.get(
                            CONF_CALENDAR_REFRESH_INTERVAL_MINUTES,
                            DEFAULT_CALENDAR_REFRESH_INTERVAL_MINUTES,
                        ),
                    ): vol.In(CALENDAR_REFRESH_INTERVAL_OPTIONS),
                    vol.Optional(
                        CONF_PROGRESS_ZONES,
                        default=current.get(CONF_PROGRESS_ZONES, ""),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                    vol.Optional(
                        CONF_PROGRESS_ALTERNATIVES,
                        default=current.get(CONF_PROGRESS_ALTERNATIVES, ""),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                    vol.Required(
                        CONF_PREPARATION_BUFFER_MINUTES,
                        default=current.get(
                            CONF_PREPARATION_BUFFER_MINUTES,
                            DEFAULT_PREPARATION_BUFFER_MINUTES,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=180)),
                    vol.Required(
                        CONF_EARLY_WARNING_MINUTES,
                        default=current.get(
                            CONF_EARLY_WARNING_MINUTES,
                            DEFAULT_EARLY_WARNING_MINUTES,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=60)),
                    vol.Required(
                        CONF_STATION_BUFFER_MINUTES,
                        default=current.get(
                            CONF_STATION_BUFFER_MINUTES,
                            DEFAULT_STATION_BUFFER_MINUTES,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=120)),
                    vol.Required(
                        CONF_STATION_ACCESS_FALLBACK_MINUTES,
                        default=current.get(
                            CONF_STATION_ACCESS_FALLBACK_MINUTES,
                            DEFAULT_STATION_ACCESS_FALLBACK_MINUTES,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=240)),
                    vol.Required(
                        CONF_STATION_ACCESS_MINIMUM_MINUTES,
                        default=current.get(
                            CONF_STATION_ACCESS_MINIMUM_MINUTES,
                            DEFAULT_STATION_ACCESS_MINIMUM_MINUTES,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=240)),
                    vol.Required(
                        CONF_STATION_ACCESS_MODE,
                        default=current.get(
                            CONF_STATION_ACCESS_MODE,
                            DEFAULT_STATION_ACCESS_MODE,
                        ),
                    ): vol.In(
                        {
                            "auto": "Automatic",
                            "walking": "Walking",
                            "driving": "Driving",
                            "bicycling": "Cycling",
                            "transit": "Public transport",
                        }
                    ),
                    vol.Optional(
                        CONF_STATION_ACCESS_PROFILES,
                        default=current.get(CONF_STATION_ACCESS_PROFILES, ""),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                    vol.Required(
                        CONF_AUTOMATIC_LIVE_RAIL_ENABLED,
                        default=current.get(
                            CONF_AUTOMATIC_LIVE_RAIL_ENABLED,
                            DEFAULT_AUTOMATIC_LIVE_RAIL_ENABLED,
                        ),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_LIVE_NOTIFICATIONS_ENABLED,
                        default=current.get(
                            CONF_LIVE_NOTIFICATIONS_ENABLED,
                            DEFAULT_LIVE_NOTIFICATIONS_ENABLED,
                        ),
                    ): selector.BooleanSelector(),
                    vol.Required(
                        CONF_DELAY_REPAY_THRESHOLD_MINUTES,
                        default=current.get(
                            CONF_DELAY_REPAY_THRESHOLD_MINUTES,
                            DEFAULT_DELAY_REPAY_THRESHOLD_MINUTES,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=120)),
                    vol.Optional(
                        CONF_ANNOUNCEMENT_TEXT_ENTITY,
                        **(
                            {"default": current[CONF_ANNOUNCEMENT_TEXT_ENTITY]}
                            if current.get(CONF_ANNOUNCEMENT_TEXT_ENTITY)
                            else {}
                        ),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="input_text")
                    ),
                    vol.Optional(
                        CONF_ANNOUNCEMENT_SCRIPT_ENTITY,
                        **(
                            {"default": current[CONF_ANNOUNCEMENT_SCRIPT_ENTITY]}
                            if current.get(CONF_ANNOUNCEMENT_SCRIPT_ENTITY)
                            else {}
                        ),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="script")
                    ),
                    vol.Required(
                        CONF_HOME_WAKE_ENABLED,
                        default=current.get(
                            CONF_HOME_WAKE_ENABLED,
                            bool(current.get(CONF_ANNOUNCEMENT_SCRIPT_ENTITY)),
                        ),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        CONF_HOME_WAKE_AWAKE_ENTITY,
                        **(
                            {"default": current[CONF_HOME_WAKE_AWAKE_ENTITY]}
                            if current.get(CONF_HOME_WAKE_AWAKE_ENTITY)
                            else {}
                        ),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["binary_sensor", "input_boolean"]
                        )
                    ),
                    vol.Required(
                        CONF_HOME_WAKE_AWAKE_STATE,
                        default=current.get(
                            CONF_HOME_WAKE_AWAKE_STATE,
                            DEFAULT_HOME_WAKE_AWAKE_STATE,
                        ),
                    ): vol.In({"on": "On", "off": "Off"}),
                    vol.Required(
                        CONF_HOME_WAKE_REPEAT_SECONDS,
                        default=current.get(
                            CONF_HOME_WAKE_REPEAT_SECONDS,
                            DEFAULT_HOME_WAKE_REPEAT_SECONDS,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=60)),
                    vol.Required(
                        CONF_HOME_WAKE_MAX_MINUTES,
                        default=current.get(
                            CONF_HOME_WAKE_MAX_MINUTES,
                            DEFAULT_HOME_WAKE_MAX_MINUTES,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=30)),
                    vol.Optional(
                        CONF_TRANSPORTAPI_APP_ID,
                    ): selector.TextSelector(),
                    vol.Optional(
                        CONF_TRANSPORTAPI_APP_KEY,
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Required(
                        CONF_LIVE_RAIL_PROVIDER,
                        default=current.get(
                            CONF_LIVE_RAIL_PROVIDER,
                            DEFAULT_LIVE_RAIL_PROVIDER,
                        ),
                    ): vol.In(
                        {
                            "transportapi": (
                                "TransportAPI (uses configured daily limit)"
                            ),
                            "railinfo": "Railinfo (no key; separate fair-use limit)",
                        }
                    ),
                    vol.Optional(
                        CONF_GOOGLE_ROUTES_API_KEY,
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
            errors=errors,
        )
