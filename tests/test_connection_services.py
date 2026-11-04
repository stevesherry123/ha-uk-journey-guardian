"""Explicit confirmation commands validate actual booking identities."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.journey_guardian import _async_register_services
from custom_components.journey_guardian.const import DOMAIN

NOW = datetime(2026, 11, 4, 8, tzinfo=UTC)
PAIR = {"inbound_id": "a" * 64, "outbound_id": "b" * 64}


async def test_confirm_validates_pair_and_revoke_persists(hass):
    coordinator = Mock()
    coordinator.data.simulation_active = False
    coordinator.data.error = None
    coordinator.travel_plan.connection_pair.return_value = (
        SimpleNamespace(booking_id=PAIR["inbound_id"]),
        SimpleNamespace(booking_id=PAIR["outbound_id"], expiry=NOW + timedelta(days=1)),
    )
    coordinator.connection_confirmations.async_confirm = AsyncMock()
    coordinator.connection_confirmations.async_revoke = AsyncMock()
    with (
        patch("custom_components.journey_guardian._runtime",
              return_value=SimpleNamespace(coordinator=coordinator)),
        patch("custom_components.journey_guardian.dt_util.now", return_value=NOW),
    ):
        _async_register_services(hass)
        await hass.services.async_call(
            DOMAIN, "confirm_connection", {**PAIR, "override_minutes": 12},
            blocking=True
        )
        coordinator.travel_plan.connection_pair.assert_called_once_with(
            PAIR["inbound_id"], PAIR["outbound_id"], now=NOW
        )
        record = coordinator.connection_confirmations.async_confirm.call_args.args[0]
        assert record.override_minutes == 12
        coordinator.travel_plan.connection_pair.side_effect = ValueError("edited")
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN, "confirm_connection", PAIR, blocking=True
            )
        assert coordinator.connection_confirmations.async_confirm.await_count == 1
        coordinator.data.simulation_active = True
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN, "revoke_connection", PAIR, blocking=True
            )
        coordinator.connection_confirmations.async_revoke.assert_not_awaited()
        coordinator.data.simulation_active = False
        await hass.services.async_call(DOMAIN, "revoke_connection", PAIR, blocking=True)
        coordinator.connection_confirmations.async_revoke.assert_awaited_once_with(
            PAIR["inbound_id"], PAIR["outbound_id"]
        )


@pytest.mark.parametrize("value", [True, -1, 1441, 10.5, "10"])
async def test_confirmation_rejects_invalid_allowance_before_runtime(hass, value):
    from voluptuous import Invalid

    with patch("custom_components.journey_guardian._runtime") as runtime:
        _async_register_services(hass)
        with pytest.raises(Invalid):
            await hass.services.async_call(
                DOMAIN, "confirm_connection", {**PAIR, "override_minutes": value},
                blocking=True,
            )
        runtime.assert_not_called()


async def test_confirmation_requires_real_healthy_calendar(hass):
    coordinator = Mock()
    coordinator.connection_confirmations.async_confirm = AsyncMock()
    with patch("custom_components.journey_guardian._runtime",
               return_value=SimpleNamespace(coordinator=coordinator)):
        _async_register_services(hass)
        for simulation, error in ((True, None), (False, "calendar_unavailable")):
            coordinator.data.simulation_active = simulation
            coordinator.data.error = error
            with pytest.raises(HomeAssistantError):
                await hass.services.async_call(
                    DOMAIN, "confirm_connection", PAIR, blocking=True
                )
        coordinator.connection_confirmations.async_confirm.assert_not_awaited()
