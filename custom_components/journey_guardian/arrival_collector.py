"""Restart-safe collection of provider-confirmed destination arrivals."""

from __future__ import annotations

import asyncio
import functools
import hashlib
import logging
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .check_history import CheckHistory
from .coordinator import JourneyGuardianCoordinator
from .models import JourneySnapshot
from .provider_broker import ProviderBrokerError
from .rail import service_identity
from .railinfo import RailinfoClient

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = "journey_guardian.arrival_collector"
CHECK_OFFSETS = (timedelta(minutes=5), timedelta(minutes=20), timedelta(hours=1))
RECOVERY_WINDOW = timedelta(hours=12)
MAX_COMPLETED = 100


class ArrivalCollector:
    """Complete observed Railinfo journeys from destination movement data."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: JourneyGuardianCoordinator,
        client: RailinfoClient,
        history: CheckHistory,
    ) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._client = client
        self._history = history
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY
        )
        self._pending: dict[str, dict[str, Any]] = {}
        self._completed: list[str] = []
        self._cancellers: dict[str, Callable[[], None]] = {}
        self._remove_listener: Callable[[], None] | None = None
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Restore pending and completed identities after restart."""
        stored = await self._store.async_load() or {}
        if not isinstance(stored, Mapping):
            return
        pending = stored.get("pending", {})
        if isinstance(pending, Mapping):
            self._pending = {
                str(key): dict(value)
                for key, value in pending.items()
                if isinstance(value, Mapping)
            }
        completed = stored.get("completed", [])
        if isinstance(completed, list):
            self._completed = [str(key) for key in completed[-MAX_COMPLETED:]]

    @callback
    def start(self) -> None:
        """Listen for live service matches and restore pending timers."""
        self._remove_listener = self._coordinator.async_add_listener(
            self._handle_coordinator_update
        )
        self._handle_coordinator_update()
        self._schedule_pending()

    @callback
    def stop(self) -> None:
        """Cancel listeners and timers."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
        for cancel in self._cancellers.values():
            cancel()
        self._cancellers.clear()

    @callback
    def _handle_coordinator_update(self) -> None:
        snapshot = self._coordinator.data
        if not _collectable(snapshot):
            return
        self._hass.async_create_task(
            self._async_register(snapshot),
            "journey_guardian register arrival collection",
        )

    async def _async_register(self, snapshot: JourneySnapshot) -> None:
        journey = snapshot.next_journey
        observation = snapshot.rail_observation
        if journey is None or journey.end is None or observation is None:
            return
        destination_code = observation.destination_code
        identity = observation.service_identity
        if destination_code is None or identity is None:
            return
        key = hashlib.sha256(
            f"{identity}|{destination_code}|{journey.start.isoformat()}".encode()
        ).hexdigest()[:24]
        async with self._lock:
            if key in self._completed or key in self._pending:
                return
            fingerprint = hashlib.sha256(
                (
                    f"{journey.start.isoformat()}|{journey.origin_name}|"
                    f"{journey.destination_confirmation}"
                ).encode()
            ).hexdigest()[:16]
            self._pending[key] = {
                "journey_fingerprint": fingerprint,
                "origin_code": journey.origin_code,
                "destination_code": destination_code,
                "service_identity": identity,
                "service_date": journey.start.date().isoformat(),
                "journey_date": journey.start.date().isoformat(),
                "scheduled_end": journey.end.isoformat(),
                "attempt": 0,
            }
            await self._async_save()
            self._schedule_pending()

    @callback
    def _schedule_pending(self) -> None:
        for cancel in self._cancellers.values():
            cancel()
        self._cancellers.clear()
        now = dt_util.now()
        for key, item in self._pending.items():
            try:
                attempt = int(item.get("attempt", 0))
                scheduled_end = datetime.fromisoformat(str(item["scheduled_end"]))
                point = scheduled_end + CHECK_OFFSETS[attempt]
            except (IndexError, KeyError, TypeError, ValueError):
                self._hass.async_create_task(
                    self._async_finish_unresolved(key, "arrival_evidence_invalid"),
                    "journey_guardian discard invalid arrival evidence",
                )
                continue
            if point > now:
                self._cancellers[key] = async_track_point_in_utc_time(
                    self._hass,
                    functools.partial(self._async_checkpoint, key=key),
                    point,
                )
            elif now - point <= RECOVERY_WINDOW:
                self._hass.async_create_task(
                    self._async_collect(key),
                    "journey_guardian recover destination arrival",
                )
            else:
                self._hass.async_create_task(
                    self._async_finish_unresolved(key, "arrival_evidence_expired"),
                    "journey_guardian expire destination arrival",
                )

    async def _async_checkpoint(self, _reached_at: datetime, key: str) -> None:
        await self._async_collect(key)

    async def _async_collect(self, key: str) -> None:
        finish_category = None
        async with self._lock:
            item = self._pending.get(key)
            if item is None:
                return
            try:
                result = await self._client.async_live_board(
                    str(item["destination_code"]), window_hours=12
                )
                arrival = _match_arrival(
                    result.payload,
                    expected_identity=str(item["service_identity"]),
                    service_date=date.fromisoformat(str(item["service_date"])),
                )
            except (ProviderBrokerError, KeyError, TypeError, ValueError) as err:
                _LOGGER.warning(
                    "Arrival collection failed with %s", type(err).__name__
                )
                arrival = None

            if arrival is not None:
                await self._history.async_record(
                    {
                        "checked_at": dt_util.now().isoformat(),
                        "journey_date": item.get("journey_date"),
                        "trigger": "railinfo_arrival",
                        "journey_fingerprint": item.get("journey_fingerprint"),
                        "origin_code": item.get("origin_code"),
                        "destination_code": item.get("destination_code"),
                        "operation": "destination_arrivals",
                        "stage": "complete",
                        "outcome": "success",
                        "status": (
                            "delayed"
                            if arrival["arrival_delay_minutes"] > 0
                            else "completed"
                        ),
                        "scheduled_arrival": arrival["scheduled_arrival"],
                        "actual_arrival": arrival["actual_arrival"],
                        "arrival_delay_minutes": arrival["arrival_delay_minutes"],
                        "completion_status": "completed",
                        "cancelled": False,
                        "evidence_source": "railinfo",
                        "evidence_observed_at": result.observed_at.isoformat(),
                        "evidence_freshness": result.freshness,
                        "service_identity": item.get("service_identity"),
                    }
                )
                await self._async_complete(key)
                return

            item["attempt"] = int(item.get("attempt", 0)) + 1
            if item["attempt"] >= len(CHECK_OFFSETS):
                finish_category = "arrival_not_found"
            else:
                await self._async_save()
                self._schedule_pending()
        if finish_category is not None:
            await self._async_finish_unresolved(key, finish_category)

    async def _async_finish_unresolved(self, key: str, category: str) -> None:
        async with self._lock:
            item = self._pending.get(key)
            if item is None:
                return
            await self._history.async_record(
                {
                    "checked_at": dt_util.now().isoformat(),
                    "journey_date": item.get("journey_date"),
                    "trigger": "railinfo_arrival",
                    "journey_fingerprint": item.get("journey_fingerprint"),
                    "origin_code": item.get("origin_code"),
                    "destination_code": item.get("destination_code"),
                    "operation": "destination_arrivals",
                    "stage": "complete",
                    "outcome": "failed",
                    "error_category": category,
                    "status": "unresolved",
                    "completion_status": "unresolved",
                    "evidence_source": "railinfo",
                    "service_identity": item.get("service_identity"),
                }
            )
            await self._async_complete(key)

    async def _async_complete(self, key: str) -> None:
        self._pending.pop(key, None)
        self._completed.append(key)
        self._completed = self._completed[-MAX_COMPLETED:]
        cancel = self._cancellers.pop(key, None)
        if cancel is not None:
            cancel()
        await self._async_save()

    async def _async_save(self) -> None:
        await self._store.async_save(
            {"pending": self._pending, "completed": self._completed}
        )

    def diagnostics(self) -> dict[str, Any]:
        """Expose only bounded, privacy-safe collector state."""
        return {
            "pending_count": len(self._pending),
            "completed_count": len(self._completed),
            "pending": [
                {
                    "journey_fingerprint": item.get("journey_fingerprint"),
                    "origin_code": item.get("origin_code"),
                    "destination_code": item.get("destination_code"),
                    "scheduled_end": item.get("scheduled_end"),
                    "attempt": item.get("attempt"),
                }
                for item in self._pending.values()
            ],
        }


def _collectable(snapshot: JourneySnapshot) -> bool:
    journey = snapshot.next_journey
    observation = snapshot.rail_observation
    return bool(
        journey is not None
        and journey.end is not None
        and observation is not None
        and observation.source == "railinfo"
        and observation.service_identity
        and observation.destination_code
        and not observation.cancelled
        and not snapshot.simulation_active
    )


def _match_arrival(
    payload: Mapping[str, Any], *, expected_identity: str, service_date: date
) -> dict[str, Any] | None:
    """Match one actual arrival using the departure service identity."""
    movements = payload.get("movements")
    if not isinstance(movements, list):
        raise ValueError("arrival_response_malformed")
    for movement in movements:
        if not isinstance(movement, Mapping):
            continue
        if str(movement.get("event_type", "")).upper() != "ARRIVAL":
            continue
        train_id = str(movement.get("train_id") or "").strip()
        # TRUST train IDs embed the four-character signalling headcode at
        # positions 3-6; Railinfo journey legs expose that same headcode.
        headcode = train_id[2:6] if len(train_id) >= 6 else ""
        if (
            not headcode
            or service_identity(headcode, service_date) != expected_identity
        ):
            continue
        try:
            scheduled = datetime.fromisoformat(str(movement["gbtt_ts"]))
            actual = datetime.fromisoformat(str(movement["actual_ts"]))
        except (KeyError, TypeError, ValueError):
            continue
        delay = max(0, round((actual - scheduled).total_seconds() / 60))
        return {
            "scheduled_arrival": scheduled.isoformat(),
            "actual_arrival": actual.isoformat(),
            "arrival_delay_minutes": delay,
        }
    return None
