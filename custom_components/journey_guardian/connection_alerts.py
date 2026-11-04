"""Durable, bounded connection warning transitions and guarded delivery."""

from __future__ import annotations

import hashlib
from asyncio import Lock
from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.util import dt as dt_util

UPDATE_MINUTES = 5
RECOVERY_MARGIN = 2
MIN_ALERT_SPACING = timedelta(minutes=5)
MAX_RECORDS = 64
OUTCOMES = {
    "claimed",
    "announcement_engine",
    "persistent_notification",
    "suppressed",
    "failed",
}


def _instant(value):
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("timezone_required")
    return parsed


def pair_key(pair):
    return hashlib.sha256(f"{pair[0]}|{pair[1]}".encode()).hexdigest()


class ConnectionAlertLedger:
    """Claim before delivery; ambiguous hand-offs are never blindly replayed."""

    def __init__(self, storage, *, scope):
        self._storage, self._scope = storage, scope
        self._records = {}
        self._loaded = False
        self._lock = Lock()

    @property
    def available(self):
        return self._loaded

    async def async_load(self, now):
        self._loaded = False
        data = await self._storage.async_load()
        records = {}
        if data is not None:
            if (
                not isinstance(data, dict)
                or type(data.get("schema")) is not int
                or data["schema"] != 1
                or data.get("scope") != self._scope
                or not isinstance(data.get("records"), dict)
                or len(data["records"]) > MAX_RECORDS
            ):
                raise ValueError("invalid_connection_alert_store")
            for key, record in data["records"].items():
                if (
                    not isinstance(key, str)
                    or len(key) != 64
                    or any(char not in "0123456789abcdef" for char in key)
                    or not isinstance(record, dict)
                    or record.get("state") not in ("at_risk", "viable")
                    or record.get("kind") not in ("risk", "update", "recovered")
                    or record.get("delivery") not in OUTCOMES
                    or type(record.get("available")) is not int
                    or type(record.get("minimum")) is not int
                    or not 0 <= record["minimum"] <= 1440
                    or type(record.get("generation")) is not int
                    or record["generation"] < 1
                ):
                    raise ValueError("invalid_connection_alert_record")
                if _instant(record["claimed_at"]) > now:
                    raise ValueError("future_alert_claim")
                if _instant(record["expires_at"]) > now:
                    records[key] = dict(record)
        self._records, self._loaded = records, True

    async def _save(self, proposed):
        try:
            await self._storage.async_save(
                {
                    "schema": 1,
                    "scope": self._scope,
                    "records": proposed,
                }
            )
        except Exception:
            self._loaded = False
            raise
        self._records = proposed

    async def async_claim(self, pair, assessment, *, now, expires_at):
        async with self._lock:
            if not self._loaded:
                raise ValueError("connection_alert_storage_unavailable")
            if assessment.classification not in ("at_risk", "viable"):
                return None
            if expires_at <= now or assessment.minutes_available is None:
                return None
            key = pair_key(pair)
            previous = self._records.get(key)
            if previous and _instant(previous["expires_at"]) <= now:
                previous = None
            kind = None
            if assessment.classification == "at_risk":
                if previous is None or previous["state"] == "viable":
                    kind = "risk"
                elif (
                    abs(assessment.minutes_available - previous["available"])
                    >= UPDATE_MINUTES
                    or assessment.minimum_minutes != previous["minimum"]
                ):
                    kind = "update"
            elif (
                previous
                and previous["state"] == "at_risk"
                and assessment.margin_minutes is not None
                and assessment.margin_minutes >= RECOVERY_MARGIN
            ):
                kind = "recovered"
            if kind is None or (
                previous and now - _instant(previous["claimed_at"]) < MIN_ALERT_SPACING
            ):
                return None
            proposed = {
                key: value
                for key, value in self._records.items()
                if _instant(value["expires_at"]) > now
            }
            if key not in proposed and len(proposed) >= MAX_RECORDS:
                raise ValueError("connection_alert_capacity")
            record = {
                "state": assessment.classification,
                "kind": kind,
                "available": assessment.minutes_available,
                "minimum": assessment.minimum_minutes,
                "claimed_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "generation": previous["generation"] + 1 if previous else 1,
                "delivery": "claimed",
            }
            proposed[key] = record
            await self._save(proposed)
            return key, record["generation"], kind

    async def async_record_delivery(self, claim, outcome):
        async with self._lock:
            key, generation, _kind = claim
            if not self._loaded or outcome not in OUTCOMES:
                raise ValueError("invalid_alert_delivery")
            current = self._records.get(key)
            if current is None or current["generation"] != generation:
                return
            proposed = deepcopy(self._records)
            proposed[key]["delivery"] = outcome
            await self._save(proposed)

    def status(self, pair, *, now):
        record = self._records.get(pair_key(pair))
        if record is None or _instant(record["expires_at"]) <= now:
            return None
        return {
            "kind": record["kind"],
            "recorded_at": record["claimed_at"],
            "delivery": record["delivery"],
            "receipt_confirmed": False,
        }


def connection_message(station, assessment, kind):
    """Describe risk without claiming a missed train or guaranteed connection."""
    station = " ".join(station.split())[:64]
    available, required = assessment.minutes_available, assessment.minimum_minutes
    if kind == "recovered":
        return (
            f"Connection margin at {station} has recovered: "
            f"{available} minutes available; {required} required. Check live updates."
        )
    timing = (
        f"arrival is {-available} minutes after onward departure"
        if available < 0
        else f"{available} minutes available to change"
    )
    detail = ""
    if assessment.inbound_event_at and assessment.outbound_event_at:
        zone = ZoneInfo("Europe/London")
        incoming = assessment.inbound_event_at.astimezone(zone)
        onward = assessment.outbound_event_at.astimezone(zone)
        pattern = "%H:%M %Z" if incoming.date() == onward.date() else "%d %b %H:%M %Z"
        detail = (
            f" Arrival {incoming.strftime(pattern)}, onward {onward.strftime(pattern)}."
        )
    return f"Connection at {station} is at risk: {timing}; {required} required.{detail}"


class ConnectionAlertController:
    """Only fresh current confirmations can enter the existing delivery route."""

    def __init__(self, ledger, scheduler):
        self.ledger, self._scheduler = ledger, scheduler

    async def async_process(
        self, pair, assessment, valid_until, *, station, expires_at, is_current
    ):
        now = dt_util.now()
        if (
            not self._scheduler.connection_notices_enabled
            or not is_current()
            or valid_until is None
            or now > valid_until
            or assessment.assessed_at > now
            or assessment.classification not in ("at_risk", "viable")
        ):
            return
        claim = await self.ledger.async_claim(
            pair, assessment, now=now, expires_at=expires_at
        )
        if claim is None:
            return

        def guard():
            return is_current() and dt_util.now() <= valid_until

        outcome = await self._scheduler.async_connection_notice(
            connection_message(station, assessment, claim[2]),
            notification_id=f"journey_guardian_connection_{claim[0][:24]}",
            kind=claim[2],
            is_current=guard,
        )
        await self.ledger.async_record_delivery(claim, outcome)
