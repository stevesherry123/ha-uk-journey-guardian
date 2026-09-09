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
from .google_routes import GoogleRoutesClient, GoogleRoutesError
from .journey import select_next_journey
from .models import JourneyEvent, JourneySnapshot, JourneyTiming
from .phase import calculate_operational_phase
from .provider_broker import ProviderBrokerError
from .rail import RailDataError, normalize_station_board
from .simulation import JourneySimulation
from .station import StationResolution, StationResolutionError, resolve_station
from .station_access_profiles import mode_for_journey, parse_station_access_profiles
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
        person_entity: str | None = None,
        station_access_mode: str = "auto",
        station_access_profiles: object = None,
        google_routes_client: GoogleRoutesClient | None = None,
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
        self._person_entity = person_entity
        self._station_access_mode = station_access_mode
        self._station_access_profiles = parse_station_access_profiles(
            station_access_profiles
        )
        self._google_routes_client = google_routes_client
        self._station_resolutions: dict[str, StationResolution] = {}
        self._last_live_rail_error: str | None = None
        self._route_warning_keys: set[str] = set()

    async def async_review(
        self, *, force_station_access: bool = False
    ) -> JourneySnapshot:
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
                await self._async_calculate_timing(
                    next_journey,
                    allow_provider=status != "active",
                    force_refresh=force_station_access,
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

    @property
    def station_access_configured(self) -> bool:
        """Return whether live station-access routing is available."""
        return bool(
            self._google_routes_client is not None
            and self._google_routes_client.configured
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
                getattr(err, "schedule_offset_minutes", None),
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
            timing = await self._async_calculate_timing(
                # Live rail data is advisory: a small timetable delay must not
                # silently relax the traveller's established leave plan.
                resolved_journey,
                base_source="transportapi",
                base_classification="calendar_anchored",
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
            None,
        )
        return result

    async def _async_calculate_timing(
        self,
        journey: JourneyEvent,
        *,
        allow_provider: bool = True,
        force_refresh: bool = False,
        base_source: str = "configured_fallback",
        base_classification: str = "inferred",
    ) -> JourneyTiming:
        """Use a live station-access route or the conservative fallback."""
        person_state = (
            self._hass.states.get(self._person_entity)
            if self._person_entity
            else None
        )
        mode = mode_for_journey(journey, self._station_access_profiles)
        if mode is None:
            mode = self._station_access_mode
        if mode == "auto":
            if person_state is None or person_state.state in {
                "unknown",
                "unavailable",
            }:
                mode = "unknown"
            else:
                mode = "driving" if person_state.state == "home" else "transit"
        fallback = calculate_fallback_timing(
            journey,
            preparation_minutes=self._preparation_buffer_minutes,
            early_warning_minutes=self._early_warning_minutes,
            station_buffer_minutes=self._station_buffer_minutes,
            station_access_minutes=self._station_access_fallback_minutes,
            source=base_source,
            classification=base_classification,
            station_access_mode=mode,
            station_access_source="configured_fallback",
            station_access_classification="inferred",
        )
        client = self._google_routes_client
        if not allow_provider or client is None or not client.configured:
            return fallback
        if person_state is None or mode == "unknown":
            return fallback
        latitude = person_state.attributes.get("latitude")
        longitude = person_state.attributes.get("longitude")
        if not isinstance(latitude, int | float) or not isinstance(
            longitude, int | float
        ):
            return fallback
        destination = _station_destination(journey)
        departure_time = max(
            fallback.leave_home_at,
            dt_util.now() + timedelta(minutes=1),
        )
        try:
            estimate = await client.async_route(
                latitude=float(latitude),
                longitude=float(longitude),
                destination=destination,
                mode=mode,
                departure_time=departure_time,
                force_refresh=force_refresh,
            )
        except GoogleRoutesError as err:
            category = str(err)
            warning_key = f"{journey.start.isoformat()}|{category}"
            if warning_key not in self._route_warning_keys:
                _LOGGER.warning("Station access routing failed: %s", category)
                self._route_warning_keys.add(warning_key)
                if len(self._route_warning_keys) > 20:
                    self._route_warning_keys.pop()
            return replace(
                fallback,
                station_access_error=f"google_routes_{category}",
            )
        return calculate_fallback_timing(
            journey,
            preparation_minutes=self._preparation_buffer_minutes,
            early_warning_minutes=self._early_warning_minutes,
            station_buffer_minutes=self._station_buffer_minutes,
            station_access_minutes=estimate.duration_minutes,
            source="google_routes",
            classification=(
                f"cached_{mode}" if estimate.cache_hit else f"live_{mode}"
            ),
            station_access_mode=mode,
            station_access_source="google_routes",
            station_access_classification=(
                f"cached_{mode}" if estimate.cache_hit else f"live_{mode}"
            ),
            station_access_distance_meters=estimate.distance_meters,
            station_access_checked_at=estimate.observed_at,
        )

    async def _async_record_live_check(
        self,
        snapshot,
        trigger,
        outcome,
        error_category,
        station,
        destination,
        stage,
        schedule_offset_minutes,
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
                "schedule_offset_minutes": schedule_offset_minutes,
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


def _station_destination(journey: JourneyEvent) -> str:
    """Return the most specific calendar station address available."""
    if journey.location.strip():
        return journey.location.rsplit(";", 1)[-1].strip()
    return f"{journey.origin_name} railway station, UK"
