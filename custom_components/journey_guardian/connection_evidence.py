"""Pure connection assessment from matched station-time evidence.

Provider adapters must establish these facts; timetable times are not live evidence.
This module performs no acquisition, persistence, scheduling or notification work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from .connection import assess_connection
from .models import RailObservation


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("timezone_required")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class ServiceReference:
    """Provider and dated matched identity; a headcode alone is insufficient."""

    provider: str
    identity: str

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip() or len(value) > 256
            for value in (self.provider, self.identity)
        ):
            raise ValueError("matched_service_reference_required")


@dataclass(frozen=True, slots=True)
class StationTimeEvidence:
    """An explicitly typed observation at a resolved station for one service."""

    service: ServiceReference
    station_identity: str
    event: Literal["arrival", "departure"]
    kind: Literal["scheduled", "predicted", "actual"]
    event_at: datetime
    observed_at: datetime
    retained: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.service, ServiceReference):
            raise ValueError("matched_service_reference_required")
        if (
            not isinstance(self.station_identity, str)
            or not self.station_identity.strip()
            or len(self.station_identity) > 256
        ):
            raise ValueError("resolved_station_required")
        if self.event not in ("arrival", "departure"):
            raise ValueError("invalid_station_event")
        if self.kind not in ("scheduled", "predicted", "actual"):
            raise ValueError("invalid_evidence_kind")
        if type(self.retained) is not bool:
            raise ValueError("invalid_retained_flag")
        _utc(self.event_at)
        _utc(self.observed_at)


@dataclass(frozen=True, slots=True)
class EvidenceConnectionAssessment:
    """Unknown evidence has no numeric margin that could imply live certainty."""

    classification: Literal["unconfirmed", "unknown", "at_risk", "viable"]
    reason: str
    assessed_at: datetime
    minimum_minutes: int
    minutes_available: int | None = None
    margin_minutes: int | None = None
    inbound_kind: str | None = None
    outbound_kind: str | None = None
    inbound_event_at: datetime | None = None
    outbound_event_at: datetime | None = None

    def as_dict(self) -> dict:
        """Project the assessment without exposing provider service identifiers."""
        return {
            "classification": self.classification,
            "reason": self.reason,
            "assessed_at": self.assessed_at.isoformat(),
            "minimum_minutes": self.minimum_minutes,
            "minutes_available": self.minutes_available,
            "margin_minutes": self.margin_minutes,
            "inbound_kind": self.inbound_kind,
            "outbound_kind": self.outbound_kind,
            "inbound_event_at": (
                self.inbound_event_at.isoformat() if self.inbound_event_at else None
            ),
            "outbound_event_at": (
                self.outbound_event_at.isoformat() if self.outbound_event_at else None
            ),
        }


def departure_time_evidence(
    observation: RailObservation | None,
    *,
    station_identity: str,
    simulation_active: bool,
) -> StationTimeEvidence | None:
    """Bridge an existing matched live prediction without inventing a timestamp.

    The caller supplies the resolved departure station for the matched booking.
    Final service/station matching and freshness are checked by the assessor.
    """
    if type(simulation_active) is not bool:
        raise ValueError("explicit_simulation_state_required")
    if (
        simulation_active or observation is None
        or observation.classification != "provider_normalized"
        or not observation.provider_available or observation.cancelled
        or observation.retained or observation.freshness != "current"
        or not observation.service_identity or observation.predicted_departure is None
    ):
        return None
    return StationTimeEvidence(
        ServiceReference(observation.source, observation.service_identity),
        station_identity, "departure", "predicted",
        observation.predicted_departure, observation.observed_at,
    )


def _unusable_reason(
    evidence: StationTimeEvidence | None,
    *,
    expected_service: ServiceReference,
    station_identity: str,
    event: str,
    now: datetime,
    max_age: timedelta,
) -> str | None:
    if evidence is None:
        return "evidence_missing"
    if evidence.service != expected_service:
        return "service_mismatch"
    if evidence.station_identity != station_identity:
        return "station_mismatch"
    if evidence.event != event:
        return "event_mismatch"
    if evidence.retained:
        return "evidence_retained"
    if evidence.kind == "scheduled":
        return "schedule_only"
    age = now - _utc(evidence.observed_at)
    if age < timedelta(0):
        return "observation_in_future"
    if age > max_age:
        return "evidence_stale"
    instant = _utc(evidence.event_at)
    if evidence.kind == "actual" and instant > _utc(evidence.observed_at):
        return "actual_after_observation"
    if event == "departure" and evidence.kind == "actual":
        return "departure_already_recorded"
    if evidence.kind == "predicted" and instant < now:
        return "prediction_elapsed"
    return None


def assess_connection_evidence(
    *,
    confirmed: bool,
    inbound: StationTimeEvidence | None,
    outbound: StationTimeEvidence | None,
    expected_inbound: ServiceReference,
    expected_outbound: ServiceReference,
    station_identity: str,
    minimum_minutes: int,
    now: datetime,
    max_age: timedelta,
) -> EvidenceConnectionAssessment:
    """Assess only confirmed pairs with fresh, correctly matched live evidence.

    Freshness is a caller-supplied policy, not a new provider polling cadence.
    A negative margin means at risk, never confirmed missed.
    """
    now = _utc(now)
    if type(confirmed) is not bool:
        raise ValueError("explicit_confirmation_required")
    if type(minimum_minutes) is not int or not 0 <= minimum_minutes <= 1440:
        raise ValueError("invalid_transfer_allowance")
    if not isinstance(max_age, timedelta) or max_age <= timedelta(0):
        raise ValueError("positive_freshness_window_required")
    if not isinstance(station_identity, str) or not station_identity.strip():
        raise ValueError("resolved_station_required")
    if not all(
        isinstance(reference, ServiceReference)
        for reference in (expected_inbound, expected_outbound)
    ):
        raise ValueError("matched_service_reference_required")
    if not confirmed:
        return EvidenceConnectionAssessment(
            "unconfirmed", "confirmation_required", now, minimum_minutes
        )
    for side, evidence, service, event in (
        ("inbound", inbound, expected_inbound, "arrival"),
        ("outbound", outbound, expected_outbound, "departure"),
    ):
        reason = _unusable_reason(
            evidence, expected_service=service, station_identity=station_identity,
            event=event, now=now, max_age=max_age,
        )
        if reason:
            return EvidenceConnectionAssessment(
                "unknown", f"{side}_{reason}", now, minimum_minutes
            )
    # Both records have been validated above, including their station/event types.
    assert inbound is not None and outbound is not None
    risk = assess_connection(
        inbound_arrival=inbound.event_at,
        outbound_departure=outbound.event_at,
        minimum_minutes=minimum_minutes,
    )
    return EvidenceConnectionAssessment(
        "at_risk" if risk.classification == "at_risk" else "viable",
        "below_transfer_allowance" if risk.classification == "at_risk"
        else "meets_transfer_allowance",
        now, minimum_minutes, risk.minutes_available,
        risk.minutes_available - minimum_minutes, inbound.kind, outbound.kind,
        inbound_event_at=inbound.event_at, outbound_event_at=outbound.event_at,
    )
