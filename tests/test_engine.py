"""Tests for privacy-safe Journey Guardian engine failures."""

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

from custom_components.journey_guardian.engine import JourneyGuardianEngine
from custom_components.journey_guardian.models import BudgetSnapshot

CHECKED_AT = datetime(2026, 8, 28, 16, 34, tzinfo=UTC)
CALENDAR_ENTITY = ".".join(("calendar", "example_travel"))


def _budget() -> Mock:
    budget = Mock()
    budget.snapshot.return_value = BudgetSnapshot(
        date="2026-08-28",
        calls_used=0,
        daily_limit=30,
        urgent_reserve=3,
    )
    return budget


async def test_calendar_error_is_sanitized(caplog) -> None:
    """Private exception details never enter coordinator data."""
    caplog.set_level(
        logging.WARNING,
        logger="custom_components.journey_guardian.engine",
    )
    hass = Mock()
    hass.services.async_call = AsyncMock(
        side_effect=RuntimeError("private calendar entity and request details")
    )
    budget = _budget()
    engine = JourneyGuardianEngine(
        hass,
        calendar_entity=".".join(("calendar", "private_example")),
        budget=budget,
    )

    snapshot = await engine.async_review()

    assert snapshot.status == "error"
    assert snapshot.error == "calendar_unavailable"
    assert "private" not in str(snapshot.as_dict()).casefold()
    assert "private" not in caplog.text.casefold()
    assert "RuntimeError" in caplog.text


async def test_active_calendar_journey_remains_selected() -> None:
    """An underway calendar leg remains available for follow-up monitoring."""
    hass = Mock()
    hass.services.async_call = AsyncMock(
        return_value={
            CALENDAR_ENTITY: {
                "events": [
                    {
                        "start": "2026-08-28T16:30:00+00:00",
                        "end": "2026-08-28T17:30:00+00:00",
                        "summary": "Rail - Example Central to Example Junction",
                        "location": "Example Central",
                    }
                ]
            }
        }
    )
    engine = JourneyGuardianEngine(
        hass,
        calendar_entity=CALENDAR_ENTITY,
        budget=_budget(),
    )

    with patch(
        "custom_components.journey_guardian.engine.dt_util.now",
        return_value=CHECKED_AT,
    ):
        snapshot = await engine.async_review()

    assert snapshot.status == "active"
    assert snapshot.next_journey is not None
    assert snapshot.next_journey.end == datetime(
        2026, 8, 28, 17, 30, tzinfo=UTC
    )


async def test_future_calendar_journey_remains_planned() -> None:
    """A journey that has not started remains in the planned state."""
    hass = Mock()
    hass.services.async_call = AsyncMock(
        return_value={
            CALENDAR_ENTITY: {
                "events": [
                    {
                        "start": "2026-08-28T17:00:00+00:00",
                        "end": "2026-08-28T18:00:00+00:00",
                        "summary": "Rail - Example Central to Example Junction",
                        "location": "Example Central",
                    }
                ]
            }
        }
    )
    engine = JourneyGuardianEngine(
        hass,
        calendar_entity=CALENDAR_ENTITY,
        budget=_budget(),
    )

    with patch(
        "custom_components.journey_guardian.engine.dt_util.now",
        return_value=CHECKED_AT,
    ):
        snapshot = await engine.async_review()

    assert snapshot.status == "planned"
    assert snapshot.next_journey is not None
    assert snapshot.timing is not None
    assert snapshot.timing.station_arrival_at == datetime(
        2026, 8, 28, 16, 45, tzinfo=UTC
    )
    assert snapshot.timing.leave_home_at == datetime(
        2026, 8, 28, 15, 45, tzinfo=UTC
    )
    assert snapshot.timing.prepare_at == datetime(
        2026, 8, 28, 15, 5, tzinfo=UTC
    )


async def test_completed_calendar_journey_returns_to_idle() -> None:
    """A calendar leg is released once its timed event has completed."""
    hass = Mock()
    hass.services.async_call = AsyncMock(
        return_value={
            CALENDAR_ENTITY: {
                "events": [
                    {
                        "start": "2026-08-28T15:30:00+00:00",
                        "end": "2026-08-28T16:30:00+00:00",
                        "summary": "Rail - Example Central to Example Junction",
                        "location": "Example Central",
                    }
                ]
            }
        }
    )
    engine = JourneyGuardianEngine(
        hass,
        calendar_entity=CALENDAR_ENTITY,
        budget=_budget(),
    )

    with patch(
        "custom_components.journey_guardian.engine.dt_util.now",
        return_value=CHECKED_AT,
    ):
        snapshot = await engine.async_review()

    assert snapshot.status == "idle"
    assert snapshot.next_journey is None
    assert snapshot.timing is None
