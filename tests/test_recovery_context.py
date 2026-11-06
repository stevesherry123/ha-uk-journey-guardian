"""Recovery scope follows confirmed connections, never the last calendar event."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.journey_guardian.connection_store import ConfirmedConnection
from custom_components.journey_guardian.recovery import RecoveryRouteError
from custom_components.journey_guardian.recovery_context import (
    build_user_recovery_context,
)
from custom_components.journey_guardian.travel_plan import RetainedLeg

NOW = datetime(2026, 11, 6, 9, tzinfo=UTC)


def booking(key, origin, destination, dep, arr):
    return RetainedLeg(
        key * 64, (NOW + timedelta(minutes=dep)).isoformat(),
        (NOW + timedelta(minutes=arr)).isoformat(), origin, destination,
        NOW.isoformat(), NOW.isoformat(),
    )


A = booking("a", "Example Central", "Example Junction", 10, 40)
B = booking("b", "Example Junction", "Sample Harbour", 55, 90)
RETURN = booking("c", "Sample Harbour", "Example Central", 180, 240)
CONNECTION = ConfirmedConnection(
    A.booking_id, B.booking_id, NOW.isoformat(), (NOW + timedelta(hours=3)).isoformat()
)


def build(bookings=(A, B, RETURN), confirmations=(CONNECTION,), **changes):
    return build_user_recovery_context(bookings, confirmations, **({
        "affected_booking_id": A.booking_id, "final_booking_id": B.booking_id,
        "confirmed_origin_code": "EXC", "origin_confirmed_at": NOW, "ready_at": NOW,
        "resolved_stations": {"sample harbour": "SMP"}, "now": NOW,
        "max_age": timedelta(minutes=5), "calendar_healthy": True,
        "plan_truncated": False, "simulation_active": False,
    } | changes))


def test_final_destination_comes_from_confirmed_chain_not_unrelated_return():
    context = build()
    assert context.request.final_destination_code == "SMP"
    assert context.connected_booking_ids == (A.booking_id, B.booking_id)
    assert context.affected_booking_ids == (A.booking_id, B.booking_id)
    assert context.request.origin_source == "user_confirmed"
    assert context.valid_until == NOW + timedelta(minutes=5)


def test_disrupted_final_leg_keeps_upstream_baseline_without_superseding_it():
    context = build(affected_booking_id=B.booking_id)
    assert context.connected_booking_ids == (A.booking_id, B.booking_id)
    assert context.affected_booking_ids == (B.booking_id,)


@pytest.mark.parametrize("changes", [
    {"final_booking_id": RETURN.booking_id}, {"final_booking_id": A.booking_id},
    {"affected_booking_id": "d" * 64}, {"calendar_healthy": False},
    {"plan_truncated": True}, {"simulation_active": True},
    {"origin_confirmed_at": NOW - timedelta(minutes=6)},
    {"origin_confirmed_at": NOW + timedelta(minutes=1)},
    {"resolved_stations": {}}, {"confirmed_origin_code": "GPS".lower()},
])
def test_unsafe_or_incomplete_context_is_rejected(changes):
    with pytest.raises(RecoveryRouteError):
        build(**changes)


@pytest.mark.parametrize("records", [(), (A, RETURN), (A, B, B)])
def test_missing_or_duplicate_bookings_do_not_recover_a_partial_chain(records):
    with pytest.raises(RecoveryRouteError):
        build(bookings=records)


def test_unconfirmed_or_expired_connection_cannot_supply_destination():
    with pytest.raises(RecoveryRouteError):
        build(confirmations=())
    expired = replace(CONNECTION, expires_at=NOW.isoformat(),
                      confirmed_at=(NOW - timedelta(minutes=10)).isoformat())
    with pytest.raises(RecoveryRouteError):
        build(confirmations=(expired,))


def test_booking_edit_does_not_inherit_confirmation():
    with pytest.raises(RecoveryRouteError):
        build(bookings=(A, replace(B, booking_id="d" * 64), RETURN))


def test_changed_station_or_overlapping_bookings_invalidates_chain():
    for edited in (replace(B, origin="Other station"),
                   replace(B, departure=(NOW + timedelta(minutes=30)).isoformat())):
        with pytest.raises(RecoveryRouteError):
            build(bookings=(A, edited, RETURN))


def test_forked_confirmation_does_not_choose_one_destination():
    fork = replace(CONNECTION, outbound_id=RETURN.booking_id)
    with pytest.raises(RecoveryRouteError):
        build(confirmations=(CONNECTION, fork))


def test_affected_removed_booking_is_rejected_without_rewriting_baseline():
    with pytest.raises(RecoveryRouteError):
        build(bookings=(A, replace(B, in_latest_response=False), RETURN))
    assert B.in_latest_response is True


def test_elapsed_upstream_booking_can_remain_in_original_baseline():
    elapsed = replace(A, in_latest_response=False,
                      departure=(NOW - timedelta(minutes=60)).isoformat(),
                      arrival=(NOW - timedelta(minutes=30)).isoformat())
    context = build(bookings=(elapsed, B, RETURN),
                    affected_booking_id=B.booking_id)
    assert context.connected_booking_ids == (A.booking_id, B.booking_id)


def test_explicit_final_booking_cannot_truncate_a_longer_confirmed_chain():
    c = booking("d", "Sample Harbour", "Final Station", 105, 140)
    next_connection = replace(CONNECTION, inbound_id=B.booking_id,
                              outbound_id=c.booking_id)
    with pytest.raises(RecoveryRouteError):
        build(bookings=(A, B, c), confirmations=(CONNECTION, next_connection))
    context = build(bookings=(A, B, c), confirmations=(CONNECTION, next_connection),
                    final_booking_id=c.booking_id,
                    resolved_stations={"final station": "FIN"})
    assert context.request.final_destination_code == "FIN"
    assert context.affected_booking_ids == (A.booking_id, B.booking_id, c.booking_id)


def test_removed_future_upstream_leg_does_not_prove_a_connected_journey():
    with pytest.raises(RecoveryRouteError):
        build(bookings=(replace(A, in_latest_response=False), B, RETURN),
              affected_booking_id=B.booking_id)


def test_new_competing_calendar_booking_requires_connection_review():
    competing = booking("e", "Other station", "Other destination", 45, 70)
    with pytest.raises(RecoveryRouteError):
        build(bookings=(A, competing, B, RETURN))


def test_confirmation_cycle_is_bounded_and_rejected():
    reverse = replace(CONNECTION, inbound_id=B.booking_id, outbound_id=A.booking_id)
    with pytest.raises(RecoveryRouteError):
        build(confirmations=(CONNECTION, reverse))
