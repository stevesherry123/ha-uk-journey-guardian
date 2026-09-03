"""Persistent TransportAPI quota management."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import STORAGE_KEY, STORAGE_VERSION
from .models import BudgetSnapshot
from .quota import can_reserve_call


class TransportAPIBudget:
    """Serialize and persist all TransportAPI call reservations."""

    def __init__(
        self,
        hass: HomeAssistant,
        daily_limit: int,
        urgent_reserve: int,
    ) -> None:
        """Initialize the budget manager."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY
        )
        self._daily_limit = daily_limit
        self._urgent_reserve = min(urgent_reserve, daily_limit)
        self._date = dt_util.now().date().isoformat()
        self._calls_used = 0
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Restore the persisted budget and roll over stale days."""
        loaded = await self._store.async_load() or {}
        stored = loaded if isinstance(loaded, Mapping) else {}
        today = dt_util.now().date().isoformat()
        if stored.get("date") == today:
            self._calls_used = _safe_calls_used(
                stored.get("calls_used"), self._daily_limit
            )
        else:
            self._calls_used = 0
        self._date = today
        await self._async_save()

    def snapshot(self) -> BudgetSnapshot:
        """Return the current immutable budget state."""
        self._rollover_if_needed()
        return BudgetSnapshot(
            date=self._date,
            calls_used=self._calls_used,
            daily_limit=self._daily_limit,
            urgent_reserve=self._urgent_reserve,
        )

    async def async_reserve_call(self, *, urgent: bool = False) -> bool:
        """Atomically reserve one call if the relevant allowance permits it."""
        async with self._lock:
            self._rollover_if_needed()
            if not can_reserve_call(
                calls_used=self._calls_used,
                daily_limit=self._daily_limit,
                urgent_reserve=self._urgent_reserve,
                urgent=urgent,
            ):
                return False
            self._calls_used += 1
            await self._async_save()
            return True

    def _rollover_if_needed(self) -> None:
        today = dt_util.now().date().isoformat()
        if self._date != today:
            self._date = today
            self._calls_used = 0

    async def _async_save(self) -> None:
        await self._store.async_save(
            {"date": self._date, "calls_used": self._calls_used}
        )


def _safe_calls_used(value: Any, daily_limit: int) -> int:
    """Treat malformed persisted quota state as exhausted, never permissive."""
    try:
        calls_used = int(value)
    except (TypeError, ValueError):
        return daily_limit
    return min(daily_limit, max(0, calls_used))
