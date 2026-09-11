"""Provider-free nightly review of saved Journey Guardian evidence."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .check_history import CheckHistory


class EndOfDayReview:
    """Summarise the local day's rail evidence without making provider calls."""

    def __init__(self, hass: HomeAssistant, history: CheckHistory) -> None:
        self._hass = hass
        self._history = history
        self._cancel = None

    @callback
    def start(self) -> None:
        self._schedule()

    @callback
    def stop(self) -> None:
        if self._cancel:
            self._cancel()
            self._cancel = None

    @callback
    def _schedule(self) -> None:
        now = dt_util.now()
        point = datetime.combine(now.date(), time(23, 30), tzinfo=now.tzinfo)
        if point <= now:
            point += timedelta(days=1)
        self._cancel = async_track_point_in_utc_time(self._hass, self._run, point)

    async def _run(self, _now: datetime) -> None:
        today = dt_util.now().date().isoformat()
        groups: dict[str, list[dict]] = defaultdict(list)
        for record in self._history.records():
            if str(record.get("checked_at", "")).startswith(today):
                groups[str(record.get("journey_fingerprint", "unknown"))].append(record)
        if groups:
            unresolved = 0
            delays = 0
            for records in groups.values():
                latest = records[-1]
                if latest.get("outcome") != "success":
                    unresolved += 1
                if latest.get("status") == "delayed":
                    delays += 1
            message = (
                f"Journey Guardian nightly review: {len(groups)} journey(s), "
                f"{delays} delayed, {unresolved} unresolved. "
                "This summary used saved local evidence and made no rail API calls."
            )
            persistent_notification.async_create(
                self._hass, message, title="UK Journey Guardian nightly review",
                notification_id="journey_guardian_end_of_day",
            )
        self._schedule()
