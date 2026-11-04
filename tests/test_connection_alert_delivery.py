"""Connection notices share the guarded household announcement route."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.journey_guardian.notification import JourneyNotificationScheduler


def scheduler(*, enabled=True, configured=True):
    hass = Mock()
    hass.services.async_call = AsyncMock()
    coordinator = Mock()
    coordinator.data = SimpleNamespace(simulation_active=False, error=None)
    result = JourneyNotificationScheduler(
        hass,
        coordinator,
        Mock(),
        live_notifications_enabled=enabled,
        announcement_text_entity="input_text.example_message" if configured else "",
        announcement_script_entity="script.example_announcement" if configured else "",
    )
    return result, hass, coordinator


async def send(subject, guard=lambda: True):
    return await subject.async_connection_notice(
        "Connection at Example Junction is at risk: 8 minutes available; 10 required.",
        notification_id="fictional_connection_alert",
        kind="risk",
        is_current=guard,
    )


async def test_live_notice_uses_helper_then_existing_script_without_receipt_claim():
    subject, hass, coordinator = scheduler()
    with patch(
        "custom_components.journey_guardian.notification.persistent_notification.async_create"
    ) as fallback:
        assert await send(subject) == "announcement_engine"
    assert hass.services.async_call.await_args_list[0].args[:2] == (
        "input_text",
        "set_value",
    )
    assert hass.services.async_call.await_args_list[1].args[:2] == (
        "script",
        "example_announcement",
    )
    fallback.assert_not_called()
    assert coordinator.record_notification.call_args.args[0] == "connection_risk"


@pytest.mark.parametrize("case", ["disabled", "simulation", "calendar", "revoked"])
async def test_invalid_context_suppresses_notice_before_handoff(case):
    subject, hass, coordinator = scheduler(enabled=case != "disabled")
    coordinator.data.simulation_active = case == "simulation"
    coordinator.data.error = "calendar_unavailable" if case == "calendar" else None
    with patch(
        "custom_components.journey_guardian.notification.persistent_notification.async_create"
    ) as fallback:
        assert await send(subject, lambda: case != "revoked") == "suppressed"
    hass.services.async_call.assert_not_awaited()
    fallback.assert_not_called()
    coordinator.record_notification.assert_not_called()


async def test_script_failure_uses_local_fallback():
    subject, hass, _ = scheduler()
    hass.services.async_call.side_effect = [None, RuntimeError("fictional failure")]
    with patch(
        "custom_components.journey_guardian.notification.persistent_notification.async_create"
    ) as fallback:
        assert await send(subject) == "persistent_notification"
    fallback.assert_called_once()


async def test_revocation_between_helper_and_script_stops_announcement():
    subject, hass, coordinator = scheduler()
    current = True

    async def helper(*args, **kwargs):
        nonlocal current
        current = False

    hass.services.async_call.side_effect = helper
    assert await send(subject, lambda: current) == "suppressed"
    assert hass.services.async_call.await_count == 1
    coordinator.record_notification.assert_not_called()


async def test_waiting_delivery_rechecks_context_after_lock():
    subject, hass, _ = scheduler()
    current = True
    await subject._delivery_lock.acquire()
    task = asyncio.create_task(send(subject, lambda: current))
    await asyncio.sleep(0)
    current = False
    subject._delivery_lock.release()
    assert await task == "suppressed"
    hass.services.async_call.assert_not_awaited()


async def test_delivery_timeout_has_bounded_local_fallback():
    subject, _, _ = scheduler()
    subject._async_deliver = AsyncMock(side_effect=TimeoutError())
    with patch(
        "custom_components.journey_guardian.notification.persistent_notification.async_create"
    ) as fallback:
        assert await send(subject) == "persistent_notification"
    fallback.assert_called_once()


async def test_successful_recovery_dismisses_earlier_local_fallback():
    subject, _, _ = scheduler()
    with patch(
        "custom_components.journey_guardian.notification.persistent_notification.async_dismiss"
    ) as dismiss:
        outcome = await subject.async_connection_notice(
            "Connection margin has recovered.",
            notification_id="fictional_connection_alert",
            kind="recovered",
            is_current=lambda: True,
        )
    assert outcome == "announcement_engine"
    dismiss.assert_called_once()
