"""Live connection risk must not be invented from stale or unrelated facts."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.journey_guardian.connection_evidence import (
    ServiceReference,
    StationTimeEvidence,
    assess_connection_evidence,
)

NOW = datetime(2026, 11, 4, 9, tzinfo=UTC)
INBOUND_SERVICE = ServiceReference("example_provider", "dated-incoming-service")
OUTBOUND_SERVICE = ServiceReference("example_provider", "dated-onward-service")
ARRIVAL = StationTimeEvidence(
    INBOUND_SERVICE, "EXJ", "arrival", "predicted", NOW + timedelta(minutes=20), NOW,
)
DEPARTURE = StationTimeEvidence(
    OUTBOUND_SERVICE, "EXJ", "departure", "predicted", NOW + timedelta(minutes=28), NOW,
)


def assess(**changes):
    parameters = {
        "confirmed": True,
        "inbound": ARRIVAL,
        "outbound": DEPARTURE,
        "expected_inbound": INBOUND_SERVICE,
        "expected_outbound": OUTBOUND_SERVICE,
        "station_identity": "EXJ",
        "minimum_minutes": 10,
        "now": NOW,
        "max_age": timedelta(minutes=5),
    }
    return assess_connection_evidence(**(parameters | changes))


def test_fresh_prediction_explains_risk_and_margin_without_claiming_missed():
    result = assess()
    assert result.classification == "at_risk"
    assert result.reason == "below_transfer_allowance"
    assert result.minutes_available == 8
    assert result.margin_minutes == -2
    assert result.inbound_kind == result.outbound_kind == "predicted"
    result = assess(inbound=replace(ARRIVAL, event_at=NOW + timedelta(minutes=30)))
    assert result.minutes_available == -2
    assert result.classification == "at_risk"


def test_delayed_onward_prediction_can_restore_required_margin():
    result = assess(outbound=replace(DEPARTURE, event_at=NOW + timedelta(minutes=35)))
    assert result.classification == "viable"
    assert result.minutes_available == 15
    assert result.margin_minutes == 5


def test_saved_template_or_unconfirmed_pair_cannot_produce_live_risk():
    result = assess(confirmed=False)
    assert result.classification == "unconfirmed"
    assert result.minutes_available is None


@pytest.mark.parametrize(("side", "field", "value", "reason"), [
    ("inbound", "kind", "scheduled", "schedule_only"),
    ("outbound", "kind", "scheduled", "schedule_only"),
    ("inbound", "retained", True, "evidence_retained"),
    ("outbound", "retained", True, "evidence_retained"),
    ("inbound", "station_identity", "OTHER", "station_mismatch"),
    ("outbound", "event", "arrival", "event_mismatch"),
    ("inbound", "service", OUTBOUND_SERVICE, "service_mismatch"),
    ("outbound", "service", ServiceReference("other", OUTBOUND_SERVICE.identity),
     "service_mismatch"),
    ("inbound", "observed_at", NOW - timedelta(minutes=6), "evidence_stale"),
    ("outbound", "observed_at", NOW + timedelta(seconds=1), "observation_in_future"),
    ("inbound", "event_at", NOW - timedelta(seconds=1), "prediction_elapsed"),
])
def test_unusable_evidence_produces_unknown_without_numeric_margin(
    side, field, value, reason
):
    evidence = ARRIVAL if side == "inbound" else DEPARTURE
    result = assess(**{side: replace(evidence, **{field: value})})
    assert result.classification == "unknown"
    assert result.reason == f"{side}_{reason}"
    assert result.minutes_available is None
    assert result.margin_minutes is None


@pytest.mark.parametrize("side", ["inbound", "outbound"])
def test_missing_evidence_is_unknown(side):
    result = assess(**{side: None})
    assert result.classification == "unknown"
    assert result.reason == f"{side}_evidence_missing"


def test_freshness_boundary_is_inclusive_but_does_not_reset_on_review():
    arrival = replace(ARRIVAL, observed_at=NOW - timedelta(minutes=5))
    assert assess(inbound=arrival).classification == "at_risk"
    assert assess(inbound=arrival, now=NOW + timedelta(seconds=1)).reason == (
        "inbound_evidence_stale"
    )


def test_actual_arrival_supported_but_future_actual_event_rejected():
    arrival = replace(ARRIVAL, kind="actual", event_at=NOW - timedelta(minutes=1))
    assert assess(inbound=arrival).classification == "viable"
    result = assess(inbound=replace(ARRIVAL, kind="actual"))
    assert result.reason == "inbound_actual_after_observation"


def test_clock_change_uses_elapsed_utc_time():
    london = ZoneInfo("Europe/London")
    now = datetime(2026, 10, 25, 0, 45, tzinfo=UTC)
    arrival = replace(ARRIVAL, observed_at=now,
                      event_at=datetime(2026, 10, 25, 1, 50, tzinfo=london, fold=0))
    departure = replace(DEPARTURE, observed_at=now,
                        event_at=datetime(2026, 10, 25, 1, 10, tzinfo=london, fold=1))
    result = assess(inbound=arrival, outbound=departure, now=now)
    assert result.minutes_available == 20
    assert result.classification == "viable"


@pytest.mark.parametrize("change", [
    {"confirmed": "yes"}, {"minimum_minutes": True}, {"minimum_minutes": -1},
    {"minimum_minutes": 1441}, {"max_age": timedelta(0)},
    {"now": NOW.replace(tzinfo=None)}, {"station_identity": ""},
    {"expected_inbound": None},
])
def test_invalid_assessment_contract_is_rejected(change):
    with pytest.raises(ValueError):
        assess(**change)


def test_projection_preserves_provenance_without_service_identifiers():
    data = assess().as_dict()
    assert data["assessed_at"] == NOW.isoformat()
    assert data["inbound_kind"] == "predicted"
    assert INBOUND_SERVICE.identity not in str(data)
    assert OUTBOUND_SERVICE.identity not in str(data)


def test_recorded_onward_departure_does_not_appear_as_live_viable_connection():
    result = assess(
        inbound=replace(ARRIVAL, kind="actual", event_at=NOW - timedelta(minutes=20)),
        outbound=replace(DEPARTURE, kind="actual", event_at=NOW - timedelta(minutes=5)),
    )
    assert result.classification == "unknown"
    assert result.reason == "outbound_departure_already_recorded"
    assert result.minutes_available is None


@pytest.mark.parametrize("field,value", [
    ("service", None), ("station_identity", ""), ("event", "boarding"),
    ("kind", "inferred"), ("retained", "false"),
    ("event_at", NOW.replace(tzinfo=None)), ("observed_at", "today"),
])
def test_malformed_provider_contract_rejected_before_assessment(field, value):
    with pytest.raises(ValueError):
        replace(ARRIVAL, **{field: value})


def test_service_identity_for_another_operating_day_cannot_match():
    result = assess(inbound=replace(
        ARRIVAL, service=ServiceReference(
            INBOUND_SERVICE.provider, "another-dated-service"
        )
    ))
    assert result.reason == "inbound_service_mismatch"


def live_departure():
    from custom_components.journey_guardian.models import RailObservation

    return RailObservation(
        "observed", "example_provider", "provider_normalized", NOW,
        NOW + timedelta(minutes=25), NOW + timedelta(minutes=28),
        3, False, 1, True, service_identity=OUTBOUND_SERVICE.identity,
    )


def test_existing_live_departure_bridge_keeps_original_timestamp_and_prediction():
    from custom_components.journey_guardian.connection_evidence import (
        departure_time_evidence,
    )

    observed = NOW - timedelta(minutes=4)
    evidence = departure_time_evidence(
        replace(live_departure(), observed_at=observed),
        station_identity="EXJ", simulation_active=False,
    )
    assert evidence.observed_at == observed
    assert evidence.event_at == DEPARTURE.event_at
    assert evidence.kind == "predicted"
    assert assess(outbound=evidence).classification == "at_risk"
    assert assess(outbound=evidence, now=NOW + timedelta(minutes=2)).reason == (
        "outbound_evidence_stale"
    )


@pytest.mark.parametrize("changes", [
    {"predicted_departure": None}, {"cancelled": True}, {"provider_available": False},
    {"retained": True}, {"freshness": "stale"}, {"service_identity": None},
    {"classification": "simulated_normalized"},
])
def test_departure_bridge_does_not_promote_unusable_or_schedule_only_data(changes):
    from custom_components.journey_guardian.connection_evidence import (
        departure_time_evidence,
    )

    assert departure_time_evidence(
        replace(live_departure(), **changes),
        station_identity="EXJ", simulation_active=False,
    ) is None


def test_simulation_cannot_be_promoted_to_live_evidence():
    from custom_components.journey_guardian.connection_evidence import (
        departure_time_evidence,
    )

    assert departure_time_evidence(
        live_departure(), station_identity="EXJ", simulation_active=True
    ) is None
