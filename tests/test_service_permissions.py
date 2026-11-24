"""Check authorization at the Home Assistant service boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ
from homeassistant.core import Context
from homeassistant.exceptions import Unauthorized

from custom_components.journey_guardian import _async_register_services
from custom_components.journey_guardian.const import (
    CONF_CALENDAR_ENTITY,
    CONF_PERSON_ENTITY,
    DOMAIN,
)


@pytest.mark.parametrize(
    ("service", "denied", "allowed"),
    [
        ("review_now", ("calendar", POLICY_READ), False),
        ("review_now", ("person", POLICY_READ), False),
        ("review_now", ("calendar", POLICY_CONTROL), True),
        ("clear_simulation", ("calendar", POLICY_CONTROL), False),
        ("clear_simulation", None, True),
    ],
)
async def test_service_permissions(hass, service, denied, allowed):
    user = Mock(is_active=True)
    user.permissions.check_entity.side_effect = lambda *permission: permission != denied
    entry = SimpleNamespace(
        data={CONF_CALENDAR_ENTITY: "calendar", CONF_PERSON_ENTITY: "person"}
    )
    runtime = Mock()
    runtime.coordinator.async_refresh_calendar_and_review = AsyncMock(
        return_value=Mock()
    )
    runtime.coordinator.async_request_refresh = AsyncMock()
    with (
        patch.object(hass.auth, "async_get_user", AsyncMock(return_value=user)),
        patch("custom_components.journey_guardian._loaded_entry", return_value=entry),
        patch(
            "custom_components.journey_guardian._runtime", return_value=runtime
        ) as get,
    ):
        _async_register_services(hass)
        call = hass.services.async_call(
            DOMAIN, service, {}, blocking=True, context=Context(user_id="caller")
        )
        if allowed:
            await call
            get.assert_called_once()
        else:
            with pytest.raises(Unauthorized):
                await call
            get.assert_not_called()
