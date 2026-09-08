"""Tests for the Journey Guardian config flow."""

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.journey_guardian.const import (
    CONF_AUTOMATIC_LIVE_RAIL_ENABLED,
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
    DOMAIN,
)

USER_INPUT = {
    CONF_CALENDAR_ENTITY: ".".join(("calendar", "example_travel")),
    CONF_PERSON_ENTITY: ".".join(("person", "example_traveller")),
    CONF_HOME_ZONE: "zone.home",
    CONF_DESTINATION_ZONES: ["zone.example_destination"],
    CONF_PREPARATION_BUFFER_MINUTES: 30,
    CONF_EARLY_WARNING_MINUTES: 10,
    CONF_STATION_BUFFER_MINUTES: 15,
    CONF_STATION_ACCESS_FALLBACK_MINUTES: 60,
    CONF_STATION_ACCESS_MODE: "walking",
    CONF_TRANSPORTAPI_APP_ID: "example-app-id",
    CONF_TRANSPORTAPI_APP_KEY: "example-app-key",
    CONF_GOOGLE_ROUTES_API_KEY: "",
    CONF_DAILY_API_LIMIT: 30,
    CONF_URGENT_API_RESERVE: 3,
    CONF_AUTOMATIC_LIVE_RAIL_ENABLED: False,
    CONF_LIVE_NOTIFICATIONS_ENABLED: False,
}


async def test_user_flow_creates_entry(hass) -> None:
    """A complete valid form creates the single config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    with (
        patch(
            "custom_components.journey_guardian.async_setup",
            return_value=True,
        ),
        patch(
            "custom_components.journey_guardian.async_setup_entry",
            return_value=True,
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "UK Journey Guardian"
    assert result["data"] == USER_INPUT


async def test_user_flow_allows_deferred_provider_credentials(hass) -> None:
    """Calendar-only setup does not require unused provider credentials."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    deferred_input = {
        key: value
        for key, value in USER_INPUT.items()
        if key
        not in {
            CONF_TRANSPORTAPI_APP_ID,
            CONF_TRANSPORTAPI_APP_KEY,
            CONF_GOOGLE_ROUTES_API_KEY,
        }
    }

    with (
        patch(
            "custom_components.journey_guardian.async_setup",
            return_value=True,
        ),
        patch(
            "custom_components.journey_guardian.async_setup_entry",
            return_value=True,
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], deferred_input
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == deferred_input


async def test_user_flow_rejects_reserve_at_limit(hass) -> None:
    """The urgent reserve must remain below the daily allowance."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    invalid_input = {
        **USER_INPUT,
        CONF_DAILY_API_LIMIT: 3,
        CONF_URGENT_API_RESERVE: 3,
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], invalid_input
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {
        CONF_URGENT_API_RESERVE: "reserve_must_be_lower"
    }


async def test_options_flow_updates_timing_and_reloads(hass) -> None:
    """Existing installs can edit conservative timing without reinstalling."""
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    updated = {
        CONF_PREPARATION_BUFFER_MINUTES: 35,
        CONF_EARLY_WARNING_MINUTES: 12,
        CONF_STATION_BUFFER_MINUTES: 20,
        CONF_STATION_ACCESS_FALLBACK_MINUTES: 75,
        CONF_STATION_ACCESS_MODE: "driving",
        CONF_AUTOMATIC_LIVE_RAIL_ENABLED: True,
        CONF_LIVE_NOTIFICATIONS_ENABLED: False,
        CONF_TRANSPORTAPI_APP_ID: "updated-app-id",
        CONF_TRANSPORTAPI_APP_KEY: "updated-app-key",
        CONF_GOOGLE_ROUTES_API_KEY: "updated-routes-key",
    }
    with patch.object(hass.config_entries, "async_reload") as async_reload:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], updated
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == updated
    async_reload.assert_awaited_once_with(entry.entry_id)
