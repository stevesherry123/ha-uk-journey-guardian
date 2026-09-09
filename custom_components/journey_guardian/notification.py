"""Cancellable, deduplicated operational notification scheduling."""

from __future__ import annotations

import asyncio
import functools
import hashlib
from collections.abc import Callable
from datetime import datetime, timedelta
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
WAKE_REMINDER_OFFSETS = (0, 5, 10)
RAIL_CHECKPOINT_MINUTES = (150, 90, 45, 10)
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
        station_access_mode: str = "auto",
    ) -> None:
        """Initialize the scheduler."""
        self._hass = hass
        self._coordinator = coordinator
        self._ledger = ledger
        self._live_notifications_enabled = live_notifications_enabled
        self._station_access_mode = station_access_mode
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
        timing = snapshot.timing
        journey = snapshot.next_journey
        if timing is not None and journey is not None:
            for reminder_number, offset_minutes in enumerate(
                WAKE_REMINDER_OFFSETS[1:], start=2
            ):
                point = timing.prepare_at + timedelta(minutes=offset_minutes)
                if now < point < timing.leave_home_at:
                    self._boundary_cancellers.append(
                        async_track_point_in_utc_time(
                            self._hass,
                            functools.partial(
                                self._async_wake_reminder_reached,
                                departure=journey.start,
                                reminder_number=reminder_number,
                            ),
                            point,
                        )
                    )
        self._hass.async_create_task(
            self._async_evaluate_notifications(snapshot),
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

    async def _async_wake_reminder_reached(
        self,
        _now: datetime,
        *,
        departure: datetime,
        reminder_number: int,
    ) -> None:
        """Emit a bounded preparation reminder for the current journey."""
        snapshot = self._coordinator.data
        journey = snapshot.next_journey
        if (
            journey is None
            or journey.start != departure
            or snapshot.operational_phase != "prepare_now"
        ):
            return
        await self._async_notify(snapshot, f"wake_{reminder_number}")

    async def _async_evaluate_notifications(
        self, snapshot: JourneySnapshot
    ) -> None:
        """Evaluate operational and live-rail notifications together."""
        await self._async_maybe_notify(snapshot)
        if (
            snapshot.simulation_active or self._live_notifications_enabled
        ) and _should_notify_rail(snapshot):
            await self._async_notify(snapshot, _rail_notification_kind(snapshot))

    async def _async_maybe_notify(self, snapshot: JourneySnapshot) -> None:
        """Create one local notification for each actionable journey phase."""
        phase = snapshot.operational_phase
        if phase not in NOTIFIABLE_PHASES or snapshot.next_journey is None:
            return
        if not snapshot.simulation_active and not self._live_notifications_enabled:
            return
        kind = "wake_1" if phase == "prepare_now" else phase
        await self._async_notify(snapshot, kind)

    async def _async_notify(self, snapshot: JourneySnapshot, kind: str) -> None:
        """Create one restart-safe local notification of a specific kind."""
        if snapshot.next_journey is None:
            return
        fingerprint = _notification_fingerprint(snapshot, kind)
        if not await self._ledger.async_claim(fingerprint):
            return
        title = (
            "UK Journey Guardian simulation"
            if snapshot.simulation_active
            else "UK Journey Guardian"
        )
        persistent_notification.async_create(
            self._hass,
            _notification_message(
                snapshot, kind, station_access_mode=self._station_access_mode
            ),
            title=title,
            notification_id=f"{DOMAIN}_{fingerprint}",
        )
        self._coordinator.record_notification(kind, dt_util.now())


def _actionable_departure(snapshot: JourneySnapshot) -> datetime:
    observation = snapshot.rail_observation
    if observation and observation.predicted_departure:
        return observation.predicted_departure
    if snapshot.next_journey is None:
        raise ValueError("A notification requires a journey")
    return snapshot.next_journey.start


def _notification_fingerprint(snapshot: JourneySnapshot, kind: str) -> str:
    """Hash private journey timing into a stable, non-reversible ledger key."""
    if snapshot.next_journey is None:
        raise ValueError("A notification requires a journey")
    departure = snapshot.next_journey.start
    source = "simulation" if snapshot.simulation_active else "calendar"
    raw_key = f"{source}|{departure.isoformat()}|{kind}"
    return hashlib.sha256(raw_key.encode()).hexdigest()[:20]


def _notification_message(
    snapshot: JourneySnapshot, kind: str, *, station_access_mode: str = "auto"
) -> str:
    """Build a concise local-only operational message."""
    timing = snapshot.timing
    departure = dt_util.as_local(_actionable_departure(snapshot)).strftime("%H:%M")
    if kind.startswith("rail_"):
        return _rail_notification_message(snapshot)
    if kind == "cancelled":
        qualifier = " simulated" if snapshot.simulation_active else ""
        return f"The {departure}{qualifier} service is cancelled."
    if kind == "provider_unavailable":
        return "Rail data is unavailable. Conservative calendar timing remains active."
    if timing is None:
        return "Journey timing requires attention."
    if kind.startswith("wake_"):
        leave = dt_util.as_local(timing.leave_home_at).strftime("%H:%M")
        reminder_number = int(kind.rsplit("_", 1)[1])
        return (
            f"Wake-up reminder {reminder_number}/3. Start getting ready. "
            f"Leave at {leave} for the {departure} departure."
        )
    station = dt_util.as_local(timing.station_arrival_at).strftime("%H:%M")
    origin = snapshot.next_journey.origin_name
    effective_mode = timing.station_access_mode
    if effective_mode == "unknown" and station_access_mode != "auto":
        effective_mode = station_access_mode
    if effective_mode == "driving":
        action = f"Time to drive to {origin}."
    elif effective_mode == "walking":
        action = f"Time to walk to {origin}."
    elif effective_mode == "bicycling":
        action = f"Time to cycle to {origin}."
    elif effective_mode == "transit":
        action = f"Time to take public transport to {origin}."
    else:
        action = f"Time to leave for {origin}."
    message = (
        f"{action} Allow {timing.station_access_minutes} minutes and aim to "
        f"arrive by {station} for the {departure} departure."
    )
    if effective_mode in {"walking", "bicycling"}:
        message += " Route guidance may not include clear pedestrian or cycle paths."
    return message


def _should_notify_rail(snapshot: JourneySnapshot) -> bool:
    """Return whether a healthy live observation deserves a status alert."""
    observation = snapshot.rail_observation
    return bool(
        snapshot.next_journey is not None
        and observation is not None
        and observation.provider_available
        and observation.freshness == "current"
        and not observation.cancelled
    )


def _rail_notification_kind(snapshot: JourneySnapshot) -> str:
    """Build a checkpoint-and-state key that suppresses unchanged repeats."""
    observation = snapshot.rail_observation
    if observation is None:
        raise ValueError("A rail notification requires an observation")
    minutes_to_departure = max(
        0,
        round(
            (
                observation.scheduled_departure - observation.observed_at
            ).total_seconds()
            / 60
        ),
    )
    checkpoint = min(
        RAIL_CHECKPOINT_MINUTES,
        key=lambda candidate: abs(candidate - minutes_to_departure),
    )
    predicted = (
        observation.predicted_departure.isoformat()
        if observation.predicted_departure is not None
        else "scheduled"
    )
    state = hashlib.sha256(
        (
            f"{observation.service_identity}|{observation.delay_minutes}|"
            f"{predicted}|{observation.platform}|{observation.leg_count}"
        ).encode()
    ).hexdigest()[:12]
    return f"rail_{checkpoint}_{state}"


def _rail_notification_message(snapshot: JourneySnapshot) -> str:
    """Describe a normalized live service without provider-specific wording."""
    observation = snapshot.rail_observation
    journey = snapshot.next_journey
    if observation is None or journey is None:
        raise ValueError("A rail notification requires a journey and observation")
    departure_value = observation.predicted_departure or observation.scheduled_departure
    departure = dt_util.as_local(departure_value).strftime("%H:%M")
    if observation.delay_minutes > 0:
        status = f"is delayed by {observation.delay_minutes} minutes"
    else:
        status = "is on time"
    message = f"The {departure} service {status}."
    if observation.platform:
        message += f" Platform {observation.platform}."
    message += f" Confirmed to call at {journey.destination_confirmation}."
    if observation.leg_count > 1:
        message += f" This journey has {observation.leg_count} rail legs."
    return message
