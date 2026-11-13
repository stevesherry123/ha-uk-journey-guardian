"""Keep only the latest successful calendar read and latest failure."""

from collections.abc import Mapping
from datetime import datetime
from hashlib import sha256

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

ERRORS = {
    "entity_unavailable",
    "service_unavailable",
    "timeout",
    "invalid_response",
    "service_call_failed",
    "review_failed",
}


class CalendarReadHistory:
    """Persist timestamps and fixed error categories for one calendar."""

    def __init__(self, hass: HomeAssistant, scope: str) -> None:
        key = sha256(scope.encode()).hexdigest()[:24]
        self._store: Store[dict] = Store(
            hass, 1, f"journey_guardian.calendar_reads.{key}"
        )
        self.last_success: datetime | None = None
        self.last_failure: datetime | None = None
        self.last_error: str | None = None

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if not isinstance(data, Mapping):
            return
        self.last_success = _timestamp(data.get("last_success_at"))
        category = data.get("last_error")
        if isinstance(category, str) and category in ERRORS:
            self.last_failure = _timestamp(data.get("last_failure_at"))
            if self.last_failure is not None:
                self.last_error = category

    def record(self, checked_at: datetime, error: str | None) -> None:
        if error is None:
            self.last_success = checked_at
        else:
            self.last_failure = checked_at
            self.last_error = error if error in ERRORS else "review_failed"
        self._store.async_delay_save(self.as_dict, 5)

    def as_dict(self) -> dict:
        return {
            "last_success_at": self.last_success.isoformat()
            if self.last_success
            else None,
            "last_failure_at": self.last_failure.isoformat()
            if self.last_failure
            else None,
            "last_error": self.last_error,
        }


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        return None
    return result if result.utcoffset() is not None else None
