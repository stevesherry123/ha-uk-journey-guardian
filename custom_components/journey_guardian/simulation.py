"""Deterministic, quota-free journey and rail-provider simulation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import (
    BudgetSnapshot,
    JourneyEvent,
    JourneySnapshot,
    RailObservation,
)
from .phase import calculate_operational_phase
from .timing import calculate_fallback_timing


@dataclass(frozen=True, slots=True)
class SimulationRequest:
    """One synthetic scenario fixed to an activation time."""

    scenario: str
    scheduled_departure: datetime
    delay_minutes: int
    duration_minutes: int
    activated_at: datetime
    accelerated: bool


class JourneySimulation:
    """Hold an explicitly activated, in-memory simulation scenario."""

    def __init__(self) -> None:
        """Initialize with live calendar mode enabled."""
        self._request: SimulationRequest | None = None

    @property
    def active(self) -> bool:
        """Return whether reviews are currently isolated from live inputs."""
        return self._request is not None

    def activate(
        self,
        *,
        scenario: str,
        now: datetime,
        departure_in_minutes: int,
        delay_minutes: int,
        duration_minutes: int,
        accelerated: bool = False,
    ) -> None:
        """Activate a synthetic scenario without calling an external provider."""
        self._request = SimulationRequest(
            scenario=scenario,
            scheduled_departure=now + timedelta(minutes=departure_in_minutes),
            delay_minutes=delay_minutes if scenario == "delayed" else 0,
            duration_minutes=duration_minutes,
            activated_at=now,
            accelerated=accelerated,
        )

    def clear(self) -> None:
        """Return subsequent reviews to the configured calendar source."""
        self._request = None

    def snapshot(
        self,
        *,
        now: datetime,
        budget: BudgetSnapshot,
        preparation_minutes: int,
        early_warning_minutes: int,
        station_buffer_minutes: int,
        station_access_minutes: int,
    ) -> JourneySnapshot | None:
        """Build a decision snapshot for the active synthetic scenario."""
        request = self._request
        if request is None:
            return None

        predicted_departure = (
            request.scheduled_departure
            + timedelta(minutes=request.delay_minutes)
            if request.scenario == "delayed"
            else None
        )
        effective_departure = predicted_departure or request.scheduled_departure
        journey_end = effective_departure + timedelta(
            minutes=request.duration_minutes
        )
        leg_count = 2 if request.scenario == "split_on_time" else 1
        cancelled = request.scenario == "cancelled"
        provider_available = request.scenario != "provider_unavailable"

        if now >= journey_end:
            self.clear()
            return None

        journey = JourneyEvent(
            start=request.scheduled_departure,
            end=journey_end,
            summary="Rail simulation - Simulation Origin to Simulation Destination",
            location="Simulation Origin",
            origin_code="SIM",
            origin_name="Simulation Origin",
            destination_confirmation="Simulation Destination",
            decision_path=f"simulation_{request.scenario}",
        )
        observation = RailObservation(
            scenario=request.scenario,
            source="simulation",
            classification="simulated",
            observed_at=now,
            scheduled_departure=request.scheduled_departure,
            predicted_departure=predicted_departure,
            delay_minutes=request.delay_minutes,
            cancelled=cancelled,
            leg_count=leg_count,
            provider_available=provider_available,
        )

        if cancelled:
            status = "cancelled"
            timing = None
        else:
            if not provider_available:
                status = "error"
            elif now >= effective_departure:
                status = "active"
            elif request.scenario == "delayed":
                status = "delayed"
            else:
                status = "planned"
            timing = calculate_fallback_timing(
                JourneyEvent(
                    start=effective_departure,
                    end=journey.end,
                    summary=journey.summary,
                    location=journey.location,
                    origin_code=journey.origin_code,
                    origin_name=journey.origin_name,
                    destination_confirmation=journey.destination_confirmation,
                    decision_path=journey.decision_path,
                ),
                preparation_minutes=(2 if request.accelerated else preparation_minutes),
                early_warning_minutes=(
                    0 if request.accelerated else early_warning_minutes
                ),
                station_buffer_minutes=(
                    1 if request.accelerated else station_buffer_minutes
                ),
                station_access_minutes=(
                    2 if request.accelerated else station_access_minutes
                ),
                source="simulation",
                classification=(
                    "simulated_predicted"
                    if predicted_departure is not None
                    else "simulated_scheduled"
                ),
            )

        return JourneySnapshot(
            status=status,
            checked_at=now,
            next_journey=journey,
            budget=budget,
            timing=timing,
            rail_observation=observation,
            simulation_active=True,
            operational_phase=calculate_operational_phase(
                status=status,
                timing=timing,
                departure=effective_departure,
                now=now,
                error=(
                    "simulated_provider_unavailable"
                    if not provider_available
                    else None
                ),
            ),
            error=(
                "simulated_provider_unavailable"
                if not provider_available
                else None
            ),
        )
