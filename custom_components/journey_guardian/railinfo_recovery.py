"""Bounded mapping of Railinfo responses to complete recovery options.

This pure adapter makes no requests and never changes a tracked journey.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .connection import TransferAllowance
from .connection_evidence import ServiceReference
from .rail import service_identity
from .railinfo_arrival import _clock, _instant, normalize_railinfo_prediction
from .recovery import (
    RecoveryLeg,
    RecoveryRequest,
    RecoveryRoute,
    RecoveryRouteError,
    _station,
    build_recovery_route,
)


@dataclass(frozen=True, slots=True)
class RailinfoRecoveryResult:
    """No options means none validated in this response, never no route exists."""

    status: str
    routes: tuple[RecoveryRoute, ...] = ()
    rejected_candidates: int = 0
    supported_changes: int = 1


def _legs(journey: Mapping, *, day, observed_at: datetime) -> tuple[RecoveryLeg, ...]:
    raw = journey.get("legs")
    changes = journey.get("changes")
    if (
        type(changes) is not int
        or changes not in (0, 1)
        or not isinstance(raw, list)
        or len(raw) != changes + 1
        or journey.get("status") not in ("on_time", "late")
    ):
        raise RecoveryRouteError("unsupported_candidate")
    zone = ZoneInfo("Europe/London")
    legs = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise RecoveryRouteError("invalid_leg")
        _station(item.get("from_crs"))
        _station(item.get("to_crs"))
        dep_clock, arr_clock = _clock(item.get("dep")), _clock(item.get("arr"))
        headcode = item.get("headcode")
        if dep_clock is None or arr_clock is None or not isinstance(headcode, str):
            raise RecoveryRouteError("missing_schedule_or_service")
        departure = _instant(day, dep_clock, zone)
        arrival = _instant(day, arr_clock, zone)
        # This first adapter deliberately excludes rollover without dated legs.
        if departure is None or arrival is None or arrival <= departure:
            raise RecoveryRouteError("unsupported_service_day")
        service = ServiceReference("railinfo", service_identity(headcode, day))
        direct = {
            "date": day.isoformat(), "is_today": True,
            "journeys": [{"changes": 0, "status": journey["status"], "legs": [item]}],
        }
        evidence = {}
        for event in ("departure", "arrival"):
            evidence[event] = normalize_railinfo_prediction(
                direct,
                origin_code=item.get("from_crs"),
                destination_code=item.get("to_crs"),
                expected_service=service,
                booked_departure=departure,
                booked_arrival=arrival,
                observed_at=observed_at,
                event=event,
            )
        if evidence["departure"] is None or evidence["arrival"] is None:
            raise RecoveryRouteError("missing_live_endpoint_prediction")
        legs.append(RecoveryLeg(
            item.get("from_crs"), item.get("to_crs"), departure, arrival,
            evidence["departure"], evidence["arrival"], False,
        ))
    return tuple(legs)


def _candidate_key(journey):
    """Recognize duplicate scheduled routes even when one copy is cancelled."""
    if not isinstance(journey, Mapping):
        return None
    legs = journey.get("legs")
    if not isinstance(legs, list) or not 1 <= len(legs) <= 2:
        return None
    key = []
    for leg in legs:
        if not isinstance(leg, Mapping):
            return None
        values = tuple(leg.get(field) for field in (
            "from_crs", "to_crs", "dep", "arr", "headcode",
        ))
        if not all(isinstance(value, str) for value in values):
            return None
        key.append(values)
    return tuple(key)


def normalize_railinfo_recovery(
    payload: Mapping[str, Any],
    request: RecoveryRequest,
    *,
    observed_at: datetime,
    now: datetime,
    max_age: timedelta,
    max_wait: timedelta,
    max_duration: timedelta,
    station_allowances: Mapping[str, TransferAllowance] | None = None,
    global_minutes: int = 10,
) -> RailinfoRecoveryResult:
    """Validate up to 40 direct/one-change candidates, preserving observation age.

    A malformed envelope or oversized response is rejected whole. Individual
    unsupported candidates are counted and cannot become partial options.
    Duplicate scheduled candidates are excluded, including conflicting statuses.
    """
    if observed_at.utcoffset() is None or now.utcoffset() is None:
        raise ValueError("timezone_required")
    if not isinstance(max_age, timedelta) or max_age <= timedelta(0):
        raise ValueError("positive_freshness_window_required")
    if not timedelta(0) <= now.astimezone(UTC) - observed_at.astimezone(UTC) <= max_age:
        return RailinfoRecoveryResult("stale_response")
    day = observed_at.astimezone(ZoneInfo("Europe/London")).date()
    if (
        not isinstance(payload, Mapping)
        or payload.get("date") != day.isoformat()
        or payload.get("is_today") is not True
        or not isinstance(payload.get("journeys"), list)
        or len(payload["journeys"]) > 40
    ):
        return RailinfoRecoveryResult("invalid_response")
    counts = Counter(_candidate_key(item) for item in payload["journeys"])
    options, conflicts = {}, set()
    rejected = 0
    for journey in payload["journeys"]:
        try:
            key = _candidate_key(journey)
            if key is not None and counts[key] > 1:
                raise RecoveryRouteError("ambiguous_duplicate_candidate")
            if not isinstance(journey, Mapping):
                raise RecoveryRouteError("invalid_candidate")
            route = build_recovery_route(
                request, _legs(journey, day=day, observed_at=observed_at),
                now=now, max_age=max_age, max_changes=1, max_wait=max_wait,
                max_duration=max_duration, station_allowances=station_allowances,
                global_minutes=global_minutes,
            )
        except RecoveryRouteError:
            rejected += 1
            continue
        previous = options.get(route.option_id)
        if previous is not None and previous.revision != route.revision:
            conflicts.add(route.option_id)
        options[route.option_id] = route
    routes = tuple(sorted(
        (route for key, route in options.items() if key not in conflicts),
        key=lambda route: (
            route.legs[-1].arrival.event_at.astimezone(UTC),
            len(route.legs), route.option_id,
        ),
    ))
    return RailinfoRecoveryResult(
        "options_available" if routes else "no_complete_route_in_response",
        routes, rejected + len(conflicts),
    )
