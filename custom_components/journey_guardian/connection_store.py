"""Versioned confirmation persistence, awaiting coordinator integration."""

from __future__ import annotations

from asyncio import Lock
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol


class Storage(Protocol):
    """The async storage interface supplied by Home Assistant's Store."""

    async def async_load(self) -> Any:
        """Load a stored document."""

    async def async_save(self, data: dict[str, Any]) -> None:
        """Durably save a document."""


def _aware(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("timezone_required")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ConfirmedConnection:
    """Exact booking identities include revisions; templates cannot confirm."""

    inbound_id: str
    outbound_id: str
    confirmed_at: str
    expires_at: str
    override_minutes: int | None = None

    def validate(self) -> None:
        for identity in (self.inbound_id, self.outbound_id):
            if (
                not isinstance(identity, str)
                or len(identity) != 64
                or any(c not in "0123456789abcdef" for c in identity)
            ):
                raise ValueError("invalid_booking_identity")
        if self.inbound_id == self.outbound_id:
            raise ValueError("distinct_bookings_required")
        start = _aware(datetime.fromisoformat(self.confirmed_at))
        end = _aware(datetime.fromisoformat(self.expires_at))
        if end <= start:
            raise ValueError("invalid_confirmation_expiry")
        value = self.override_minutes
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("invalid_transfer_allowance")


class ConnectionConfirmationStore:
    """Commit memory only after successful save; refuse writes before load."""

    def __init__(self, storage: Storage, *, scope: str) -> None:
        self._storage = storage
        self._scope = scope
        self._records: dict[tuple[str, str], ConfirmedConnection] = {}
        self._lock = Lock()
        self._loaded = False

    async def async_load(self, now: datetime) -> None:
        async with self._lock:
            self._loaded = False
            self._records = {}
            now = _aware(now)
            raw = await self._storage.async_load()
            records = {}
            if raw is not None:
                if (
                    not isinstance(raw, Mapping)
                    or type(raw.get("schema")) is not int
                    or raw.get("schema") != 1
                    or raw.get("scope") != self._scope
                    or not isinstance(raw.get("records"), list)
                    or len(raw["records"]) > 64
                ):
                    raise ValueError("invalid_confirmation_store")
                for item in raw["records"]:
                    record = ConfirmedConnection(**item)
                    record.validate()
                    if _aware(datetime.fromisoformat(record.confirmed_at)) > now:
                        raise ValueError("future_confirmation")
                    if _aware(datetime.fromisoformat(record.expires_at)) > now:
                        records[(record.inbound_id, record.outbound_id)] = record
            self._records = records
            self._loaded = True

    def get(
        self, inbound_id: str, outbound_id: str, *, now: datetime
    ) -> ConfirmedConnection | None:
        now = _aware(now)
        record = self._records.get((inbound_id, outbound_id))
        if record and _aware(datetime.fromisoformat(record.expires_at)) > now:
            return record
        return None

    def active(self, *, now: datetime) -> tuple[ConfirmedConnection, ...]:
        """Return unexpired explicit confirmations, never suggestion templates."""
        now = _aware(now)
        return tuple(record for record in self._records.values()
                     if _aware(datetime.fromisoformat(record.expires_at)) > now)

    async def async_confirm(
        self, record: ConfirmedConnection, *, now: datetime
    ) -> None:
        async with self._lock:
            if not self._loaded:
                raise ValueError("confirmation_store_not_loaded")
            now = _aware(now)
            record.validate()
            if not (
                _aware(datetime.fromisoformat(record.confirmed_at)) <= now
                < _aware(datetime.fromisoformat(record.expires_at))
            ):
                raise ValueError("confirmation_not_current")
            proposed = {
                key: value for key, value in self._records.items()
                if _aware(datetime.fromisoformat(value.expires_at)) > now
            }
            proposed[(record.inbound_id, record.outbound_id)] = record
            if len(proposed) > 64:
                raise ValueError("confirmation_capacity_reached")
            await self._storage.async_save({
                "schema": 1, "scope": self._scope,
                "records": [asdict(value) for value in proposed.values()],
            })
            self._records = proposed

    async def async_revoke(self, inbound_id: str, outbound_id: str) -> None:
        """Persist revocation before removing confirmation from memory."""
        async with self._lock:
            if not self._loaded:
                raise ValueError("confirmation_store_not_loaded")
            proposed = dict(self._records)
            proposed.pop((inbound_id, outbound_id), None)
            await self._storage.async_save({
                "schema": 1, "scope": self._scope,
                "records": [asdict(value) for value in proposed.values()],
            })
            self._records = proposed
