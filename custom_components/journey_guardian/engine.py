"""Journey Guardian decision engine."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import replace
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .budget import TransportAPIBudget
from .check_history import CheckHistory
from .const import (
    DEFAULT_EARLY_WARNING_MINUTES,
    DEFAULT_LOOKAHEAD_HOURS,
    DEFAULT_PREPARATION_BUFFER_MINUTES,
    DEFAULT_STATION_ACCESS_FALLBACK_MINUTES,
    DEFAULT_STATION_BUFFER_MINUTES,
)
from .journey import select_next_journey
from .models import JourneySnapshot
from .phase import calculate_operational_phase
from .provider_broker import ProviderBrokerError
from .rail import RailDataError, normalize_station_board
from .simulation import JourneySimulation
from .station import StationResolution, StationResolutionError, resolve_station
from .timing import calculate_fallback_timing
from .transportapi import TransportAPIClient

_LOGGER = logging.getLogger(__name__)


class JourneyGuardianEngine:
    """Read journey inputs and produce one normalized decision snapshot."""

    def __init__(
        self,
        hass: HomeAssistant,
        calendar_entity: str,
        budget: TransportAPIBudget,
        preparation_buffer_minutes: int = DEFAULT_PREPARATION_BUFFER_MINUTES,
        early_warning_minutes: int = DEFAULT_EARLY_WARNING_MINUTES,
        station_buffer_minutes: int = DEFAULT_STATION_BUFFER_MINUTES,
        station_access_fallback_minutes: int = (
            DEFAULT_STATION_ACCESS_FALLBACK_MINUTES
        ),
        simulation: JourneySimulation | None = None,
        transportapi_client: TransportAPIClient | None = None,
        check_history: CheckHistory | None = None,
    ) -> None:
        """Initialize the engine."""
        self._hass = hass
        self._calendar_entity = calendar_entity
        self._budget = budget
        self._preparation_buffer_minutes = preparation_buffer_minutes
        self._early_warning_minutes = early_warning_minutes
        self._station_buffer_minutes = station_buffer_minutes
        self._station_access_fallback_minutes = station_access_fallback_minutes
        self._simulation = simulation
        self._transportapi_client = transportapi_client
        self._check_history = check_history
        self._station_resolutions: dict[str, StationResolution] = {}
        self._last_live_rail_error: str | None = None

    async def async_review(self) -> JourneySnapshot:
        """Review the next calendar journey without consuming rail API quota."""
        checked_at = dt_util.now()
        if self._simulation is not None:
            simulated = self._simulation.snapshot(
                now=checked_at,
                budget=self._budget.snapshot(),
                preparation_minutes=self._preparation_buffer_minutes,
                early_warning_minutes=self._early_warning_minutes,
                station_buffer_minutes=self._station_buffer_minutes,
                station_access_minutes=self._station_access_fallback_minutes,
            )
            if simulated is not None:
                return replace(
                    simulated,
                    last_live_rail_error=self._last_live_rail_error,
                )
        try:
            events = await self._async_calendar_events(checked_at)
            next_journey = select_next_journey(events, checked_at)
            if next_journey is None:
                status = "idle"
            elif next_journey.start <= checked_at:
                status = "active"
            else:
                status = "planned"
            timing = (
                calculate_fallback_timing(
                    next_journey,
                    preparation_minutes=self._preparation_buffer_minutes,
                    early_warning_minutes=self._early_warning_minutes,
                    station_buffer_minutes=self._station_buffer_minutes,
                    station_access_minutes=self._station_access_fallback_minutes,
                )
                if next_journey is not None
                else None
            )
            return JourneySnapshot(
                status=status,
                checked_at=checked_at,
                next_journey=next_journey,
                budget=self._budget.snapshot(),
                timing=timing,
                operational_phase=calculate_operational_phase(
                    status=status,
                    timing=timing,
                    departure=(next_journey.start if next_journey else None),
                    now=checked_at,
                ),
                last_live_rail_error=self._last_live_rail_error,
            )
        except Exception as err:  # Home Assistant service errors vary by provider
            # Exception messages from calendars and future provider clients may
            # contain entity IDs, event details, URLs, or credentials. Preserve
            # only a stable public category in coordinator data.
            _LOGGER.warning(
                "Calendar review failed with %s", type(err).__name__
            )
            return JourneySnapshot(
                status="error",
                checked_at=checked_at,
                next_journey=None,
                budget=self._budget.snapshot(),
                operational_phase="error",
                error="calendar_unavailable",
                last_live_rail_error=self._last_live_rail_error,
            )

    @property
    def live_rail_configured(self) -> bool:
        """Return whether quota-controlled live rail acquisition is available."""
        return bool(
            self._transportapi_client is not None
            and self._transportapi_client.configured
        )

    async def async_review_live_rail(
        self,
        *,
        decision_path: str = "transportapi_manual",
        urgent: bool = False,
    ) -> JourneySnapshot:
        """Perform one quota-controlled live rail review."""
        snapshot = await self.async_review()
        if snapshot.simulation_active:
            raise ValueError("simulation_active")
        journey = snapshot.next_journey
        if journey is None:
            raise ValueError("rail_journey_unavailable")
        client = self._transportapi_client
        if client is None or not client.configured:
            raise ValueError("transportapi_credentials_missing")

        station = None
        destination = None
        stage = "resolve_origin"
        try:
            station = await self._async_resolve_station(
                name=journey.origin_name,
                code=journey.origin_code,
                location=journey.location,
                urgent=urgent,
            )
            stage = "resolve_destination"
            destination = await self._async_resolve_station(
                name=journey.destination_confirmation,
                code="CALENDAR",
                location="",
                urgent=urgent,
            )
            stage = "station_timetable"
            board = await client.async_station_board(
                station.code,
                journey.start,
                calling_at=destination.code,
                urgent=urgent,
            )
            stage = "match_timetable"
            observation = normalize_station_board(
                board.payload,
                journey=journey,
                observed_at=board.observed_at,
                expected_station_code=station.code,
            )
            observation = replace(
                observation,
                freshness=board.freshness,
                age_seconds=board.age_seconds,
                provider_available=board.healthy,
            )
        except (ProviderBrokerError, RailDataError, StationResolutionError) as err:
            category = getattr(err, "category", "provider_unavailable")
            self._last_live_rail_error = f"transportapi_{category}"
            _LOGGER.warning("Manual rail review failed: %s", category)
            degraded = replace(
                snapshot,
                budget=self._budget.snapshot(),
                last_live_rail_error=self._last_live_rail_error,
            )
            await self._async_record_live_check(
                degraded,
                decision_path,
                "failed",
                category,
                station,
                destination,
                stage,
            )
            return degraded

        self._last_live_rail_error = None
        resolved_journey = replace(
            journey,
            origin_code=station.code,
            origin_name=station.name,
            destination_confirmation=destination.name,
            decision_path=decision_path,
        )
        if observation.cancelled:
            status = "cancelled"
            timing = None
        else:
            departure = (
                observation.predicted_departure
                or observation.scheduled_departure
            )
            if departure <= snapshot.checked_at:
                status = "active"
            elif observation.delay_minutes > 0:
                status = "delayed"
            else:
                status = "planned"
            timing = calculate_fallback_timing(
                replace(resolved_journey, start=departure),
                preparation_minutes=self._preparation_buffer_minutes,
                early_warning_minutes=self._early_warning_minutes,
                station_buffer_minutes=self._station_buffer_minutes,
                station_access_minutes=self._station_access_fallback_minutes,
                source="transportapi",
                classification=(
                    "predicted"
                    if observation.predicted_departure is not None
                    else "scheduled"
                ),
            )
        actionable_departure = (
            observation.predicted_departure
            or observation.scheduled_departure
        )
        result = JourneySnapshot(
            status=status,
            checked_at=snapshot.checked_at,
            next_journey=resolved_journey,
            budget=self._budget.snapshot(),
            timing=timing,
            rail_observation=observation,
            operational_phase=calculate_operational_phase(
                status=status,
                timing=timing,
                departure=actionable_departure,
                now=snapshot.checked_at,
            ),
            error=board.error_category,
            last_live_rail_error=None,
        )
        await self._async_record_live_check(
            result,
            decision_path,
            "success",
            None,
            station,
            destination,
            "complete",
        )
        return result

    async def _async_record_live_check(
        self,
        snapshot,
        trigger,
        outcome,
        error_category,
        station,
        destination,
        stage,
    ) -> None:
        """Persist a privacy-safe live-check audit record."""
        if self._check_history is None:
            return
        journey = snapshot.next_journey
        fingerprint = None
        if journey is not None:
            fingerprint = hashlib.sha256(
                f"{journey.start.isoformat()}|{journey.origin_name}|{journey.destination_confirmation}".encode()
            ).hexdigest()[:16]
        observation = snapshot.rail_observation
        await self._check_history.async_record(
            {
                "checked_at": snapshot.checked_at.isoformat(),
                "trigger": trigger,
                "journey_fingerprint": fingerprint,
                "origin_code": (
                    station.code
                    if station
                    else journey.origin_code if journey else None
                ),
                "destination_code": destination.code if destination else None,
                "operation": "station_timetables",
                "stage": stage,
                "outcome": outcome,
                "error_category": error_category,
                "match_quality": observation.match_quality if observation else None,
                "calls_used": snapshot.budget.calls_used,
                "status": snapshot.status,
            }
        )

    async def _async_resolve_station(
        self, *, name: str, code: str, location: str, urgent: bool = False
    ) -> StationResolution:
        """Resolve explicitly or with one cached manual Places lookup."""
        cache_key = hashlib.sha256(
            "|".join(
                (
                    code,
                    name.casefold().strip(),
                    location.casefold().strip(),
                )
            ).encode()
        ).hexdigest()
        if cached := self._station_resolutions.get(cache_key):
            return cached
        try:
            station = resolve_station(
                origin_name=name,
                origin_code=code,
                location=location,
            )
        except StationResolutionError as err:
            if err.category != "station_code_unresolved":
                raise
            if self._transportapi_client is None:
                raise
            places = await self._transportapi_client.async_places(
                name, urgent=urgent
            )
            station = resolve_station(
                origin_name=name,
                origin_code=code,
                location=location,
                places_payload=places.payload,
            )
        if len(self._station_resolutions) >= 20:
            self._station_resolutions.pop(next(iter(self._station_resolutions)))
        self._station_resolutions[cache_key] = station
        return station

    async def _async_calendar_events(self, start: Any) -> list[dict[str, Any]]:
        end = start + timedelta(hours=DEFAULT_LOOKAHEAD_HOURS)
        response = await self._hass.services.async_call(
            "calendar",
            "get_events",
            {
                "entity_id": self._calendar_entity,
                "start_date_time": start.isoformat(),
                "end_date_time": end.isoformat(),
            },
            blocking=True,
            return_response=True,
        )
        calendar_data = response.get(self._calendar_entity, {})
        events = calendar_data.get("events", [])
        return list(events) if isinstance(events, list) else []
