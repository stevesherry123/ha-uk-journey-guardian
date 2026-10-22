"""Cancellable, deduplicated operational notification scheduling."""

from __future__ import annotations

import asyncio
import functools
import hashlib
import logging
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

_LOGGER = logging.getLogger(__name__)

NOTIFIABLE_PHASES = {
    "prepare_now",
    "leave_now",
    "cancelled",
    "provider_unavailable",
}
WAKE_REMINDER_OFFSETS = (0, 5, 10)
RAIL_CHECKPOINT_MINUTES = (150, 90, 45, 10, 2)
MAX_LEDGER_ENTRIES = 100
HOME_WAKE_NOTIFICATION_ID = f"{DOMAIN}_home_wake_alarm"


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
        announcement_text_entity: str = "",
        announcement_script_entity: str = "",
        person_entity: str = "",
        home_zone_entity: str = "zone.home",
        home_wake_enabled: bool = False,
        home_wake_awake_entity: str = "",
        home_wake_awake_state: str = "on",
        home_wake_repeat_seconds: int = 6,
        home_wake_max_minutes: int = 15,
    ) -> None:
        """Initialize the scheduler."""
        self._hass = hass
        self._coordinator = coordinator
        self._ledger = ledger
        self._live_notifications_enabled = live_notifications_enabled
        self._station_access_mode = station_access_mode
        self._announcement_text_entity = announcement_text_entity.strip()
        self._announcement_script_entity = announcement_script_entity.strip()
        self._person_entity = person_entity.strip()
        self._home_zone_entity = home_zone_entity.strip()
        self._home_wake_enabled = home_wake_enabled
        self._home_wake_awake_entity = home_wake_awake_entity.strip()
        self._home_wake_awake_state = home_wake_awake_state.casefold().strip()
        self._home_wake_repeat_seconds = max(5, home_wake_repeat_seconds)
        self._home_wake_max_minutes = max(1, home_wake_max_minutes)
        self._delivery_lock = asyncio.Lock()
        self._boundary_cancellers: list[Callable[[], None]] = []
        self._remove_listener: Callable[[], None] | None = None
        self._home_wake_task: asyncio.Task[None] | None = None
        self._home_wake_departure: datetime | None = None
        self._home_wake_completed_departure: datetime | None = None
        self._home_wake_delivery_count = 0
        self._home_wake_last_delivery: str | None = None
        self._home_wake_last_stop_reason: str | None = None

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
        self._cancel_home_wake_alarm(reason="integration_stopped")
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Reschedule exact boundaries and evaluate the current phase."""
        self._cancel_boundaries()
        snapshot = self._coordinator.data
        now = dt_util.now()
        self._record_awake_evidence(snapshot)
        home_wake_alarm = self._should_run_home_wake_alarm(snapshot)
        self._sync_home_wake_alarm(snapshot, home_wake_alarm)
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
        if timing is not None and journey is not None and not home_wake_alarm:
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
                elif point <= now < timing.leave_home_at and now - point <= timedelta(
                    minutes=1
                ):
                    # A simultaneous coordinator refresh can cancel a due timer.
                    # The ledger makes this catch-up safe if the timer also ran.
                    self._hass.async_create_task(
                        self._async_wake_reminder_reached(
                            now,
                            departure=journey.start,
                            reminder_number=reminder_number,
                        ),
                        f"{DOMAIN} catch up preparation reminder",
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

    @callback
    def _sync_home_wake_alarm(
        self, snapshot: JourneySnapshot, should_run: bool
    ) -> None:
        """Start or stop the high-frequency home wake-up loop."""
        journey = snapshot.next_journey
        if not should_run or journey is None:
            self._cancel_home_wake_alarm(
                reason=self._home_wake_readiness(snapshot)
            )
            return
        if (
            self._home_wake_task is not None
            and not self._home_wake_task.done()
            and self._home_wake_departure == journey.start
        ):
            return
        self._cancel_home_wake_alarm(reason="journey_changed")
        self._home_wake_departure = journey.start
        self._home_wake_delivery_count = 0
        self._home_wake_last_delivery = None
        self._home_wake_last_stop_reason = None
        self._home_wake_task = self._hass.async_create_task(
            self._async_run_home_wake_alarm(journey.start),
            f"{DOMAIN} home wake alarm",
        )

    @callback
    def _cancel_home_wake_alarm(self, *, reason: str) -> None:
        task = self._home_wake_task
        self._home_wake_task = None
        self._home_wake_departure = None
        if task is not None and not task.done():
            self._home_wake_last_stop_reason = reason
            task.cancel()

    async def _async_run_home_wake_alarm(self, departure: datetime) -> None:
        """Repeat a wake-up message while the traveller is home and asleep."""
        started_at = dt_util.now()
        try:
            while True:
                snapshot = self._coordinator.data
                journey = snapshot.next_journey
                timing = snapshot.timing
                if self._awake_state_observed():
                    self._home_wake_completed_departure = departure
                    self._home_wake_last_stop_reason = "awake"
                    return
                if (
                    journey is None
                    or journey.start != departure
                    or timing is None
                    or not self._should_run_home_wake_alarm(snapshot)
                ):
                    self._home_wake_last_stop_reason = (
                        self._home_wake_readiness(snapshot)
                    )
                    return
                deadline = min(
                    timing.leave_home_at,
                    started_at + timedelta(minutes=self._home_wake_max_minutes),
                )
                now = dt_util.now()
                if now >= deadline:
                    self._home_wake_completed_departure = departure
                    self._home_wake_last_stop_reason = (
                        "leave_home"
                        if now >= timing.leave_home_at
                        else "safety_limit"
                    )
                    return
                self._home_wake_last_delivery = await self._async_deliver(
                    _notification_message(snapshot, "wake_alarm"),
                    title="UK Journey Guardian wake-up",
                    notification_id=HOME_WAKE_NOTIFICATION_ID,
                    simulation=False,
                )
                self._home_wake_delivery_count += 1
                self._coordinator.record_notification("wake_alarm", dt_util.now())
                remaining = (deadline - dt_util.now()).total_seconds()
                if remaining <= 0:
                    self._home_wake_completed_departure = departure
                    self._home_wake_last_stop_reason = (
                        "leave_home"
                        if dt_util.now() >= timing.leave_home_at
                        else "safety_limit"
                    )
                    return
                await asyncio.sleep(
                    min(self._home_wake_repeat_seconds, remaining)
                )
        finally:
            if asyncio.current_task() is self._home_wake_task:
                self._home_wake_task = None
                self._home_wake_departure = None

    def _should_run_home_wake_alarm(self, snapshot: JourneySnapshot) -> bool:
        """Return whether this snapshot needs the home-only repeating alarm."""
        return self._home_wake_readiness(snapshot) == "ready"

    def _home_wake_finished(self, snapshot: JourneySnapshot) -> bool:
        """Do not restart bounded wake reminders after the home alarm finishes."""
        journey = snapshot.next_journey
        return bool(
            self._home_wake_enabled
            and not snapshot.simulation_active
            and journey is not None
            and self._person_is_home()
            and (
                self._awake_state_observed()
                or self._home_wake_completed_departure == journey.start
            )
        )

    def _home_wake_readiness(self, snapshot: JourneySnapshot) -> str:
        """Explain whether the repeating alarm can run for this snapshot."""
        if not self._home_wake_enabled:
            return "disabled"
        if not self._live_notifications_enabled:
            return "notifications_disabled"
        if snapshot.simulation_active:
            return "simulation"
        if snapshot.next_journey is None:
            return "no_journey"
        if snapshot.timing is None:
            return "timing_unavailable"
        if snapshot.operational_phase != "prepare_now":
            return snapshot.operational_phase
        if self._home_wake_completed_departure == snapshot.next_journey.start:
            return "completed"
        if not self._person_is_home():
            return "away"
        if self._awake_state_observed():
            return "awake"
        return "ready"

    def diagnostics(self) -> dict[str, Any]:
        """Return privacy-safe alarm eligibility and delivery evidence."""
        task = self._home_wake_task
        status = self._home_wake_readiness(self._coordinator.data)
        if task is not None and not task.done():
            status = "ringing"
        return {
            "enabled": self._home_wake_enabled,
            "status": status,
            "awake_evidence_configured": bool(
                self._home_wake_awake_entity
            ),
            "announcement_engine_configured": (
                self._announcement_engine_configured()
            ),
            "repeat_seconds": self._home_wake_repeat_seconds,
            "max_minutes": self._home_wake_max_minutes,
            "delivery_count": self._home_wake_delivery_count,
            "last_delivery": self._home_wake_last_delivery,
            "last_stop_reason": self._home_wake_last_stop_reason,
        }

    def _record_awake_evidence(self, snapshot: JourneySnapshot) -> None:
        """Remember momentary awake evidence for the current departure."""
        journey = snapshot.next_journey
        if (
            journey is not None
            and snapshot.operational_phase == "prepare_now"
            and self._person_is_home()
            and self._awake_state_observed()
        ):
            self._home_wake_completed_departure = journey.start

    def _person_is_home(self) -> bool:
        """Match the configured traveller against the configured home zone."""
        traveller_state = self._hass.states.get(self._person_entity)
        if traveller_state is None:
            return False
        home_names = {"home"}
        if self._home_zone_entity.startswith("zone."):
            home_names.add(self._home_zone_entity.removeprefix("zone.").casefold())
        zone = self._hass.states.get(self._home_zone_entity)
        if zone is not None:
            friendly_name = str(zone.attributes.get("friendly_name", "")).strip()
            if friendly_name:
                home_names.add(friendly_name.casefold())
        return traveller_state.state.casefold() in home_names

    def _awake_state_observed(self) -> bool:
        """Return whether the configured evidence entity reports awake."""
        state = self._hass.states.get(self._home_wake_awake_entity)
        return bool(
            state is not None
            and state.state.casefold() == self._home_wake_awake_state
        )

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
            or self._home_wake_finished(snapshot)
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
        if phase == "prepare_now" and (
            self._should_run_home_wake_alarm(snapshot)
            or self._home_wake_finished(snapshot)
        ):
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
        message = _notification_message(
            snapshot, kind, station_access_mode=self._station_access_mode
        )
        await self._async_deliver(
            message,
            title=title,
            notification_id=f"{DOMAIN}_{fingerprint}",
            simulation=snapshot.simulation_active,
        )
        self._coordinator.record_notification(kind, dt_util.now())

    async def async_manual_review(
        self, message: str, summary: str, *, simulation: bool
    ) -> str:
        """Respond to an explicit request, including while automatic alerts are off."""
        notification_id = f"{DOMAIN}_travel_review"
        title = "Travel review simulation" if simulation else "Travel review"
        try:
            async with asyncio.timeout(20):
                delivery = await self._async_deliver(
                    summary, title=title, notification_id=notification_id,
                    simulation=simulation, script_data={"message": summary},
                )
        except TimeoutError:
            delivery = "persistent_notification"
        persistent_notification.async_create(
            self._hass, message, title=title, notification_id=notification_id
        )
        self._coordinator.record_notification("manual_review", dt_util.now())
        return delivery

    async def _async_deliver(
        self,
        message: str,
        *,
        title: str,
        notification_id: str,
        simulation: bool,
        script_data: dict | None = None,
    ) -> str:
        """Deliver live messages through the configured announcement engine."""
        configured = self._announcement_engine_configured()
        if not simulation and configured:
            try:
                async with self._delivery_lock:
                    await self._hass.services.async_call(
                        "input_text",
                        "set_value",
                        {
                            "entity_id": self._announcement_text_entity,
                            "value": message,
                        },
                        blocking=True,
                    )
                    await self._hass.services.async_call(
                        "script",
                        self._announcement_script_entity.removeprefix("script."),
                        script_data or {},
                        blocking=True,
                    )
                return "announcement_engine"
            except Exception as err:  # HA service failures vary by platform.
                _LOGGER.warning(
                    "Announcement delivery failed with %s; using local fallback",
                    type(err).__name__,
                )
        persistent_notification.async_create(
            self._hass,
            message,
            title=title,
            notification_id=notification_id,
        )
        return "persistent_notification"

    def _announcement_engine_configured(self) -> bool:
        """Return whether live delivery can call the selected script."""
        return bool(
            self._announcement_text_entity.startswith("input_text.")
            and self._announcement_script_entity.startswith("script.")
        )


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
    routing_note = ""
    if not snapshot.simulation_active:
        if timing.station_access_source == "configured_fallback":
            routing_note = (
                " Worst-case planning allowance; live routing unavailable."
            )
        elif timing.station_access_fallback_reason:
            routing_note = " Google driving estimate; Waze unavailable."
    if kind == "wake_alarm":
        leave = dt_util.as_local(timing.leave_home_at).strftime("%H:%M")
        origin = snapshot.next_journey.origin_name
        return (
            f"Wake up now. It is time to get out of bed. Your {departure} "
            f"train leaves from {origin}. You need to leave home at {leave}."
            f"{routing_note}"
        )
    if kind.startswith("wake_"):
        leave = dt_util.as_local(timing.leave_home_at).strftime("%H:%M")
        reminder_number = int(kind.rsplit("_", 1)[1])
        return (
            f"Wake-up reminder {reminder_number}/3. Start getting ready. "
            f"Leave at {leave} for the {departure} departure.{routing_note}"
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
    return message + routing_note


def _should_notify_rail(snapshot: JourneySnapshot) -> bool:
    """Return whether a healthy live observation deserves a status alert."""
    observation = snapshot.rail_observation
    return bool(
        snapshot.next_journey is not None
        and snapshot.next_journey.decision_path != "travel_review_manual"
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
