"""Data models for Journey Guardian."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

BOOKING_CHECK_FAILURES = frozenset(
    f"{provider}_{category}"
    for provider in ("railinfo", "transportapi")
    for category in (
        "rail_schedule_mismatch", "rail_service_not_found",
        "rail_service_ambiguous", "station_not_found",
        "station_code_unresolved", "station_match_ambiguous",
    )
)


@dataclass(frozen=True, slots=True)
class JourneyEvent:
    """A normalized timed journey event."""

    start: datetime
    end: datetime | None
    summary: str
    location: str
    origin_code: str
    origin_name: str
    destination_confirmation: str
    decision_path: str

    @property
    def booking_fingerprint(self) -> str:
        """Bind diagnostic evidence to exact booking intent, not selection order."""
        values = [
            self.start.isoformat(), self.end.isoformat() if self.end else None,
            self.summary, self.location, self.origin_name,
            self.destination_confirmation,
        ]
        return hashlib.sha256(json.dumps(values).encode()).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable representation."""
        data = asdict(self)
        data["start"] = self.start.isoformat()
        data["end"] = self.end.isoformat() if self.end is not None else None
        return data


@dataclass(frozen=True, slots=True)
class JourneyTiming:
    """Actionable journey times and their provenance."""

    prepare_at: datetime
    leave_home_at: datetime
    station_arrival_at: datetime
    preparation_minutes: int
    early_warning_minutes: int
    station_buffer_minutes: int
    station_access_minutes: int
    source: str
    classification: str
    station_access_mode: str = "unknown"
    station_access_source: str = "configured_fallback"
    station_access_classification: str = "inferred"
    station_access_distance_meters: int | None = None
    station_access_error: str | None = None
    station_access_checked_at: datetime | None = None
    station_access_provider_minutes: int | None = None
    station_access_fallback_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable representation."""
        data = asdict(self)
        data["prepare_at"] = self.prepare_at.isoformat()
        data["leave_home_at"] = self.leave_home_at.isoformat()
        data["station_arrival_at"] = self.station_arrival_at.isoformat()
        data["station_access_checked_at"] = (
            self.station_access_checked_at.isoformat()
            if self.station_access_checked_at is not None
            else None
        )
        return data


@dataclass(frozen=True, slots=True)
class RailObservation:
    """Provider-neutral rail observation used by decisions and simulations."""

    scenario: str
    source: str
    classification: str
    observed_at: datetime
    scheduled_departure: datetime
    predicted_departure: datetime | None
    delay_minutes: int
    cancelled: bool
    leg_count: int
    provider_available: bool
    freshness: str = "current"
    age_seconds: int = 0
    service_identity: str | None = None
    platform: str | None = None
    match_quality: str = "not_applicable"
    schedule_offset_minutes: int = 0
    retained: bool = False
    destination_code: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable representation."""
        data = asdict(self)
        data["observed_at"] = self.observed_at.isoformat()
        data["scheduled_departure"] = self.scheduled_departure.isoformat()
        data["predicted_departure"] = (
            self.predicted_departure.isoformat()
            if self.predicted_departure is not None
            else None
        )
        return data


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    """Current TransportAPI allowance state."""

    date: str
    calls_used: int
    daily_limit: int
    urgent_reserve: int

    @property
    def calls_remaining(self) -> int:
        """Return total calls remaining."""
        return max(0, self.daily_limit - self.calls_used)

    @property
    def routine_calls_remaining(self) -> int:
        """Return calls available without consuming the urgent reserve."""
        return max(0, self.daily_limit - self.urgent_reserve - self.calls_used)

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable representation."""
        return {
            "date": self.date,
            "calls_used": self.calls_used,
            "daily_limit": self.daily_limit,
            "urgent_reserve": self.urgent_reserve,
            "calls_remaining": self.calls_remaining,
            "routine_calls_remaining": self.routine_calls_remaining,
        }


@dataclass(frozen=True, slots=True)
class RailCheckIssue:
    """A failed check, not proof that the calendar itself is incorrect."""

    booking_fingerprint: str
    recorded_at: datetime
    category: str
    stage: str

    def as_dict(self) -> dict[str, Any]:
        """Expose bounded categories and a timestamp, never provider payloads."""
        return {
            "booking_fingerprint": self.booking_fingerprint,
            "recorded_at": self.recorded_at.isoformat(),
            "category": self.category,
            "stage": self.stage,
        }


@dataclass(frozen=True, slots=True)
class JourneySnapshot:
    """Coordinator output exposed to Home Assistant."""

    status: str
    checked_at: datetime
    next_journey: JourneyEvent | None
    budget: BudgetSnapshot
    timing: JourneyTiming | None = None
    rail_observation: RailObservation | None = None
    simulation_active: bool = False
    operational_phase: str = "idle"
    error: str | None = None
    last_live_rail_error: str | None = None
    booked_legs: tuple[JourneyEvent, ...] = ()
    booked_leg_count: int = 0
    current_rail_issue: RailCheckIssue | None = None
    calendar_read_error: str | None = None

    @property
    def data_healthy(self) -> bool:
        """Return whether the most recent review completed cleanly."""
        return self.error is None

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable representation."""
        return {
            "status": self.status,
            "checked_at": self.checked_at.isoformat(),
            "next_journey": (
                self.next_journey.as_dict() if self.next_journey is not None else None
            ),
            "timing": self.timing.as_dict() if self.timing is not None else None,
            "rail_observation": (
                self.rail_observation.as_dict()
                if self.rail_observation is not None
                else None
            ),
            "simulation_active": self.simulation_active,
            "operational_phase": self.operational_phase,
            "budget": self.budget.as_dict(),
            "data_healthy": self.data_healthy,
            "error": self.error,
            "last_live_rail_error": self.last_live_rail_error,
            "current_rail_issue": (
                self.current_rail_issue.as_dict() if self.current_rail_issue else None
            ),
            "booked_legs": [leg.as_dict() for leg in self.booked_legs],
            "booked_leg_count": self.booked_leg_count,
        }
