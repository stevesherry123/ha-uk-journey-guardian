"""Build recovery scope from exact confirmed bookings and a user-confirmed origin."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from .connection_preferences import station_key
from .connection_store import ConfirmedConnection
from .recovery import RecoveryRequest, RecoveryRouteError, _station, _utc
from .travel_plan import RetainedLeg


@dataclass(frozen=True, slots=True)
class RecoveryContext:
    """Immutable booked baseline for search and a later supersession preview."""

    request: RecoveryRequest
    connected_booking_ids: tuple[str, ...]
    affected_booking_ids: tuple[str, ...]
    valid_until: datetime


def build_user_recovery_context(
    bookings: Sequence[RetainedLeg],
    confirmations: Sequence[ConfirmedConnection],
    *,
    affected_booking_id: str,
    final_booking_id: str,
    confirmed_origin_code: str,
    origin_confirmed_at: datetime,
    ready_at: datetime,
    resolved_stations: Mapping[str, str],
    now: datetime,
    max_age: timedelta,
    calendar_healthy: bool,
    plan_truncated: bool,
    simulation_active: bool,
) -> RecoveryContext:
    """Require a complete unambiguous confirmed chain and explicit final booking.

    This is an internal boundary for a future explicit user command. It does not
    infer a current station from a booking, GPS or elapsed scheduled arrival.
    Resolved stations map normalized exact display names to verified CRS codes.
    Provider-confirmed disruption origins need their own evidence adapter.
    """
    now = _utc(now)
    if calendar_healthy is not True or plan_truncated is not False:
        raise RecoveryRouteError("complete_current_calendar_required")
    if simulation_active is not False:
        raise RecoveryRouteError("simulation_excluded")
    if not isinstance(max_age, timedelta) or max_age <= timedelta(0):
        raise RecoveryRouteError("positive_freshness_window_required")
    origin_confirmed_at = _utc(origin_confirmed_at)
    if not timedelta(0) <= now - origin_confirmed_at <= max_age:
        raise RecoveryRouteError("recovery_origin_not_current")
    _station(confirmed_origin_code)
    if (
        not isinstance(bookings, Sequence) or not 1 <= len(bookings) <= 64
        or not isinstance(confirmations, Sequence) or len(confirmations) > 64
    ):
        raise RecoveryRouteError("bounded_plan_required")
    by_id = {}
    for booking in bookings:
        if not isinstance(booking, RetainedLeg) or booking.booking_id in by_id:
            raise RecoveryRouteError("unambiguous_bookings_required")
        if (
            not isinstance(booking.booking_id, str) or len(booking.booking_id) != 64
            or any(char not in "0123456789abcdef" for char in booking.booking_id)
        ):
            raise RecoveryRouteError("exact_bookings_required")
        by_id[booking.booking_id] = booking
    if affected_booking_id not in by_id or final_booking_id not in by_id:
        raise RecoveryRouteError("exact_bookings_required")
    incoming, outgoing = {}, {}
    edges = {}
    for connection in confirmations:
        if not isinstance(connection, ConfirmedConnection):
            raise RecoveryRouteError("confirmed_connections_required")
        connection.validate()
        key = (connection.inbound_id, connection.outbound_id)
        if key in edges:
            raise RecoveryRouteError("ambiguous_connection")
        edges[key] = connection
        incoming.setdefault(connection.outbound_id, []).append(connection.inbound_id)
        outgoing.setdefault(connection.inbound_id, []).append(connection.outbound_id)

    # Walk backwards first so the affected final leg still has a connected scope.
    start, seen = affected_booking_id, set()
    while incoming.get(start):
        if start in seen or len(incoming[start]) != 1:
            raise RecoveryRouteError("ambiguous_connection_chain")
        seen.add(start)
        start = incoming[start][0]
    chain, seen, validity = [], set(), [origin_confirmed_at + max_age]
    current = start
    while True:
        if current in seen or current not in by_id:
            raise RecoveryRouteError("incomplete_connection_chain")
        seen.add(current)
        booking = by_id[current]
        if len(incoming.get(current, [])) > 1 or len(outgoing.get(current, [])) > 1:
            raise RecoveryRouteError("ambiguous_connection_chain")
        departure = _utc(datetime.fromisoformat(booking.departure))
        if booking.arrival is None:
            raise RecoveryRouteError("booked_arrival_required")
        arrival = _utc(datetime.fromisoformat(booking.arrival))
        if arrival <= departure or now >= booking.expiry:
            raise RecoveryRouteError("invalid_or_expired_booking")
        if booking.in_latest_response is not True and arrival > now:
            raise RecoveryRouteError("removed_future_booking")
        chain.append(current)
        next_ids = outgoing.get(current, [])
        if not next_ids:
            break
        next_id = next_ids[0]
        if next_id not in by_id:
            raise RecoveryRouteError("incomplete_connection_chain")
        connection = edges[(current, next_id)]
        confirmed_at = _utc(datetime.fromisoformat(connection.confirmed_at))
        expires_at = _utc(datetime.fromisoformat(connection.expires_at))
        if not confirmed_at <= now < expires_at:
            raise RecoveryRouteError("current_confirmation_required")
        validity.append(expires_at)
        following = by_id[next_id]
        if (
            station_key(booking.destination) != station_key(following.origin)
            or arrival > _utc(datetime.fromisoformat(following.departure))
        ):
            raise RecoveryRouteError("disconnected_bookings")
        next_departure = _utc(datetime.fromisoformat(following.departure))
        if any(
            other.booking_id not in (current, next_id)
            and other.in_latest_response is True
            and departure <= _utc(datetime.fromisoformat(other.departure))
            <= next_departure
            for other in bookings
        ):
            raise RecoveryRouteError("competing_calendar_booking")
        current = next_id
    if len(chain) < 2 or chain[-1] != final_booking_id:
        raise RecoveryRouteError("confirmed_final_booking_required")
    affected = tuple(chain[chain.index(affected_booking_id):])
    # Elapsed upstream bookings may have left the calendar's upcoming response.
    # Every affected booking must still be present to avoid reviving an edit.
    if any(by_id[key].in_latest_response is not True for key in affected):
        raise RecoveryRouteError("affected_bookings_not_current")
    final = by_id[final_booking_id]
    if not isinstance(resolved_stations, Mapping) or len(resolved_stations) > 64:
        raise RecoveryRouteError("resolved_station_mapping_required")
    destination = resolved_stations.get(station_key(final.destination))
    _station(destination)
    identity = hashlib.sha256("|".join(chain).encode()).hexdigest()
    request = RecoveryRequest(
        identity, confirmed_origin_code, destination, "user_confirmed",
        origin_confirmed_at, ready_at, True,
    )
    return RecoveryContext(request, tuple(chain), affected, min(validity))
