"""Config flow for Journey Guardian."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CALENDAR_ENTITY,
    CONF_DAILY_API_LIMIT,
    CONF_DESTINATION_ZONES,
    CONF_EARLY_WARNING_MINUTES,
    CONF_GOOGLE_ROUTES_API_KEY,
    CONF_HOME_ZONE,
    CONF_LIVE_NOTIFICATIONS_ENABLED,
    CONF_PERSON_ENTITY,
    CONF_PREPARATION_BUFFER_MINUTES,
    CONF_STATION_ACCESS_FALLBACK_MINUTES,
    CONF_STATION_ACCESS_MODE,
    CONF_STATION_BUFFER_MINUTES,
    CONF_TRANSPORTAPI_APP_ID,
    CONF_TRANSPORTAPI_APP_KEY,
    CONF_URGENT_API_RESERVE,
    DEFAULT_DAILY_API_LIMIT,
    DEFAULT_EARLY_WARNING_MINUTES,
    DEFAULT_HOME_ZONE,
    DEFAULT_LIVE_NOTIFICATIONS_ENABLED,
    DEFAULT_PREPARATION_BUFFER_MINUTES,
    DEFAULT_STATION_ACCESS_FALLBACK_MINUTES,
    DEFAULT_STATION_ACCESS_MODE,
    DEFAULT_STATION_BUFFER_MINUTES,
    DEFAULT_URGENT_API_RESERVE,
    DOMAIN,
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
            if user_input[CONF_URGENT_API_RESERVE] >= user_input[CONF_DAILY_API_LIMIT]:
                errors[CONF_URGENT_API_RESERVE] = "reserve_must_be_lower"
            else:
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
                    CONF_STATION_ACCESS_MODE,
                    default=DEFAULT_STATION_ACCESS_MODE,
                ): vol.In(
                    {
                        "auto": "Automatic",
                        "walking": "Walking",
                        "driving": "Driving",
                        "bicycling": "Cycling",
                    }
                ),
                vol.Optional(CONF_TRANSPORTAPI_APP_ID): selector.TextSelector(),
                vol.Optional(CONF_TRANSPORTAPI_APP_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
                vol.Optional(CONF_GOOGLE_ROUTES_API_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD
                    )
                ),
                vol.Required(
                    CONF_DAILY_API_LIMIT, default=DEFAULT_DAILY_API_LIMIT
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                vol.Required(
                    CONF_URGENT_API_RESERVE,
                    default=DEFAULT_URGENT_API_RESERVE,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=20)),
                vol.Required(
                    CONF_LIVE_NOTIFICATIONS_ENABLED,
                    default=DEFAULT_LIVE_NOTIFICATIONS_ENABLED,
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )


class JourneyGuardianOptionsFlow(OptionsFlowWithReload):
    """Edit Journey Guardian timing settings without reinstalling."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Manage timing options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
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
                        CONF_LIVE_NOTIFICATIONS_ENABLED,
                        default=current.get(
                            CONF_LIVE_NOTIFICATIONS_ENABLED,
                            DEFAULT_LIVE_NOTIFICATIONS_ENABLED,
                        ),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        CONF_TRANSPORTAPI_APP_ID,
                        default=current.get(CONF_TRANSPORTAPI_APP_ID, ""),
                    ): selector.TextSelector(),
                    vol.Optional(
                        CONF_TRANSPORTAPI_APP_KEY,
                        default=current.get(CONF_TRANSPORTAPI_APP_KEY, ""),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
        )
