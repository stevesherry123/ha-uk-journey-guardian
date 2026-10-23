"""The beta frontend serves code only, not configuration or itinerary data."""

from unittest.mock import AsyncMock, patch

from homeassistant.setup import async_setup_component

from custom_components.journey_guardian.frontend import (
    CARD_FILE,
    CARD_URL,
    async_register_card,
)


async def test_no_http_does_not_create_or_start_a_server(hass):
    await async_register_card(hass)
    assert not hass.data.get("journey_guardian_card_registered")


async def test_card_registration_is_single_file_and_idempotent(hass):
    hass.config.components.add("http")
    with patch.object(hass, "http", create=True) as http:
        http.async_register_static_paths = AsyncMock()
        await async_register_card(hass)
        await async_register_card(hass)
        http.async_register_static_paths.assert_awaited_once()
        paths = http.async_register_static_paths.await_args.args[0]
        assert len(paths) == 1
        assert paths[0].url_path == CARD_URL
        assert paths[0].path == str(CARD_FILE)
        assert paths[0].cache_headers is False
        assert CARD_FILE.is_file()


async def test_card_asset_is_served_without_exposing_adjacent_files(hass, hass_client):
    assert await async_setup_component(hass, "http", {})
    await async_register_card(hass)
    client = await hass_client()
    response = await client.get(CARD_URL)
    assert response.status == 200
    assert "journey-guardian-card" in await response.text()
    assert (await client.get("/journey_guardian/manifest.json")).status == 404
