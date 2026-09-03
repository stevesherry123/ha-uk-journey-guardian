"""Tests for integration-wide Journey Guardian setup."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.setup import async_setup_component

from custom_components.journey_guardian.const import (
    DOMAIN,
    SERVICE_CLEAR_SIMULATION,
    SERVICE_REVIEW_NOW,
    SERVICE_SIMULATE_JOURNEY,
)


async def test_review_action_registered_without_entry(hass) -> None:
    """The integration action exists independently of config-entry reloads."""
    assert await async_setup_component(hass, DOMAIN, {})

    assert hass.services.has_service(DOMAIN, SERVICE_REVIEW_NOW)
    assert hass.services.has_service(DOMAIN, SERVICE_SIMULATE_JOURNEY)
    assert hass.services.has_service(DOMAIN, SERVICE_CLEAR_SIMULATION)
    assert not hass.services.has_service(DOMAIN, "reset_api_budget")


async def test_simulation_action_uses_safe_defaults_and_returns_snapshot(hass) -> None:
    """The public action activates only the in-memory simulation controller."""
    assert await async_setup_component(hass, DOMAIN, {})
    runtime = Mock()
    runtime.coordinator.async_request_refresh = AsyncMock()
    runtime.coordinator.data.as_dict.return_value = {
        "simulation_active": True,
        "status": "planned",
    }
    now = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)

    with (
        patch(
            "custom_components.journey_guardian._runtime",
            return_value=runtime,
        ),
        patch(
            "custom_components.journey_guardian.dt_util.now",
            return_value=now,
        ),
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_SIMULATE_JOURNEY,
            {"scenario": "on_time"},
            blocking=True,
            return_response=True,
        )

    runtime.simulation.activate.assert_called_once_with(
        scenario="on_time",
        now=now,
        departure_in_minutes=180,
        delay_minutes=15,
        duration_minutes=60,
        accelerated=False,
    )
    runtime.coordinator.async_request_refresh.assert_awaited_once()
    assert response == {"simulation_active": True, "status": "planned"}


async def test_clear_simulation_action_restores_live_review(hass) -> None:
    """Clearing a scenario refreshes immediately from configured live inputs."""
    assert await async_setup_component(hass, DOMAIN, {})
    runtime = Mock()
    runtime.coordinator.async_request_refresh = AsyncMock()
    runtime.coordinator.data.as_dict.return_value = {
        "simulation_active": False,
        "status": "idle",
    }

    with patch(
        "custom_components.journey_guardian._runtime",
        return_value=runtime,
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_CLEAR_SIMULATION,
            {},
            blocking=True,
            return_response=True,
        )

    runtime.simulation.clear.assert_called_once_with()
    runtime.coordinator.async_request_refresh.assert_awaited_once()
    assert response == {"simulation_active": False, "status": "idle"}
