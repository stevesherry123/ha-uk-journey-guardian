"""Journey Guardian update coordinator."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DEFAULT_UPDATE_INTERVAL, NAME
from .engine import JourneyGuardianEngine
from .live_evidence import LiveEvidenceStore
from .models import JourneySnapshot
from .phase import calculate_operational_phase

_LOGGER = logging.getLogger(__name__)


class JourneyGuardianCoordinator(DataUpdateCoordinator[JourneySnapshot]):
    """Coordinate calendar reviews and entity updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        engine: JourneyGuardianEngine,
        *,
        calendar_entity: str = "",
        calendar_refresh_interval_minutes: int = 0,
    ) -> None:
        """Initialize the coordinator."""
        self.engine = engine
        self._calendar_entity = calendar_entity
        self.calendar_source_refresh_interval_minutes = max(
            0, calendar_refresh_interval_minutes
        )
        self._calendar_source_refresh_interval = (
            timedelta(minutes=self.calendar_source_refresh_interval_minutes)
            if self.calendar_source_refresh_interval_minutes
            else None
        )
        self._last_calendar_source_refresh_attempt_at: datetime | None = None
        self.last_calendar_source_refresh_at: datetime | None = None
        self.last_calendar_source_refresh_error: str | None = None
        self.last_live_check_at: datetime | None = None
        self.next_live_check_at: datetime | None = None
        self.last_station_access_test_at: datetime | None = None
        self.next_station_access_check_at: datetime | None = None
        self.last_notification: str | None = None
        self.last_notification_at: datetime | None = None
        self._last_live_snapshot: JourneySnapshot | None = None
        self.live_evidence = LiveEvidenceStore(hass)
        super().__init__(
            hass,
            logger=_LOGGER,
            config_entry=entry,
            name=NAME,
            update_interval=DEFAULT_UPDATE_INTERVAL,
            always_update=False,
        )

    async def _async_update_data(self) -> JourneySnapshot:
        """Return the latest normalized journey state."""
        await self.async_refresh_calendar_source()
        snapshot = await self.engine.async_review()
        previous = self._last_live_snapshot
        if previous is None:
            observation = self.live_evidence.restore(snapshot)
            if observation is not None:
                previous = replace(snapshot, rail_observation=observation)
        if _can_retain_live_evidence(snapshot, previous):
            snapshot = _retain_live_evidence(snapshot, previous)
        return snapshot

    async def async_refresh_calendar_source(self, *, force: bool = False) -> bool:
        """Refresh the upstream calendar entity when configured and due."""
        if not self._calendar_entity:
            return False
        if not force and self._calendar_source_refresh_interval is None:
            return False

        if self.hass.states.get(self._calendar_entity) is None:
            self.last_calendar_source_refresh_error = "calendar_unavailable"
            return False

        now = dt_util.now()
        if (
            not force
            and self._last_calendar_source_refresh_attempt_at is not None
            and now - self._last_calendar_source_refresh_attempt_at
            < DEFAULT_UPDATE_INTERVAL
        ):
            return False
        if (
            not force
            and self.last_calendar_source_refresh_at is not None
            and now - self.last_calendar_source_refresh_at
            < self._calendar_source_refresh_interval
        ):
            return False

        self._last_calendar_source_refresh_attempt_at = now
        try:
            await self.hass.services.async_call(
                "homeassistant",
                "update_entity",
                {"entity_id": self._calendar_entity},
                blocking=True,
            )
        except HomeAssistantError as err:
            self.last_calendar_source_refresh_error = type(err).__name__
            _LOGGER.warning(
                "Unable to refresh the configured calendar source (%s)",
                self.last_calendar_source_refresh_error,
            )
            return False

        self.last_calendar_source_refresh_at = now
        self.last_calendar_source_refresh_error = None
        return True

    async def async_refresh_calendar_and_review(self) -> JourneySnapshot:
        """Force the source calendar to update before reviewing the journey."""
        await self.async_refresh_calendar_source(force=True)
        await self.async_request_refresh()
        return self.data

    async def async_review_live_rail(
        self,
        *,
        decision_path: str = "transportapi_manual",
        urgent: bool = False,
        force_calendar_refresh: bool = False,
    ) -> JourneySnapshot:
        """Run a quota-controlled provider review and publish its snapshot."""
        if force_calendar_refresh:
            await self.async_refresh_calendar_source(force=True)
        try:
            snapshot = await self.engine.async_review_live_rail(
                decision_path=decision_path,
                urgent=urgent,
            )
        except ValueError as err:
            raise HomeAssistantError(str(err)) from None
        self.last_live_check_at = snapshot.checked_at
        previous = self._last_live_snapshot
        if (
            snapshot.rail_observation is None
            and _can_retain_live_evidence(snapshot, previous)
        ):
            snapshot = _retain_live_evidence(snapshot, previous)
        if (
            snapshot.rail_observation is not None
            and not snapshot.rail_observation.retained
        ):
            self._last_live_snapshot = snapshot
            await self.live_evidence.async_save(snapshot)
        self.async_set_updated_data(snapshot)
        return snapshot

    async def async_test_station_access(self) -> JourneySnapshot:
        """Force one station-access request and publish the result."""
        snapshot = await self.engine.async_review(force_station_access=True)
        if _can_retain_live_evidence(snapshot, self._last_live_snapshot):
            snapshot = _retain_live_evidence(snapshot, self._last_live_snapshot)
        self.last_station_access_test_at = snapshot.checked_at
        self.async_set_updated_data(snapshot)
        return snapshot

    def record_notification(self, kind: str, sent_at: datetime) -> None:
        """Record privacy-safe notification diagnostics."""
        self.last_notification = kind
        self.last_notification_at = sent_at


def _retain_live_evidence(
    snapshot: JourneySnapshot,
    previous: JourneySnapshot,
) -> JourneySnapshot:
    """Carry provider evidence across quota-free calendar and route refreshes."""
    observation = previous.rail_observation
    journey = snapshot.next_journey
    if observation is None or journey is None:
        return snapshot
    age_seconds = max(
        0,
        int((snapshot.checked_at - observation.observed_at).total_seconds()),
    )
    retained = replace(
        observation,
        freshness=("historical" if snapshot.status == "active" else "retained"),
        age_seconds=age_seconds,
        retained=True,
    )
    if observation.cancelled:
        status = "cancelled"
        timing = None
        phase = "cancelled"
    else:
        actionable_departure = (
            observation.predicted_departure or observation.scheduled_departure
        )
        timing = snapshot.timing
        # Retained provider evidence remains visible and notification-worthy,
        # but never alters the calendar-anchored personal departure plan.
        if actionable_departure <= snapshot.checked_at:
            status = "active"
        elif observation.delay_minutes > 0:
            status = "delayed"
        else:
            status = "planned"
        phase = calculate_operational_phase(
            status=status,
            timing=timing,
            departure=actionable_departure,
            now=snapshot.checked_at,
        )
    return replace(
        snapshot,
        status=status,
        next_journey=previous.next_journey,
        timing=timing,
        rail_observation=retained,
        operational_phase=phase,
    )


def _can_retain_live_evidence(
    snapshot: JourneySnapshot,
    previous: JourneySnapshot | None,
) -> bool:
    """Return whether both snapshots identify the same scheduled journey."""
    return bool(
        previous is not None
        and snapshot.next_journey is not None
        and previous.next_journey is not None
        and previous.rail_observation is not None
        and snapshot.next_journey.start == previous.next_journey.start
        and snapshot.next_journey.summary == previous.next_journey.summary
    )
