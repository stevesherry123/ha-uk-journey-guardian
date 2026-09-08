"""Tests for automatic station-access refresh checkpoints."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

from custom_components.journey_guardian.models import (
    BudgetSnapshot,
    JourneyEvent,
    JourneySnapshot,
)
from custom_components.journey_guardian.station_access_monitor import (
    StationAccessMonitor,
)

NOW = datetime(2026, 9, 8, 20, 0, tzinfo=UTC)
BUDGET = BudgetSnapshot("2026-09-08", 0, 30, 3)


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
    coordinator.engine.station_access_configured = True
    coordinator.async_add_listener.return_value = Mock()
    coordinator.async_test_station_access = AsyncMock()
    return coordinator


def test_monitor_schedules_next_useful_checkpoint(hass) -> None:
    """A distant journey first refreshes six hours before departure."""
    departure = NOW + timedelta(hours=8)
    coordinator = _coordinator(departure)
    monitor = StationAccessMonitor(hass, coordinator)

    with patch(
        "custom_components.journey_guardian.station_access_monitor.dt_util.now",
        return_value=NOW,
    ):
        monitor.start()

    assert coordinator.next_station_access_check_at == departure - timedelta(
        hours=6
    )
    monitor.stop()


async def test_reached_checkpoint_forces_fresh_route(hass) -> None:
    """A scheduled checkpoint invokes the cache-bypassing route review."""
    departure = NOW + timedelta(minutes=15)
    coordinator = _coordinator(departure)
    monitor = StationAccessMonitor(hass, coordinator)

    await monitor._async_checkpoint_reached(NOW, departure)

    coordinator.async_test_station_access.assert_awaited_once_with()


async def test_stale_checkpoint_does_not_review_changed_journey(hass) -> None:
    """A timer from a superseded calendar event cannot update timings."""
    coordinator = _coordinator(NOW + timedelta(hours=1))
    monitor = StationAccessMonitor(hass, coordinator)

    await monitor._async_checkpoint_reached(
        NOW,
        NOW + timedelta(hours=2),
    )

    coordinator.async_test_station_access.assert_not_awaited()
