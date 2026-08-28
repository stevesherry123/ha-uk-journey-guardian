"""Tests for Journey Guardian coordinator polling."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.journey_guardian.const import (
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.journey_guardian.coordinator import JourneyGuardianCoordinator
from custom_components.journey_guardian.models import BudgetSnapshot, JourneySnapshot

CHECKED_AT = datetime(2026, 8, 28, 14, 15, tzinfo=UTC)
BUDGET = BudgetSnapshot(
    date="2026-08-28",
    calls_used=0,
    daily_limit=30,
    urgent_reserve=3,
)


async def test_error_retains_normal_polling_interval(hass) -> None:
    """Temporary calendar failures do not create aggressive polling."""
    engine = Mock()
    engine.async_review = AsyncMock(
        return_value=JourneySnapshot(
            status="error",
            checked_at=CHECKED_AT,
            next_journey=None,
            budget=BUDGET,
            error="calendar_unavailable",
        )
    )
    coordinator = JourneyGuardianCoordinator(
        hass,
        MockConfigEntry(domain=DOMAIN),
        engine,
    )

    error_snapshot = await coordinator._async_update_data()

    assert error_snapshot.status == "error"
    assert coordinator.update_interval == DEFAULT_UPDATE_INTERVAL
