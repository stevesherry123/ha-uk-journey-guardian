"""Journey Guardian update coordinator."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .connection import resolve_transfer_allowance
from .connection_preferences import (
    CONF_CONNECTION_MONITOR,
    CONF_STATION_TRANSFERS,
    CONF_TRANSFER_FALLBACK,
    DEFAULT_TRANSFER_MINUTES,
    parse_station_transfers,
    station_key,
)
from .connection_storage import HAConnectionConfirmations
from .const import CONF_LIVE_RAIL_PROVIDER, DEFAULT_UPDATE_INTERVAL, NAME
from .engine import JourneyGuardianEngine
from .health_issues import JourneyHealthIssues
from .live_evidence import MAX_OBSERVATION_AGE, LiveEvidenceStore
from .models import JourneySnapshot
from .phase import calculate_operational_phase
from .railinfo_booking_match import BookingMatchRequest, BookingMatchResult
from .travel_plan import TravelPlanStore

_LOGGER = logging.getLogger(__name__)
CALENDAR_SOURCE_RETRY_INTERVAL = timedelta(minutes=15)


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
        self.last_successful_calendar_review_at: datetime | None = None
        self.health_issues = JourneyHealthIssues(hass)
        entry.async_on_unload(self.health_issues.stop)
        self._last_live_snapshot: JourneySnapshot | None = None
        self._booking_match_revision = 0
        self._booking_match_review: BookingMatchResult | None = None
        settings = {**entry.data, **entry.options}
        self.connection_monitor_enabled = settings.get(CONF_CONNECTION_MONITOR, False)
        self.connection_alert_ledger = None
        self.connection_alert_error = False
        self.connection_assessments = {}
        self.next_connection_check_at = None
        self.transfer_fallback = settings.get(
            CONF_TRANSFER_FALLBACK, DEFAULT_TRANSFER_MINUTES
        )
        self.station_transfers = parse_station_transfers(
            settings.get(CONF_STATION_TRANSFERS)
        )
        self.live_evidence = LiveEvidenceStore(
            hass, scope=f"{entry.entry_id}|{calendar_entity}",
            provider=settings.get(CONF_LIVE_RAIL_PROVIDER, ""),
        )
        self.travel_plan = TravelPlanStore(
            hass, scope=f"{entry.entry_id}|{calendar_entity}"
        )
        self.connection_confirmations = HAConnectionConfirmations(
            hass, scope=f"{entry.entry_id}|{calendar_entity}"
        )
        super().__init__(
            hass,
            logger=_LOGGER,
            config_entry=entry,
            name=NAME,
            update_interval=DEFAULT_UPDATE_INTERVAL,
            always_update=False,
        )

    def is_superseded(self, journey, now):
        recovery = getattr(self, "recovery_runtime", None)
        if recovery is None:
            return False
        booking_id = self.travel_plan.booking_identity(journey)
        if recovery.is_booking_superseded(booking_id, now):
            return True
        if journey.decision_path != "calendar_recovered":
            return False
        # Outage recovery reconstructs a summary without the original location.
        return any(
            datetime.fromisoformat(leg["departure"]) == journey.start
            and leg["arrival"] is not None
            and datetime.fromisoformat(leg["arrival"]) == journey.end
            and recovery.is_booking_superseded(leg["booking_id"], now)
            for leg in self.travel_plan.attributes(now)["retained_booked_legs"]
        )

    def suppress_superseded(self, snapshot):
        if (
            not snapshot.simulation_active and snapshot.next_journey is not None
            and self.is_superseded(snapshot.next_journey, dt_util.utcnow())
        ):
            return replace(
                snapshot, next_journey=None, timing=None, rail_observation=None,
                status="idle", operational_phase="idle",
            )
        return snapshot

    def connection_dashboard(self, now: datetime) -> dict:
        """Expose current candidate pairs without assuming live transfer viability."""
        snapshot = self.data
        error = self.connection_confirmations.persistence_error
        if snapshot is None or snapshot.simulation_active:
            return {"connections": [], "connection_storage_error": error}
        legs = self.travel_plan.attributes(now)["retained_booked_legs"]
        current = [leg for leg in legs if leg["in_latest_response"]]
        keys = {(first["booking_id"], second["booking_id"])
                for first, second in zip(current, current[1:], strict=False)}
        active = getattr(self.connection_confirmations, "active", None)
        if active is not None:
            keys.update((record.inbound_id, record.outbound_id)
                        for record in active(now=now))
        by_id = {leg["booking_id"]: leg for leg in legs}
        pairs = []
        recovery = getattr(self, "recovery_runtime", None)
        for first, second in sorted(
            keys, key=lambda pair: by_id.get(pair[1], {}).get("departure", "")
        ):
            if first not in by_id or second not in by_id:
                continue
            if recovery is not None and any(
                recovery.is_booking_superseded(key, now) for key in (first, second)
            ):
                continue
            inbound, outbound = by_id[first], by_id[second]
            saved = self.connection_confirmations.get(first, second, now=now)
            try:
                self.travel_plan.connection_pair(
                    inbound["booking_id"], outbound["booking_id"], now=now,
                    monitoring=saved is not None,
                )
            except ValueError:
                continue
            saved = self.connection_confirmations.get(
                inbound["booking_id"], outbound["booking_id"], now=now
            )
            allowance = resolve_transfer_allowance(
                connection_minutes=saved.override_minutes if saved else None,
                station_minutes=self.station_transfers.get(
                    station_key(inbound["destination"])
                ),
                global_minutes=self.transfer_fallback,
            )
            live = getattr(self, "connection_assessments", {}).get((first, second))
            assessment = None
            if live is not None:
                result, expiry = live
                assessment = result.as_dict()
                if snapshot.error or result.minimum_minutes != allowance.minutes:
                    assessment.update(
                        classification="unknown",
                        reason="calendar_unavailable" if snapshot.error
                        else "transfer_allowance_changed",
                        minutes_available=None, margin_minutes=None,
                    )
                elif expiry is not None and now > expiry:
                    assessment.update(classification="unknown", reason="evidence_stale",
                                      minutes_available=None, margin_minutes=None)
            pairs.append({
                "inbound_id": inbound["booking_id"],
                "outbound_id": outbound["booking_id"],
                "station": inbound["destination"],
                "inbound_arrival": inbound["arrival"],
                "outbound_departure": outbound["departure"],
                "confirmed": saved is not None,
                "assessment": assessment if saved else None,
                "last_alert": (
                    self.connection_alert_ledger.status((first, second), now=now)
                    if getattr(self, "connection_alert_ledger", None) is not None
                    else None
                ),
                "allowance_minutes": allowance.minutes,
                "allowance_source": allowance.source,
                "override_minutes": saved.override_minutes if saved else None,
                "can_confirm": not error and not snapshot.error
                and datetime.fromisoformat(outbound["departure"]) > now,
                "can_monitor": not error and not snapshot.error,
            })
        return {
            "connections": pairs, "connection_storage_error": error,
            "connection_alert_error": getattr(self, "connection_alert_error", False),
            "connection_monitor_enabled": getattr(
                self, "connection_monitor_enabled", False
            ),
            "connection_monitor_supported": getattr(
                getattr(self, "engine", None), "_live_rail_provider", None
            ) == "railinfo",
            "next_connection_check_at": (
                getattr(self, "next_connection_check_at", None).isoformat()
                if isinstance(getattr(self, "next_connection_check_at", None), datetime)
                else None
            ),
        }

    async def _async_update_data(self) -> JourneySnapshot:
        """Return the latest normalized journey state."""
        return await self._async_review_data()

    async def _async_review_data(
        self, *, force_station_access: bool = False
    ) -> JourneySnapshot:
        await self.async_refresh_calendar_source()
        snapshot = (
            await self.engine.async_review(force_station_access=True)
            if force_station_access else await self.engine.async_review()
        )
        self._update_health_issues(snapshot)
        await self.travel_plan.async_update(snapshot)
        snapshot = self.suppress_superseded(snapshot)
        recovered = self.live_evidence.restore_journey(snapshot)
        if recovered is not None and self.is_superseded(recovered, dt_util.utcnow()):
            recovered = None
        if recovered is not None:
            snapshot = replace(
                snapshot, next_journey=recovered, status="active",
                operational_phase="active",
            )
        previous = self._last_live_snapshot
        if not _can_retain_live_evidence(snapshot, previous):
            observation = self.live_evidence.restore(
                snapshot, recovered=recovered is not None
            )
            if observation is not None:
                previous = replace(snapshot, rail_observation=observation)
        if _can_retain_live_evidence(snapshot, previous):
            snapshot = _retain_live_evidence(snapshot, previous)
        await self.live_evidence.async_save(snapshot)
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
        retry_interval = (
            CALENDAR_SOURCE_RETRY_INTERVAL
            if self.last_calendar_source_refresh_error is not None
            else DEFAULT_UPDATE_INTERVAL
        )
        if (
            not force
            and self._last_calendar_source_refresh_attempt_at is not None
            and now - self._last_calendar_source_refresh_attempt_at
            < retry_interval
        ):
            return False
        if (
            not force
            and self.last_calendar_source_refresh_error is None
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

        state = self.hass.states.get(self._calendar_entity)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self.last_calendar_source_refresh_error = "calendar_unavailable"
            return False
        self.last_calendar_source_refresh_at = now
        self.last_calendar_source_refresh_error = None
        return True

    async def async_refresh_calendar_and_review(
        self, *, force_station_access: bool = False
    ) -> JourneySnapshot:
        """Force the source calendar to update before reviewing the journey."""
        await self.async_refresh_calendar_source(force=True)
        if force_station_access:
            self.async_set_updated_data(
                await self._async_review_data(force_station_access=True)
            )
        else:
            await self.async_request_refresh()
        return self.data

    async def async_review_live_rail(
        self,
        *,
        decision_path: str = "transportapi_manual",
        urgent: bool = False,
        force_calendar_refresh: bool = False,
        snapshot: JourneySnapshot | None = None,
    ) -> JourneySnapshot:
        """Run a quota-controlled provider review and publish its snapshot."""
        if force_calendar_refresh:
            await self.async_refresh_calendar_source(force=True)
        try:
            review_options = {"snapshot": snapshot} if snapshot is not None else {}
            snapshot = await self.engine.async_review_live_rail(
                decision_path=decision_path,
                urgent=urgent,
                **review_options,
            )
        except ValueError as err:
            raise HomeAssistantError(str(err)) from None
        if (
            snapshot.next_journey is not None
            and self.is_superseded(snapshot.next_journey, dt_util.utcnow())
        ):
            return self.data
        self.last_live_check_at = snapshot.checked_at
        if not snapshot.simulation_active:
            self.health_issues.observe(
                "rail", failed=snapshot.last_live_rail_error is not None,
                now=snapshot.checked_at, token=snapshot.checked_at.isoformat(),
            )
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

    async def async_booking_match(
        self, request: BookingMatchRequest
    ) -> BookingMatchResult:
        """Review the current booking without publishing a changed journey."""
        snapshot = self.data
        if (
            not self.last_update_success or snapshot is None
            or snapshot.error or snapshot.simulation_active
            or snapshot.next_journey != request.booking
        ):
            return BookingMatchResult("booking_match_context_unavailable")
        self._booking_match_revision += 1
        revision = self._booking_match_revision
        self._booking_match_review = None
        result = await self.engine.async_booking_match(request)
        if (
            self.data is not snapshot or not self.last_update_success
            or revision != self._booking_match_revision
        ):
            return BookingMatchResult("booking_match_context_changed")
        if result.proposal is not None:
            self._booking_match_review = result
        return result

    def confirm_booking_match(self, proposal_id: str) -> BookingMatchResult:
        """Acknowledge one current proposal, without changing operational intent."""
        snapshot = self.data
        review = self._booking_match_review
        proposal = review.proposal if review is not None else None
        if (
            not self.last_update_success or snapshot is None
            or snapshot.error or snapshot.simulation_active
            or snapshot.next_journey is None or proposal is None
            or snapshot.next_journey.booking_fingerprint != proposal.booking_fingerprint
            or proposal.proposal_id != proposal_id
            or not proposal.observed_at <= dt_util.utcnow() < proposal.valid_until
        ):
            return BookingMatchResult("booking_match_confirmation_unavailable")
        confirmed = BookingMatchResult("proposal_confirmed", proposal, confirmed=True)
        self._booking_match_review = confirmed
        return confirmed

    async def async_test_station_access(
        self, *, automatic: bool = False
    ) -> JourneySnapshot:
        """Force one station-access request and publish the result."""
        if not automatic:
            self.engine.reset_google_access_backoff()
        snapshot = await self._async_review_data(force_station_access=True)
        self.last_station_access_test_at = snapshot.checked_at
        self.async_set_updated_data(snapshot)
        return snapshot

    def record_notification(self, kind: str, sent_at: datetime) -> None:
        """Record privacy-safe notification diagnostics."""
        self.last_notification = kind
        self.last_notification_at = sent_at

    def _update_health_issues(self, snapshot: JourneySnapshot) -> None:
        if snapshot.simulation_active:
            return
        now = snapshot.checked_at
        calendar_failed = snapshot.error == "calendar_unavailable"
        source_failed = self.last_calendar_source_refresh_error is not None
        source_attempt = self._last_calendar_source_refresh_attempt_at
        self.health_issues.observe(
            "calendar", failed=calendar_failed or source_failed, now=now,
            token=(
                source_attempt.isoformat()
                if source_failed and not calendar_failed and source_attempt else
                now.isoformat()
            ),
        )
        if not calendar_failed:
            self.last_successful_calendar_review_at = now
        timing = snapshot.timing
        if timing is not None:
            self.health_issues.observe_google_access(
                error=timing.station_access_error,
                source=timing.station_access_source,
            )
        if timing is not None and (
            timing.station_access_error is not None
            or timing.station_access_source in {"google_routes", "waze_sensor"}
        ):
            self.health_issues.observe(
                "routing", failed=timing.station_access_error is not None,
                now=now, token=(timing.station_access_checked_at or now).isoformat(),
            )
        if self.last_live_check_at is not None and snapshot.last_live_rail_error:
            self.health_issues.observe(
                "rail", failed=True, now=now,
                token=self.last_live_check_at.isoformat(),
            )


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
        and snapshot.next_journey.end == previous.next_journey.end
        and not snapshot.simulation_active
        and not previous.simulation_active
        and timedelta(0) <= snapshot.checked_at
        - previous.rail_observation.observed_at <= MAX_OBSERVATION_AGE
    )
