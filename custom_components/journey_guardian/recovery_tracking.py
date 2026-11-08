"""Durable replacement tracking, separate from calendar bookings."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta

from .recovery import RecoveryRoute, _station, _utc


@dataclass(frozen=True, slots=True)
class TrackedRecoveryLeg:
    origin: str
    destination: str
    service_identity: str
    scheduled_departure: str
    scheduled_arrival: str
    approved_departure: str
    approved_arrival: str

    def validate(self) -> None:
        _station(self.origin)
        _station(self.destination)
        if (
            self.origin == self.destination
            or not isinstance(self.service_identity, str)
            or not 1 <= len(self.service_identity) <= 128
        ):
            raise ValueError("invalid_replacement_leg")
        if self.instant("scheduled_arrival") <= self.instant(
            "scheduled_departure"
        ) or self.instant("approved_arrival") <= self.instant("approved_departure"):
            raise ValueError("invalid_replacement_times")

    def instant(self, field: str) -> datetime:
        return _utc(datetime.fromisoformat(getattr(self, field)))


@dataclass(frozen=True, slots=True)
class TrackedRecovery:
    option_id: str
    revision: str
    affected_booking_ids: tuple[str, ...]
    approved_at: str
    legs: tuple[TrackedRecoveryLeg, ...]
    leg_index: int = 0
    stopped: bool = False

    @property
    def tracking_id(self) -> str:
        return hashlib.sha256(
            f"{self.option_id}|{self.approved_at}".encode()
        ).hexdigest()

    @property
    def finished(self) -> bool:
        return self.leg_index == len(self.legs)

    @property
    def expires_at(self) -> datetime:
        return self.legs[-1].instant("approved_arrival") + timedelta(hours=8)

    def validate(self) -> None:
        ids = (self.option_id, self.revision, *self.affected_booking_ids)
        if (
            not 1 <= len(self.legs) <= 2
            or not 1 <= len(self.affected_booking_ids) <= 64
            or type(self.stopped) is not bool
            or type(self.leg_index) is not int
            or not 0 <= self.leg_index <= len(self.legs)
            or any(
                not isinstance(key, str)
                or len(key) != 64
                or any(c not in "0123456789abcdef" for c in key)
                for key in ids
            )
        ):
            raise ValueError("invalid_replacement")
        approved_at = _utc(datetime.fromisoformat(self.approved_at))
        for leg in self.legs:
            leg.validate()
            if (
                leg.instant("approved_departure") <= approved_at
                or leg.instant("approved_arrival") > approved_at + timedelta(hours=10)
            ):
                raise ValueError("invalid_approval_time")
        for first, second in zip(self.legs, self.legs[1:], strict=False):
            if first.destination != second.origin or first.instant(
                "approved_arrival"
            ) > second.instant("approved_departure"):
                raise ValueError("disconnected_replacement")


class RecoveryTrackingStore:
    """Persist one explicitly approved route and its user-confirmed progress."""

    def __init__(self, storage):
        self._storage = storage
        self._lock = asyncio.Lock()
        self.record: TrackedRecovery | None = None
        self.available = False

    async def async_load(self, now: datetime) -> None:
        raw = await self._storage.async_load()
        if raw is not None:
            if not isinstance(raw, dict) or raw.get("schema") != 1:
                raise ValueError("invalid_replacement_store")
            payload = dict(raw["record"])
            if len(payload["legs"]) > 2 or len(payload["affected_booking_ids"]) > 64:
                raise ValueError("replacement_store_limit")
            payload["legs"] = tuple(
                TrackedRecoveryLeg(**leg) for leg in payload["legs"]
            )
            payload["affected_booking_ids"] = tuple(payload["affected_booking_ids"])
            record = TrackedRecovery(**payload)
            record.validate()
            if _utc(datetime.fromisoformat(record.approved_at)) > now:
                raise ValueError("future_approval")
            if now < record.expires_at:
                self.record = record
        self.available = True

    async def _save(self, record: TrackedRecovery) -> None:
        await self._storage.async_save({"schema": 1, "record": asdict(record)})
        self.record = record

    async def async_approve(
        self, route: RecoveryRoute, affected_ids: tuple[str, ...], *, now: datetime
    ) -> None:
        async with self._lock:
            if not self.available or now >= route.valid_until:
                raise ValueError("approval_unavailable")
            if (
                self.record
                and not self.record.finished
                and not self.record.stopped
                and now < self.record.expires_at
            ):
                if (self.record.option_id, self.record.revision) == (
                    route.option_id,
                    route.revision,
                ):
                    return
                raise ValueError("replacement_already_active")
            record = TrackedRecovery(
                route.option_id,
                route.revision,
                affected_ids,
                now.isoformat(),
                tuple(
                    TrackedRecoveryLeg(
                        leg.origin_code,
                        leg.destination_code,
                        leg.departure.service.identity,
                        leg.scheduled_departure.isoformat(),
                        leg.scheduled_arrival.isoformat(),
                        leg.departure.event_at.isoformat(),
                        leg.arrival.event_at.isoformat(),
                    )
                    for leg in route.legs
                ),
            )
            record.validate()
            await self._save(record)

    async def async_confirm_arrival(
        self, tracking_id: str, leg_index: int, *, now: datetime
    ) -> None:
        async with self._lock:
            record = self.record
            if (
                not self.available
                or record is None
                or record.finished
                or record.stopped
                or record.tracking_id != tracking_id
                or record.leg_index != leg_index
                or now >= record.expires_at
                or now < record.legs[leg_index].instant("approved_departure")
            ):
                raise ValueError("current_replacement_leg_required")
            await self._save(replace(record, leg_index=leg_index + 1))

    async def async_stop(self, tracking_id: str) -> None:
        async with self._lock:
            record = self.record
            if (
                not self.available
                or record is None
                or record.tracking_id != tracking_id
            ):
                raise ValueError("current_replacement_required")
            if not record.finished and not record.stopped:
                await self._save(replace(record, stopped=True))
