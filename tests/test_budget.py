"""Tests for durable, fail-safe TransportAPI budget state."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from custom_components.journey_guardian.budget import TransportAPIBudget

NOW = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)


async def test_budget_restores_usage_across_restart(hass) -> None:
    """A restart cannot restore provider allowance already consumed today."""
    budget = TransportAPIBudget(hass, daily_limit=30, urgent_reserve=3)
    budget._store = AsyncMock()
    budget._store.async_load.return_value = {
        "date": "2026-09-03",
        "calls_used": 12,
    }

    with patch(
        "custom_components.journey_guardian.budget.dt_util.now",
        return_value=NOW,
    ):
        await budget.async_load()
        reserved = await budget.async_reserve_call()
        calls_used = budget.snapshot().calls_used

    assert reserved
    assert calls_used == 13
    budget._store.async_save.assert_awaited_with(
        {"date": "2026-09-03", "calls_used": 13}
    )


async def test_malformed_budget_state_fails_closed(hass) -> None:
    """Malformed storage exhausts allowance and is immediately rewritten."""
    budget = TransportAPIBudget(hass, daily_limit=30, urgent_reserve=3)
    budget._store = AsyncMock()
    budget._store.async_load.return_value = {
        "date": "2026-09-03",
        "calls_used": "not-a-number",
    }

    with patch(
        "custom_components.journey_guardian.budget.dt_util.now",
        return_value=NOW,
    ):
        await budget.async_load()
        calls_used = budget.snapshot().calls_used

    assert calls_used == 30
    budget._store.async_save.assert_awaited_once_with(
        {"date": "2026-09-03", "calls_used": 30}
    )


async def test_impossible_stored_usage_is_clamped_to_hard_limit(hass) -> None:
    """Corrupt high usage cannot roll over into additional provider calls."""
    budget = TransportAPIBudget(hass, daily_limit=30, urgent_reserve=3)
    budget._store = AsyncMock()
    budget._store.async_load.return_value = {
        "date": "2026-09-03",
        "calls_used": 999,
    }

    with patch(
        "custom_components.journey_guardian.budget.dt_util.now",
        return_value=NOW,
    ):
        await budget.async_load()
        reserved = await budget.async_reserve_call(urgent=True)
        calls_used = budget.snapshot().calls_used

    assert not reserved
    assert calls_used == 30
