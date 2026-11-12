"""Provider-neutral end-to-end recovery contract; no search or adoption actions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .connection import TransferAllowance, resolve_transfer_allowance
from .connection_evidence import StationTimeEvidence


class RecoveryRouteError(ValueError):
    """Expose a stable rejection reason without itinerary details."""


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise RecoveryRouteError("timezone_required")
    return value.astimezone(UTC)


def _station(code: str) -> None:
    if (
        not isinstance(code, str)
        or len(code) != 3
        or not code.isascii()
        or not code.isalpha()
        or code != code.upper()
    ):
        raise RecoveryRouteError("resolved_station_required")


@dataclass(frozen=True, slots=True)
class RecoveryRequest:
    """Use the confirmed connected journey's destination, not the day's last event."""

    journey_id: str
    origin_code: str
    final_destination_code: str
    origin_source: str
    origin_observed_at: datetime
    ready_at: datetime
    destination_confirmed: bool

    def __post_init__(self):
        _station(self.origin_code)
        _station(self.final_destination_code)
        if self.origin_code == self.final_destination_code:
            raise RecoveryRouteError("already_at_destination")
        if (
            not isinstance(self.journey_id, str)
            or not self.journey_id.strip()
            or len(self.journey_id) > 256
        ):
            raise RecoveryRouteError("connected_journey_required")
        if self.origin_source not in ("provider_confirmed", "user_confirmed"):
            raise RecoveryRouteError("confirmed_recovery_origin_required")
        if self.destination_confirmed is not True:
            raise RecoveryRouteError("confirmed_final_destination_required")
        _utc(self.origin_observed_at)
        _utc(self.ready_at)


@dataclass(frozen=True, slots=True)
class RecoveryLeg:
    """Scheduled baseline plus explicitly matched prediction for each endpoint."""

    origin_code: str
    destination_code: str
    scheduled_departure: datetime
    scheduled_arrival: datetime
    departure: StationTimeEvidence
    arrival: StationTimeEvidence
    cancelled: bool


@dataclass(frozen=True, slots=True)
class RecoveryTransfer:
    station_code: str
    minutes_available: int
    minutes_required: int
    allowance_source: str


@dataclass(frozen=True, slots=True)
class RecoveryRoute:
    """Complete assessed option, not a booking or a promise of ticket acceptance."""

    option_id: str
    revision: str
    request: RecoveryRequest
    legs: tuple[RecoveryLeg, ...]
    transfers: tuple[RecoveryTransfer, ...]
    checked_at: datetime
    valid_until: datetime
    ticket_acceptance: str = field(default="unknown", init=False)


def _fresh(evidence: StationTimeEvidence, now: datetime, max_age: timedelta):
    if not isinstance(evidence, StationTimeEvidence):
        raise RecoveryRouteError("station_prediction_required")
    if evidence.retained or evidence.kind != "predicted":
        raise RecoveryRouteError("live_prediction_required")
    age = now - _utc(evidence.observed_at)
    if not timedelta(0) <= age <= max_age:
        raise RecoveryRouteError("prediction_not_current")


def build_recovery_route(
    request: RecoveryRequest,
    legs: Sequence[RecoveryLeg],
    *,
    now: datetime,
    max_age: timedelta,
    max_changes: int,
    max_wait: timedelta,
    max_duration: timedelta,
    station_allowances: Mapping[str, TransferAllowance] | None = None,
    global_minutes: int = 10,
) -> RecoveryRoute:
    """Reject incomplete, disconnected, stale or unachievable candidate routes.

    All limits are explicit inputs; this does not assert a provider can search
    this many changes. Saved station-name preferences must be resolved to station
    codes by the caller before supplying station_allowances.
    """
    now = _utc(now)
    if not isinstance(request, RecoveryRequest):
        raise RecoveryRouteError("recovery_request_required")
    if not isinstance(max_age, timedelta) or max_age <= timedelta(0):
        raise RecoveryRouteError("positive_freshness_window_required")
    if type(max_changes) is not int or not 0 <= max_changes <= 8:
        raise RecoveryRouteError("bounded_change_limit_required")
    if not timedelta(0) <= now - _utc(request.origin_observed_at) <= max_age:
        raise RecoveryRouteError("recovery_origin_not_current")
    if (
        not isinstance(max_wait, timedelta)
        or max_wait < timedelta(0)
        or not isinstance(max_duration, timedelta)
        or max_duration <= timedelta(0)
    ):
        raise RecoveryRouteError("bounded_time_limits_required")
    if not isinstance(legs, Sequence) or not 1 <= len(legs) <= max_changes + 1:
        raise RecoveryRouteError("unsupported_leg_count")
    legs = tuple(legs)
    if not all(isinstance(leg, RecoveryLeg) for leg in legs):
        raise RecoveryRouteError("recovery_leg_required")
    if legs[0].origin_code != request.origin_code:
        raise RecoveryRouteError("wrong_recovery_origin")
    if legs[-1].destination_code != request.final_destination_code:
        raise RecoveryRouteError("final_destination_not_reached")
    if type(global_minutes) is not int or not 0 <= global_minutes <= 1440:
        raise RecoveryRouteError("invalid_transfer_allowance")
    if station_allowances is not None and not isinstance(station_allowances, Mapping):
        raise RecoveryRouteError("invalid_transfer_preferences")
    fallback = resolve_transfer_allowance(global_minutes=global_minutes)
    preferences = station_allowances or {}
    if len(preferences) > 64:
        raise RecoveryRouteError("bounded_station_preferences_required")
    for code in preferences:
        _station(code)
    transfers, baseline, revision = [], [], []
    validity = [request.origin_observed_at + max_age]
    visited = {request.origin_code}
    seen_services = set()
    for index, leg in enumerate(legs):
        _station(leg.origin_code)
        _station(leg.destination_code)
        if type(leg.cancelled) is not bool or leg.cancelled:
            raise RecoveryRouteError("cancelled_or_unverified_service")
        if leg.destination_code in visited:
            raise RecoveryRouteError("route_loop")
        visited.add(leg.destination_code)
        if _utc(leg.scheduled_arrival) <= _utc(leg.scheduled_departure):
            raise RecoveryRouteError("invalid_scheduled_leg")
        _fresh(leg.departure, now, max_age)
        _fresh(leg.arrival, now, max_age)
        if (
            leg.departure.event != "departure"
            or leg.arrival.event != "arrival"
            or leg.departure.station_identity != leg.origin_code
            or leg.arrival.station_identity != leg.destination_code
            or leg.departure.service != leg.arrival.service
        ):
            raise RecoveryRouteError("service_or_station_mismatch")
        service_key = (leg.departure.service.provider, leg.departure.service.identity)
        if service_key in seen_services:
            raise RecoveryRouteError("duplicate_service_leg")
        seen_services.add(service_key)
        departure, arrival = _utc(leg.departure.event_at), _utc(leg.arrival.event_at)
        if departure < max(now, _utc(request.ready_at)):
            raise RecoveryRouteError("departure_not_reachable")
        if arrival <= departure:
            raise RecoveryRouteError("invalid_predicted_leg")
        if index == 0 and departure > now + max_wait:
            raise RecoveryRouteError("initial_wait_exceeds_limit")
        if index:
            previous = legs[index - 1]
            if previous.destination_code != leg.origin_code:
                raise RecoveryRouteError("disconnected_transfer")
            allowance = preferences.get(leg.origin_code, fallback)
            if not isinstance(allowance, TransferAllowance) or allowance.source not in (
                "connection_override",
                "station_default",
                "global_fallback",
            ):
                raise RecoveryRouteError("invalid_transfer_allowance")
            if type(allowance.minutes) is not int or not 0 <= allowance.minutes <= 1440:
                raise RecoveryRouteError("invalid_transfer_allowance")
            available = int(
                (departure - _utc(previous.arrival.event_at)).total_seconds() // 60
            )
            if available < allowance.minutes:
                raise RecoveryRouteError("insufficient_transfer_time")
            transfers.append(
                RecoveryTransfer(
                    leg.origin_code, available, allowance.minutes, allowance.source
                )
            )
        validity.extend(
            (
                leg.departure.observed_at + max_age,
                leg.arrival.observed_at + max_age,
                departure,
            )
        )
        service = leg.departure.service
        baseline.append(
            [
                service.provider,
                service.identity,
                leg.origin_code,
                leg.destination_code,
                _utc(leg.scheduled_departure).isoformat(),
                _utc(leg.scheduled_arrival).isoformat(),
            ]
        )
        revision.append([departure.isoformat(), arrival.isoformat()])
    if (
        _utc(legs[-1].arrival.event_at) - _utc(legs[0].departure.event_at)
        > max_duration
    ):
        raise RecoveryRouteError("journey_duration_exceeds_limit")
    identity = hashlib.sha256(
        json.dumps(
            [
                request.journey_id,
                request.origin_code,
                request.final_destination_code,
                baseline,
            ],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    version = hashlib.sha256(
        json.dumps(
            [
                identity,
                revision,
                [
                    (item.station_code, item.minutes_required, item.allowance_source)
                    for item in transfers
                ],
            ],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return RecoveryRoute(
        identity,
        version,
        request,
        legs,
        tuple(transfers),
        now,
        min(_utc(value) for value in validity),
    )
