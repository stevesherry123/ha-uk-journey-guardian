"""Restart-safe, quota-controlled automatic live-rail checkpoints."""

from __future__ import annotations

import asyncio
import functools
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

CHECKPOINT_MINUTES = (150, 90, 45, 10, 2)
POST_DEPARTURE_CHECKPOINT_MINUTES = (5, 15, 30)
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
        self._coordinator.next_live_check_at = None
        snapshot = self._coordinator.data
        journey = snapshot.next_journey
        if (
            journey is None
            or snapshot.simulation_active
            or snapshot.status == "cancelled"
            or not self._coordinator.engine.live_rail_configured
        ):
            return

        now = dt_util.now()
        future_points: list[datetime] = []
        catchup_points: list[tuple[datetime, int]] = []
        for lead_minutes in CHECKPOINT_MINUTES:
            point = journey.start - timedelta(minutes=lead_minutes)
            if point > now:
                future_points.append(point)
                self._checkpoint_cancellers.append(
                    async_track_point_in_utc_time(
                        self._hass,
                        functools.partial(
                            self._async_checkpoint_reached,
                            departure=journey.start,
                            lead_minutes=lead_minutes,
                        ),
                        point,
                    )
                )
            elif now - point <= CATCHUP_WINDOW:
                catchup_points.append((point, lead_minutes))
        # A service which is still reported on time at the final pre-departure
        # check can acquire a delay afterwards. Always keep a bounded set of
        # post-departure checks so that this last-minute change is observed.
        for elapsed_minutes in POST_DEPARTURE_CHECKPOINT_MINUTES:
            point = journey.start + timedelta(minutes=elapsed_minutes)
            if point > now:
                future_points.append(point)
                self._checkpoint_cancellers.append(
                    async_track_point_in_utc_time(
                        self._hass,
                        functools.partial(
                            self._async_checkpoint_reached,
                            departure=journey.start,
                            lead_minutes=-elapsed_minutes,
                        ),
                        point,
                    )
                )
            elif now - point <= CATCHUP_WINDOW:
                catchup_points.append((point, -elapsed_minutes))
        # Catch-up windows overlap around departure. Run only the most recent
        # due checkpoint so a coordinator refresh cannot spend quota twice for
        # effectively the same live observation.
        if catchup_points:
            _point, lead_minutes = max(catchup_points, key=lambda item: item[0])
            self._hass.async_create_task(
                self._async_run_checkpoint(journey.start, lead_minutes),
                f"{DOMAIN} catch up rail checkpoint",
            )
        if future_points:
            self._coordinator.next_live_check_at = min(future_points)

    @callback
    def _cancel_checkpoints(self) -> None:
        for cancel in self._checkpoint_cancellers:
            cancel()
        self._checkpoint_cancellers.clear()

    async def _async_checkpoint_reached(
        self,
        _reached_at: datetime,
        departure: datetime,
        lead_minutes: int,
    ) -> None:
        """Run a reached checkpoint directly in Home Assistant's async job."""
        await self._async_run_checkpoint(departure, lead_minutes)

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
