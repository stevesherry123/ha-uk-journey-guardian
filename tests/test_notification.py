"""Tests for cancellable, restart-safe operational notifications."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

from custom_components.journey_guardian.models import (
    BudgetSnapshot,
    JourneyEvent,
    JourneySnapshot,
    JourneyTiming,
)
from custom_components.journey_guardian.notification import (
    JourneyNotificationScheduler,
    NotificationLedger,
)

NOW = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)
DEPARTURE = NOW + timedelta(minutes=75)
TIMING = JourneyTiming(
    prepare_at=NOW - timedelta(minutes=40),
    leave_home_at=NOW,
    station_arrival_at=NOW + timedelta(minutes=60),
    preparation_minutes=30,
    early_warning_minutes=10,
    station_buffer_minutes=15,
    station_access_minutes=60,
    source="simulation",
    classification="simulated_scheduled",
)


def _snapshot(*, simulation: bool, phase: str = "leave_now") -> JourneySnapshot:
    journey = JourneyEvent(
        start=DEPARTURE,
        end=DEPARTURE + timedelta(minutes=60),
        summary="Rail simulation - Simulation Origin to Simulation Destination",
        location="Simulation Origin",
        origin_code="SIM",
        origin_name="Simulation Origin",
        destination_confirmation="Simulation Destination",
        decision_path="simulation_on_time",
    )
    return JourneySnapshot(
        status="planned",
        checked_at=NOW,
        next_journey=journey,
        budget=BudgetSnapshot("2026-09-03", 0, 29, 3),
        timing=TIMING,
        simulation_active=simulation,
        operational_phase=phase,
    )


async def test_simulation_notification_is_created_once() -> None:
    """Repeated refreshes cannot duplicate an actionable simulation alert."""
    hass = Mock()
    coordinator = Mock()
    ledger = Mock()
    ledger.async_claim = AsyncMock(side_effect=(True, False))
    scheduler = JourneyNotificationScheduler(
        hass, coordinator, ledger, live_notifications_enabled=False
    )
    snapshot = _snapshot(simulation=True)

    with patch(
        "custom_components.journey_guardian.notification."
        "persistent_notification.async_create"
    ) as create_notification:
        await scheduler._async_maybe_notify(snapshot)
        await scheduler._async_maybe_notify(snapshot)

    assert ledger.async_claim.await_count == 2
    create_notification.assert_called_once()
    assert create_notification.call_args.kwargs["title"] == (
        "UK Journey Guardian simulation"
    )
    assert "Leave now" in create_notification.call_args.args[1]


async def test_live_notification_is_disabled_during_shadow_mode() -> None:
    """Real calendar journeys remain silent until explicitly enabled."""
    ledger = Mock()
    ledger.async_claim = AsyncMock()
    scheduler = JourneyNotificationScheduler(
        Mock(), Mock(), ledger, live_notifications_enabled=False
    )

    with patch(
        "custom_components.journey_guardian.notification."
        "persistent_notification.async_create"
    ) as create_notification:
        await scheduler._async_maybe_notify(_snapshot(simulation=False))

    ledger.async_claim.assert_not_awaited()
    create_notification.assert_not_called()


async def test_live_notification_can_be_enabled_explicitly() -> None:
    """Calendar notifications require and respect the opt-in setting."""
    ledger = Mock()
    ledger.async_claim = AsyncMock(return_value=True)
    scheduler = JourneyNotificationScheduler(
        Mock(), Mock(), ledger, live_notifications_enabled=True
    )

    with patch(
        "custom_components.journey_guardian.notification."
        "persistent_notification.async_create"
    ) as create_notification:
        await scheduler._async_maybe_notify(_snapshot(simulation=False))

    ledger.async_claim.assert_awaited_once()
    create_notification.assert_called_once()
    assert create_notification.call_args.kwargs["title"] == "UK Journey Guardian"


async def test_ledger_rejects_fingerprint_restored_after_restart(hass) -> None:
    """A persisted fingerprint prevents a duplicate after Home Assistant restarts."""
    ledger = NotificationLedger(hass)
    ledger._store = AsyncMock()
    ledger._store.async_load.return_value = {"keys": ["existing"]}

    await ledger.async_load()

    assert not await ledger.async_claim("existing")
    ledger._store.async_save.assert_not_awaited()


def test_scheduler_cancels_boundaries_on_stop() -> None:
    """Reload and unload remove every outstanding exact-time callback."""
    hass = Mock()
    hass.async_create_task.side_effect = lambda coroutine, _name: coroutine.close()
    coordinator = Mock()
    coordinator.data = _snapshot(simulation=True, phase="prepare_now")
    remove_listener = Mock()
    coordinator.async_add_listener.return_value = remove_listener
    cancel_callbacks = [Mock(), Mock()]

    with (
        patch(
            "custom_components.journey_guardian.notification.dt_util.now",
            return_value=NOW,
        ),
        patch(
            "custom_components.journey_guardian.notification."
            "async_track_point_in_utc_time",
            side_effect=cancel_callbacks,
        ) as track,
    ):
        scheduler = JourneyNotificationScheduler(
            hass, coordinator, Mock(), live_notifications_enabled=False
        )
        scheduler.start()
        scheduler.stop()

    assert track.call_count == 2
    for cancel in cancel_callbacks:
        cancel.assert_called_once_with()
    remove_listener.assert_called_once_with()
