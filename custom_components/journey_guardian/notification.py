"""Cancellable, deduplicated operational notification scheduling."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    NOTIFICATION_STORAGE_KEY,
    NOTIFICATION_STORAGE_VERSION,
)
from .coordinator import JourneyGuardianCoordinator
from .models import JourneySnapshot
from .phase import future_phase_boundaries

NOTIFIABLE_PHASES = {
    "prepare_now",
    "leave_now",
    "cancelled",
    "provider_unavailable",
}
MAX_LEDGER_ENTRIES = 100


class NotificationLedger:
    """Persist privacy-safe notification fingerprints across restarts."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the notification ledger."""
        self._store: Store[dict[str, Any]] = Store(
            hass, NOTIFICATION_STORAGE_VERSION, NOTIFICATION_STORAGE_KEY
        )
        self._keys: list[str] = []
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Load bounded notification fingerprints from storage."""
        stored = await self._store.async_load() or {}
        keys = stored.get("keys", [])
        self._keys = (
            [str(key) for key in keys[-MAX_LEDGER_ENTRIES:]]
            if isinstance(keys, list)
            else []
        )

    async def async_claim(self, key: str) -> bool:
        """Atomically claim a notification fingerprint once."""
        async with self._lock:
            if key in self._keys:
                return False
            self._keys.append(key)
            self._keys = self._keys[-MAX_LEDGER_ENTRIES:]
            await self._store.async_save({"keys": self._keys})
            return True


class JourneyNotificationScheduler:
    """Refresh at journey boundaries and emit deduplicated notifications."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: JourneyGuardianCoordinator,
        ledger: NotificationLedger,
        *,
        live_notifications_enabled: bool,
    ) -> None:
        """Initialize the scheduler."""
        self._hass = hass
        self._coordinator = coordinator
        self._ledger = ledger
        self._live_notifications_enabled = live_notifications_enabled
        self._boundary_cancellers: list[Callable[[], None]] = []
        self._remove_listener: Callable[[], None] | None = None

    @callback
    def start(self) -> None:
        """Start observing coordinator changes and schedule current boundaries."""
        self._remove_listener = self._coordinator.async_add_listener(
            self._handle_coordinator_update
        )
        self._handle_coordinator_update()

    @callback
    def stop(self) -> None:
        """Cancel all boundary and coordinator listeners."""
        self._cancel_boundaries()
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Reschedule exact boundaries and evaluate the current phase."""
        self._cancel_boundaries()
        snapshot = self._coordinator.data
        now = dt_util.now()
        departure = (
            _actionable_departure(snapshot)
            if snapshot.next_journey is not None
            else None
        )
        for _phase, point in future_phase_boundaries(
            snapshot.timing, departure, now
        ):
            self._boundary_cancellers.append(
                async_track_point_in_utc_time(
                    self._hass, self._async_boundary_reached, point
                )
            )
        self._hass.async_create_task(
            self._async_maybe_notify(snapshot),
            f"{DOMAIN} evaluate operational notification",
        )

    @callback
    def _cancel_boundaries(self) -> None:
        for cancel in self._boundary_cancellers:
            cancel()
        self._boundary_cancellers.clear()

    async def _async_boundary_reached(self, _now: datetime) -> None:
        """Refresh the shared decision at an exact operational boundary."""
        await self._coordinator.async_request_refresh()

    async def _async_maybe_notify(self, snapshot: JourneySnapshot) -> None:
        """Create one local notification for each actionable journey phase."""
        phase = snapshot.operational_phase
        if phase not in NOTIFIABLE_PHASES or snapshot.next_journey is None:
            return
        if not snapshot.simulation_active and not self._live_notifications_enabled:
            return
        fingerprint = _notification_fingerprint(snapshot, phase)
        if not await self._ledger.async_claim(fingerprint):
            return
        title = (
            "UK Journey Guardian simulation"
            if snapshot.simulation_active
            else "UK Journey Guardian"
        )
        persistent_notification.async_create(
            self._hass,
            _notification_message(snapshot, phase),
            title=title,
            notification_id=f"{DOMAIN}_{fingerprint}",
        )


def _actionable_departure(snapshot: JourneySnapshot) -> datetime:
    observation = snapshot.rail_observation
    if observation and observation.predicted_departure:
        return observation.predicted_departure
    if snapshot.next_journey is None:
        raise ValueError("A notification requires a journey")
    return snapshot.next_journey.start


def _notification_fingerprint(snapshot: JourneySnapshot, phase: str) -> str:
    """Hash private journey timing into a stable, non-reversible ledger key."""
    departure = _actionable_departure(snapshot)
    source = "simulation" if snapshot.simulation_active else "calendar"
    raw_key = f"{source}|{departure.isoformat()}|{phase}"
    return hashlib.sha256(raw_key.encode()).hexdigest()[:20]


def _notification_message(snapshot: JourneySnapshot, phase: str) -> str:
    """Build a concise local-only operational message."""
    timing = snapshot.timing
    departure = dt_util.as_local(_actionable_departure(snapshot)).strftime("%H:%M")
    if phase == "cancelled":
        qualifier = " simulated" if snapshot.simulation_active else ""
        return f"The {departure}{qualifier} service is cancelled."
    if phase == "provider_unavailable":
        return "Rail data is unavailable. Conservative calendar timing remains active."
    if timing is None:
        return "Journey timing requires attention."
    if phase == "prepare_now":
        leave = dt_util.as_local(timing.leave_home_at).strftime("%H:%M")
        return f"Prepare now. Leave at {leave} for the {departure} departure."
    station = dt_util.as_local(timing.station_arrival_at).strftime("%H:%M")
    return f"Leave now. Aim to arrive by {station} for the {departure} departure."
