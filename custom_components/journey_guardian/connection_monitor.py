"""Opt-in bounded monitoring for explicitly confirmed Railinfo connections."""

from __future__ import annotations

import hashlib
from asyncio import Lock
from datetime import UTC, datetime, timedelta

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .connection_evidence import EvidenceConnectionAssessment
from .connection_review import async_review_connection

MAX_DAILY_CHECKS = 8
MIN_SPACING = timedelta(minutes=5)
CATCHUP = timedelta(minutes=2)


class ConnectionCheckLedger:
    """Persist check claims before acquisition; failed writes cannot spend work."""

    def __init__(self, storage, *, scope: str):
        self._storage = storage
        self._scope = scope
        self._state = {"day": "", "keys": [], "last": None}
        self._loaded = False
        self._lock = Lock()

    async def async_load(self):
        self._loaded = False
        data = await self._storage.async_load()
        if data is not None:
            if (
                not isinstance(data, dict)
                or type(data.get("schema")) is not int
                or data.get("schema") != 1
                or data.get("scope") != self._scope
                or not isinstance(data.get("keys"), list)
                or len(data["keys"]) > MAX_DAILY_CHECKS
                or not isinstance(data.get("day"), str)
            ):
                raise ValueError("invalid_connection_check_ledger")
            datetime.strptime(data["day"], "%Y-%m-%d")
            for key in data["keys"]:
                if (
                    not isinstance(key, str)
                    or len(key) != 64
                    or any(char not in "0123456789abcdef" for char in key)
                ):
                    raise ValueError("invalid_checkpoint_key")
            if data.get("last") is not None:
                last = datetime.fromisoformat(data["last"])
                if last.utcoffset() is None:
                    raise ValueError("timezone_required")
            self._state = {key: data.get(key) for key in ("day", "keys", "last")}
        self._loaded = True

    def eligible(self, key, now):
        if not self._loaded:
            return False
        day = dt_util.as_local(now).date().isoformat()
        if self._state["day"] > day:
            return False
        if self._state["day"] == day and (
            key in self._state["keys"] or len(self._state["keys"]) >= MAX_DAILY_CHECKS
        ):
            return False
        last = self._state["last"]
        return last is None or (
            now.astimezone(UTC) - datetime.fromisoformat(last).astimezone(UTC)
            >= MIN_SPACING
        )

    async def async_claim(self, key, now):
        async with self._lock:
            if not self.eligible(key, now):
                return False
            day = dt_util.as_local(now).date().isoformat()
            keys = self._state["keys"] if day == self._state["day"] else []
            proposed = {"day": day, "keys": [*keys, key], "last": now.isoformat()}
            try:
                await self._storage.async_save(
                    {"schema": 1, "scope": self._scope, **proposed}
                )
            except Exception:
                self._loaded = False
                raise
            self._state = proposed
            return True


def checkpoint_key(pair, point):
    return hashlib.sha256(
        f"{pair[0]}|{pair[1]}|{point.astimezone(UTC).isoformat()}".encode()
    ).hexdigest()


class ConnectionMonitor:
    """One timer, sparse checkpoints, no operational alerts or selected-leg edits."""

    def __init__(self, hass, coordinator, ledger, *, enabled=False, alerts=None):
        self._hass, self._coordinator, self._ledger = hass, coordinator, ledger
        self._alerts = alerts
        self._enabled = enabled
        self._cancel = self._remove = None
        self._stopped = True
        self._busy = False

    @callback
    def start(self):
        if not self._enabled or not self._stopped:
            return
        self._stopped = False
        self._remove = self._coordinator.async_add_listener(self._schedule)
        self._schedule()

    @callback
    def stop(self):
        self._stopped = True
        if self._cancel:
            self._cancel()
            self._cancel = None
        if self._remove:
            self._remove()
            self._remove = None
        self._coordinator.next_connection_check_at = None

    def _targets(self, now):
        snapshot = self._coordinator.data
        if (
            self._stopped
            or snapshot is None
            or snapshot.simulation_active
            or snapshot.error
            or self._coordinator.engine._live_rail_provider != "railinfo"
        ):
            return []
        return [
            pair
            for pair in self._coordinator.connection_dashboard(now)["connections"]
            if pair["confirmed"] and pair.get("can_monitor", pair["can_confirm"])
        ]

    @callback
    def _schedule(self):
        if self._cancel:
            self._cancel()
            self._cancel = None
        self._coordinator.next_connection_check_at = None
        if self._busy:
            return
        now, points = dt_util.now(), []
        for pair in self._targets(now):
            identity = pair["inbound_id"], pair["outbound_id"]
            arrival = datetime.fromisoformat(pair["inbound_arrival"])
            departure = datetime.fromisoformat(pair["outbound_departure"])
            times = {arrival + timedelta(minutes=offset) for offset in (-15, -5, 5)}
            times.update(departure + timedelta(minutes=offset) for offset in (-2, 5))
            for point in times:
                if (
                    not arrival - timedelta(minutes=20)
                    <= point
                    <= departure + timedelta(minutes=10)
                ):
                    continue
                key = checkpoint_key(identity, point)
                if point >= now - CATCHUP and self._ledger.eligible(
                    key, max(now, point)
                ):
                    points.append((point, identity))
        if not points:
            return
        due = [item for item in points if item[0] <= now]
        point, pair = max(due) if due else min(points)
        fire_at = max(now, point)
        self._coordinator.next_connection_check_at = fire_at

        async def reached(_now):
            await self._run(pair, point)

        self._cancel = async_track_point_in_utc_time(self._hass, reached, fire_at)

    async def _run(self, pair, point):
        now = dt_util.now()
        targets = {
            (item["inbound_id"], item["outbound_id"]): item
            for item in self._targets(now)
        }
        if self._busy or pair not in targets or now - point > CATCHUP:
            return
        self._busy = True
        try:
            if not await self._ledger.async_claim(checkpoint_key(pair, point), now):
                return
            inbound, outbound = self._coordinator.travel_plan.connection_pair(
                *pair, now=now, monitoring=True
            )
            result = await async_review_connection(
                self._coordinator.engine,
                inbound,
                outbound,
                minimum_minutes=targets[pair]["allowance_minutes"],
                now=now,
                still_current=lambda: (
                    pair
                    in {
                        (item["inbound_id"], item["outbound_id"])
                        for item in self._targets(dt_util.now())
                    }
                ),
            )
            if pair in {
                (item["inbound_id"], item["outbound_id"])
                for item in self._targets(dt_util.now())
            }:
                self._coordinator.connection_assessments[pair] = result
                if self._alerts is not None:
                    try:
                        await self._alerts.async_process(
                            pair, result[0], result[1], station=inbound.destination,
                            expires_at=outbound.expiry,
                            is_current=lambda: any(
                                (item["inbound_id"], item["outbound_id"]) == pair
                                and item["allowance_minutes"]
                                == result[0].minimum_minutes
                                for item in self._targets(dt_util.now())
                            ),
                        )
                    except Exception:
                        self._coordinator.connection_alert_error = True
        except Exception:  # Provider/storage details must not leak into public state.
            if pair not in {
                (item["inbound_id"], item["outbound_id"])
                for item in self._targets(dt_util.now())
            }:
                return
            self._coordinator.connection_assessments[pair] = (
                EvidenceConnectionAssessment(
                    "unknown",
                    "connection_check_unavailable",
                    dt_util.now(),
                    targets[pair]["allowance_minutes"],
                ),
                None,
            )
        finally:
            self._busy = False
            self._schedule()
            self._coordinator.async_update_listeners()
