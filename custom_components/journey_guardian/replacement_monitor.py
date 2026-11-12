"""Schedule sparse checks for the current approved replacement train."""

from datetime import timedelta

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .connection_monitor import CATCHUP, checkpoint_key


class ReplacementMonitor:
    """Share the connection budget and persist a claim before each provider check."""

    def __init__(self, hass, runtime, ledger):
        self.hass = hass
        self.runtime = runtime
        self.ledger = ledger
        self._cancel = None
        self._unsubscribe = None
        self._running = False

    def start(self):
        self._unsubscribe = self.runtime.coordinator.async_add_listener(self._schedule)
        self._schedule()

    def stop(self):
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._cancel_timer()

    def _cancel_timer(self):
        if self._cancel is not None:
            self._cancel()
            self._cancel = None
        self.runtime.next_tracking_check_at = None

    def _targets(self, now):
        record = self.runtime.active_tracking(now)
        if record is None:
            return []
        leg = record.legs[record.leg_index]
        return sorted(
            (
                leg.instant(field) - lead,
                record.tracking_id,
                record.leg_index,
            )
            for field, lead in (
                ("approved_departure", timedelta(minutes=5)),
                ("approved_arrival", timedelta(minutes=10)),
            )
        )

    @staticmethod
    def _key(point, tracking_id, index):
        return checkpoint_key((tracking_id, f"replacement_leg_{index}"), point)

    @callback
    def _schedule(self):
        self._cancel_timer()
        if self._unsubscribe is None or self._running:
            return
        now = dt_util.utcnow()
        for point, tracking_id, index in self._targets(now):
            when = max(now + timedelta(seconds=1), point)
            if when > point + CATCHUP or not self.ledger.eligible(
                self._key(point, tracking_id, index), when
            ):
                continue
            self.runtime.next_tracking_check_at = when

            async def run(_now, target=(point, tracking_id, index)):
                await self._run(*target)

            self._cancel = async_track_point_in_utc_time(self.hass, run, when)
            return

    async def _run(self, point, tracking_id, index):
        if self._unsubscribe is None or self._running:
            return
        self._running = True
        self._cancel = None
        self.runtime.next_tracking_check_at = None
        try:
            now = dt_util.utcnow()
            if not point <= now <= point + CATCHUP or (
                point,
                tracking_id,
                index,
            ) not in self._targets(now):
                return
            if not await self.ledger.async_claim(
                self._key(point, tracking_id, index), now
            ):
                return
            if self._unsubscribe is not None:
                await self.runtime.async_check_tracking(
                    tracking_id=tracking_id, leg_index=index
                )
        except ValueError, OSError, HomeAssistantError:
            # The ledger disables automatic claims after a failed save.
            return
        finally:
            self._running = False
            self._schedule()
            if self._unsubscribe is not None:
                self.runtime.coordinator.async_update_listeners()
