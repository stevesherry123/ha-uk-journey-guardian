"""Tests for restart-safe automatic rail checkpoints."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

from custom_components.journey_guardian.models import (
    BudgetSnapshot,
    JourneyEvent,
    JourneySnapshot,
)
from custom_components.journey_guardian.rail_monitor import AutomaticRailMonitor

NOW = datetime(2026, 9, 4, 10, 0, tzinfo=UTC)
BUDGET = BudgetSnapshot("2026-09-04", 0, 30, 3)


def _coordinator(departure: datetime) -> Mock:
    journey = JourneyEvent(
        start=departure,
        end=departure + timedelta(hours=2),
        summary="Example rail journey",
        location="Example Central",
        origin_code="EXC",
        origin_name="Example Central",
        destination_confirmation="Sample Harbour",
        decision_path="calendar_route",
    )
    coordinator = Mock()
    coordinator.data = JourneySnapshot(
        status="planned",
        checked_at=NOW,
        next_journey=journey,
        budget=BUDGET,
    )
    coordinator.engine.live_rail_configured = True
    coordinator.async_add_listener.return_value = Mock()
    coordinator.async_review_live_rail = AsyncMock()
    return coordinator


async def test_monitor_catches_up_once_at_routine_checkpoint(hass) -> None:
    """A late coordinator update catches a just-due routine checkpoint."""
    coordinator = _coordinator(NOW + timedelta(minutes=150))
    ledger = Mock()
    ledger.async_claim = AsyncMock(return_value=True)
    monitor = AutomaticRailMonitor(hass, coordinator, ledger, enabled=True)

    with patch(
        "custom_components.journey_guardian.rail_monitor.dt_util.now",
        return_value=NOW,
    ):
        monitor.start()
        await hass.async_block_till_done()

    coordinator.async_review_live_rail.assert_awaited_once_with(
        decision_path="transportapi_automatic",
        urgent=False,
    )
    monitor.stop()


async def test_final_checkpoint_can_use_urgent_reserve(hass) -> None:
    """Only the final ten-minute checkpoint is classified as urgent."""
    coordinator = _coordinator(NOW + timedelta(minutes=10))
    ledger = Mock()
    ledger.async_claim = AsyncMock(return_value=True)
    monitor = AutomaticRailMonitor(hass, coordinator, ledger, enabled=True)

    with patch(
        "custom_components.journey_guardian.rail_monitor.dt_util.now",
        return_value=NOW,
    ):
        monitor.start()
        await hass.async_block_till_done()

    coordinator.async_review_live_rail.assert_awaited_once_with(
        decision_path="transportapi_automatic",
        urgent=True,
    )
    monitor.stop()


async def test_claimed_checkpoint_is_not_repeated(hass) -> None:
    """A persisted claim prevents duplicate reservations after rescheduling."""
    coordinator = _coordinator(NOW + timedelta(minutes=90))
    ledger = Mock()
    ledger.async_claim = AsyncMock(return_value=False)
    monitor = AutomaticRailMonitor(hass, coordinator, ledger, enabled=True)

    with patch(
        "custom_components.journey_guardian.rail_monitor.dt_util.now",
        return_value=NOW,
    ):
        monitor.start()
        await hass.async_block_till_done()

    coordinator.async_review_live_rail.assert_not_awaited()
    monitor.stop()


def test_disabled_monitor_registers_no_listener(hass) -> None:
    """Automatic provider use remains opt-in."""
    coordinator = _coordinator(NOW + timedelta(minutes=150))
    monitor = AutomaticRailMonitor(
        hass,
        coordinator,
        Mock(),
        enabled=False,
    )

    monitor.start()

    coordinator.async_add_listener.assert_not_called()


async def test_future_timer_schedules_checkpoint_task(hass) -> None:
    """The HA timer callback schedules rather than leaks its coroutine."""
    coordinator = _coordinator(NOW + timedelta(minutes=200))
    ledger = Mock()
    ledger.async_claim = AsyncMock(return_value=True)
    monitor = AutomaticRailMonitor(hass, coordinator, ledger, enabled=True)

    with patch(
        "custom_components.journey_guardian.rail_monitor.async_track_point_in_utc_time"
    ) as track, patch(
        "custom_components.journey_guardian.rail_monitor.dt_util.now",
        return_value=NOW,
    ):
        monitor.start()
        callback = track.call_args_list[0].args[1]
        callback(NOW + timedelta(minutes=50))
        await hass.async_block_till_done()

    coordinator.async_review_live_rail.assert_awaited_once()
    monitor.stop()
