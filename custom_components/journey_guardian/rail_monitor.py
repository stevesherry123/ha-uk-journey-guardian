"""Restart-safe, quota-controlled automatic live-rail checkpoints."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    AUTO_RAIL_STORAGE_KEY,
    AUTO_RAIL_STORAGE_VERSION,
    DOMAIN,
)
from .coordinator import JourneyGuardianCoordinator

_LOGGER = logging.getLogger(__name__)

CHECKPOINT_MINUTES = (150, 90, 45, 10)
CATCHUP_WINDOW = timedelta(minutes=12)
MAX_LEDGER_ENTRIES = 100


class AutomaticRailLedger:
    """Persist privacy-safe automatic-check claims across restarts."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the bounded ledger."""
        self._store: Store[dict[str, Any]] = Store(
            hass, AUTO_RAIL_STORAGE_VERSION, AUTO_RAIL_STORAGE_KEY
        )
        self._keys: list[str] = []
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Restore valid bounded claim keys."""
        stored = await self._store.async_load() or {}
        keys = stored.get("keys", [])
        self._keys = (
            [str(key) for key in keys[-MAX_LEDGER_ENTRIES:]]
            if isinstance(keys, list)
            else []
        )

    async def async_claim(self, key: str) -> bool:
        """Claim a checkpoint once before any provider reservation."""
        async with self._lock:
            if key in self._keys:
                return False
            self._keys.append(key)
            self._keys = self._keys[-MAX_LEDGER_ENTRIES:]
            await self._store.async_save({"keys": self._keys})
            return True


class AutomaticRailMonitor:
    """Schedule a small fixed set of live checks for the current journey."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: JourneyGuardianCoordinator,
        ledger: AutomaticRailLedger,
        *,
        enabled: bool,
    ) -> None:
        """Initialize an opt-in monitor."""
        self._hass = hass
        self._coordinator = coordinator
        self._ledger = ledger
        self._enabled = enabled
        self._checkpoint_cancellers: list[Callable[[], None]] = []
        self._remove_listener: Callable[[], None] | None = None

    @callback
    def start(self) -> None:
        """Start scheduling only when explicitly enabled."""
        if not self._enabled:
            return
        self._remove_listener = self._coordinator.async_add_listener(
            self._handle_coordinator_update
        )
        self._handle_coordinator_update()

    @callback
    def stop(self) -> None:
        """Cancel all listeners and future checkpoints."""
        self._cancel_checkpoints()
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Rebuild checkpoints for the currently selected calendar journey."""
        self._cancel_checkpoints()
        snapshot = self._coordinator.data
        journey = snapshot.next_journey
        if (
            journey is None
            or snapshot.simulation_active
            or snapshot.status in {"active", "cancelled"}
            or not self._coordinator.engine.live_rail_configured
        ):
            return

        now = dt_util.now()
        for lead_minutes in CHECKPOINT_MINUTES:
            point = journey.start - timedelta(minutes=lead_minutes)
            if point > now:
                self._checkpoint_cancellers.append(
                    async_track_point_in_utc_time(
                        self._hass,
                        lambda reached_at,
                        departure=journey.start,
                        lead=lead_minutes: self._checkpoint_reached(
                            reached_at, departure, lead
                        ),
                        point,
                    )
                )
            elif now - point <= CATCHUP_WINDOW:
                self._hass.async_create_task(
                    self._async_run_checkpoint(journey.start, lead_minutes),
                    f"{DOMAIN} catch up automatic rail checkpoint",
                )

    @callback
    def _cancel_checkpoints(self) -> None:
        for cancel in self._checkpoint_cancellers:
            cancel()
        self._checkpoint_cancellers.clear()

    @callback
    def _checkpoint_reached(
        self,
        _reached_at: datetime,
        departure: datetime,
        lead_minutes: int,
    ) -> None:
        """Schedule one reached checkpoint in Home Assistant's task loop."""
        self._hass.async_create_task(
            self._async_run_checkpoint(departure, lead_minutes),
            f"{DOMAIN} automatic rail checkpoint",
        )

    async def _async_run_checkpoint(
        self, departure: datetime, lead_minutes: int
    ) -> None:
        """Claim and execute a checkpoint if it is still the current journey."""
        current = self._coordinator.data.next_journey
        if current is None or current.start != departure:
            return
        claim = hashlib.sha256(
            f"{departure.isoformat()}|{lead_minutes}".encode()
        ).hexdigest()[:24]
        if not await self._ledger.async_claim(claim):
            return
        try:
            await self._coordinator.async_review_live_rail(
                decision_path="transportapi_automatic",
                urgent=lead_minutes <= 10,
            )
        except Exception as err:  # HA and provider errors are sanitized elsewhere.
            _LOGGER.warning(
                "Automatic rail checkpoint failed with %s",
                type(err).__name__,
            )
