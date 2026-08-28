"""Tests for privacy-safe Journey Guardian engine failures."""

import logging
from unittest.mock import AsyncMock, Mock

from custom_components.journey_guardian.engine import JourneyGuardianEngine
from custom_components.journey_guardian.models import BudgetSnapshot


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
    budget = Mock()
    budget.snapshot.return_value = BudgetSnapshot(
        date="2026-08-28",
        calls_used=0,
        daily_limit=30,
        urgent_reserve=3,
    )
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
