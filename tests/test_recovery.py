"""Only complete, fresh and achievable routes can become recovery options."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.journey_guardian.connection import TransferAllowance
from custom_components.journey_guardian.connection_evidence import (
    ServiceReference,
    StationTimeEvidence,
)
from custom_components.journey_guardian.recovery import (
    RecoveryLeg,
    RecoveryRequest,
    RecoveryRouteError,
    build_recovery_route,
)

NOW = datetime(2026, 11, 4, 10, tzinfo=UTC)
REQUEST = RecoveryRequest(
    "fictional-confirmed-journey", "EXC", "SMP", "provider_confirmed", NOW, NOW, True
)


def leg(origin, destination, depart, arrive, identity="service-a"):
    service = ServiceReference("example_provider", identity)
    departure = NOW + timedelta(minutes=depart)
    arrival = NOW + timedelta(minutes=arrive)
    return RecoveryLeg(
        origin,
        destination,
        departure,
        arrival,
        StationTimeEvidence(service, origin, "departure", "predicted", departure, NOW),
        StationTimeEvidence(service, destination, "arrival", "predicted", arrival, NOW),
        False,
    )


DIRECT = leg("EXC", "SMP", 10, 90)
SPLIT = (leg("EXC", "EXJ", 10, 40), leg("EXJ", "SMP", 55, 100, "service-b"))


def build(legs=(DIRECT,), **changes):
    params = {
        "now": NOW,
        "max_age": timedelta(minutes=5),
        "max_changes": 2,
        "max_wait": timedelta(hours=1),
        "max_duration": timedelta(hours=8),
    }
    request = changes.pop("request", REQUEST)
    return build_recovery_route(request, legs, **(params | changes))


def test_direct_route_reaches_confirmed_destination_with_unknown_ticket_acceptance():
    route = build()
    assert route.legs[-1].destination_code == REQUEST.final_destination_code
    assert route.ticket_acceptance == "unknown"
    assert not route.transfers
    assert route.valid_until == NOW + timedelta(minutes=5)


def test_split_route_records_transfer_allowance_and_full_endpoint():
    route = build(
        SPLIT, station_allowances={"EXJ": TransferAllowance(12, "station_default")}
    )
    assert len(route.legs) == 2
    assert route.transfers[0].minutes_available == 15
    assert route.transfers[0].minutes_required == 12
    assert route.transfers[0].allowance_source == "station_default"
    assert route.legs[-1].destination_code == "SMP"


def test_route_with_multiple_changes_is_supported_by_contract_not_provider_promise():
    route = build(
        (
            leg("EXC", "EXJ", 10, 30),
            leg("EXJ", "ABC", 45, 65, "service-b"),
            leg("ABC", "SMP", 80, 110, "service-c"),
        )
    )
    assert len(route.transfers) == 2
    assert all(item.allowance_source == "global_fallback" for item in route.transfers)


def test_interchange_only_recovery_is_rejected_instead_of_stranding_user():
    with pytest.raises(RecoveryRouteError, match="final_destination_not_reached"):
        build((SPLIT[0],))


def test_unrelated_final_booking_cannot_replace_confirmed_connected_endpoint():
    with pytest.raises(RecoveryRouteError, match="final_destination_not_reached"):
        build((leg("EXC", "OTH", 10, 90),))


def test_disconnected_stations_and_insufficient_transfer_are_rejected():
    with pytest.raises(RecoveryRouteError, match="disconnected_transfer"):
        build((SPLIT[0], leg("OTH", "SMP", 55, 100, "service-b")))
    with pytest.raises(RecoveryRouteError, match="insufficient_transfer_time"):
        build(
            SPLIT, station_allowances={"EXJ": TransferAllowance(20, "station_default")}
        )


def test_user_ready_time_and_current_time_must_allow_first_departure():
    with pytest.raises(RecoveryRouteError, match="departure_not_reachable"):
        build(request=replace(REQUEST, ready_at=NOW + timedelta(minutes=11)))
    with pytest.raises(RecoveryRouteError, match="departure_not_reachable"):
        build((leg("EXC", "SMP", -1, 90),))


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"kind": "scheduled"}, "live_prediction_required"),
        ({"kind": "actual"}, "live_prediction_required"),
        ({"retained": True}, "live_prediction_required"),
        ({"observed_at": NOW - timedelta(minutes=6)}, "prediction_not_current"),
        ({"observed_at": NOW + timedelta(seconds=1)}, "prediction_not_current"),
        ({"station_identity": "OTH"}, "service_or_station_mismatch"),
        ({"event": "arrival"}, "service_or_station_mismatch"),
        (
            {"service": ServiceReference("other", "service-a")},
            "service_or_station_mismatch",
        ),
    ],
)
def test_unusable_evidence_rejects_whole_route(changes, reason):
    with pytest.raises(RecoveryRouteError, match=reason):
        build((replace(DIRECT, departure=replace(DIRECT.departure, **changes)),))


def test_cancellation_and_origin_evidence_are_not_guessed():
    with pytest.raises(RecoveryRouteError, match="cancelled_or_unverified_service"):
        build((replace(DIRECT, cancelled=True),))
    with pytest.raises(RecoveryRouteError, match="confirmed_recovery_origin_required"):
        replace(REQUEST, origin_source="gps_proximity")
    with pytest.raises(
        RecoveryRouteError, match="confirmed_final_destination_required"
    ):
        replace(REQUEST, destination_confirmed=False)
    with pytest.raises(RecoveryRouteError, match="recovery_origin_not_current"):
        build(request=replace(REQUEST, origin_observed_at=NOW - timedelta(minutes=6)))


def test_origin_freshness_limits_option_lifetime():
    route = build(
        request=replace(REQUEST, origin_observed_at=NOW - timedelta(minutes=4))
    )
    assert route.valid_until == NOW + timedelta(minutes=1)


def test_provider_search_limit_is_explicit_and_no_partial_truncation_occurs():
    with pytest.raises(RecoveryRouteError, match="unsupported_leg_count"):
        build(SPLIT, max_changes=0)
    with pytest.raises(RecoveryRouteError, match="bounded_change_limit_required"):
        build(max_changes=True)


def test_option_identity_is_stable_but_revised_predictions_change_revision():
    original = build()
    updated = build(
        (
            replace(
                DIRECT,
                arrival=replace(
                    DIRECT.arrival,
                    event_at=DIRECT.arrival.event_at + timedelta(minutes=5),
                ),
            ),
        )
    )
    assert original.option_id == updated.option_id
    assert original.revision != updated.revision
    assert build().revision == original.revision


def test_partial_service_or_repeated_train_is_not_silently_coalesced():
    with pytest.raises(RecoveryRouteError, match="duplicate_service_leg"):
        build(
            (
                SPLIT[0],
                replace(
                    SPLIT[1],
                    departure=replace(
                        SPLIT[1].departure, service=SPLIT[0].departure.service
                    ),
                    arrival=replace(SPLIT[1].arrival, service=SPLIT[0].arrival.service),
                ),
            )
        )


def test_elapsed_time_across_autumn_clock_change_is_respected():
    zone = ZoneInfo("Europe/London")
    now = datetime(2026, 10, 25, 0, 40, tzinfo=UTC)
    service = ServiceReference("example_provider", "autumn-service")
    departure = datetime(2026, 10, 25, 1, 50, tzinfo=zone, fold=0)
    arrival = datetime(2026, 10, 25, 1, 10, tzinfo=zone, fold=1)
    item = RecoveryLeg(
        "EXC",
        "SMP",
        departure,
        arrival,
        StationTimeEvidence(service, "EXC", "departure", "predicted", departure, now),
        StationTimeEvidence(service, "SMP", "arrival", "predicted", arrival, now),
        False,
    )
    route = build(
        (item,), now=now, request=replace(REQUEST, origin_observed_at=now, ready_at=now)
    )
    assert route.legs[0].arrival.event_at.astimezone(UTC) > departure.astimezone(UTC)


def test_end_to_end_route_still_requires_bounded_wait_and_duration():
    with pytest.raises(RecoveryRouteError, match="initial_wait_exceeds_limit"):
        build((leg("EXC", "SMP", 61, 120),))
    with pytest.raises(RecoveryRouteError, match="journey_duration_exceeds_limit"):
        build((leg("EXC", "SMP", 10, 600),))
    with pytest.raises(RecoveryRouteError, match="bounded_time_limits_required"):
        build(max_duration=timedelta(0))


def test_empty_route_or_unbounded_iterator_is_rejected():
    for legs in ((), iter((DIRECT,))):
        with pytest.raises(RecoveryRouteError, match="unsupported_leg_count"):
            build(legs)


def test_unverified_cancellation_flag_cannot_be_treated_as_false():
    with pytest.raises(RecoveryRouteError, match="cancelled_or_unverified_service"):
        build((replace(DIRECT, cancelled=None),))


def test_transfer_preference_changes_revision_but_keeps_service_identity():
    first = build(SPLIT)
    second = build(
        SPLIT, station_allowances={"EXJ": TransferAllowance(12, "station_default")}
    )
    assert first.option_id == second.option_id
    assert first.revision != second.revision


def test_unresolved_station_preferences_are_not_silently_ignored():
    with pytest.raises(RecoveryRouteError, match="resolved_station_required"):
        build(
            SPLIT,
            station_allowances={
                "Example Junction": TransferAllowance(20, "station_default"),
            },
        )


def test_later_ready_time_cannot_move_the_search_wait_limit_into_future():
    with pytest.raises(RecoveryRouteError, match="initial_wait_exceeds_limit"):
        build(
            (leg("EXC", "SMP", 70, 150),),
            request=replace(REQUEST, ready_at=NOW + timedelta(minutes=30)),
        )
