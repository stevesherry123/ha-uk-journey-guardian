"""Bounded, privacy-safe history of live rail checks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

STORAGE_VERSION = 1
STORAGE_KEY = "journey_guardian.check_history"
MAX_RECORDS = 20


class CheckHistory:
    """Persist recent check outcomes across coordinator refreshes and restarts."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY
        )
        self._records: list[dict[str, Any]] = []

    async def async_load(self) -> None:
        """Restore only well-formed, bounded records."""
        loaded = await self._store.async_load() or {}
        records = loaded.get("records", []) if isinstance(loaded, Mapping) else []
        if isinstance(records, list):
            self._records = [
                dict(record) for record in records[-MAX_RECORDS:]
                if isinstance(record, Mapping)
            ]

    async def async_record(self, record: Mapping[str, Any]) -> None:
        """Append a sanitized record and persist it immediately."""
        allowed = {
            "checked_at", "trigger", "journey_fingerprint", "origin_code",
            "destination_code", "operation", "stage", "outcome", "error_category",
            "schedule_offset_minutes", "match_quality", "calls_used", "status",
        }
        self._records.append({key: record.get(key) for key in allowed})
        self._records = self._records[-MAX_RECORDS:]
        await self._store.async_save({"records": self._records})

    def records(self) -> list[dict[str, Any]]:
        """Return defensive copies of the retained records."""
        return [dict(record) for record in self._records]
