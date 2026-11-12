"""Fictional records preserve the verified field shape, never real itineraries."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.journey_guardian.connection_evidence import ServiceReference
from custom_components.journey_guardian.rail import service_identity
from custom_components.journey_guardian.railinfo_arrival import (
    normalize_railinfo_arrival,
)

NOW = datetime(2026, 11, 4, 9, tzinfo=UTC)
DEPARTURE = NOW + timedelta(hours=1)
ARRIVAL = NOW + timedelta(hours=2)
SERVICE = ServiceReference("railinfo", service_identity("1A23", NOW.date()))


def payload():
    return {"date": "2026-11-04", "is_today": True, "journeys": [{
        "changes": 0, "status": "on_time", "legs": [{
            "from_crs": "EXC", "to_crs": "EXJ", "dep": "1000", "arr": "1100",
            "expected_dep": "1000", "expected_arr": "1108", "headcode": "1A23",
            "mode": "train", "status": "late", "status_source": "darwin",
        }],
    }]}


def normalize(data=None, **changes):
    return normalize_railinfo_arrival(payload() if data is None else data, **({
        "origin_code": "EXC", "destination_code": "EXJ", "expected_service": SERVICE,
        "booked_departure": DEPARTURE, "booked_arrival": ARRIVAL,
        "observed_at": NOW,
    } | changes))


def test_explicit_live_arrival_uses_arrival_field_and_original_observation_time():
    result = normalize()
    assert result.event_at == ARRIVAL + timedelta(minutes=8)
    assert result.observed_at == NOW
    assert result.station_identity == "EXJ"
    assert result.service == SERVICE
    assert (result.event, result.kind) == ("arrival", "predicted")


def test_explicit_on_time_arrival_remains_prediction_not_actual_arrival():
    data = payload()
    leg = data["journeys"][0]["legs"][0]
    leg.update(expected_arr="1100", status="on_time")
    result = normalize(data)
    assert result.event_at == ARRIVAL
    assert result.kind == "predicted"


@pytest.mark.parametrize("changes", [
    {"expected_arr": None}, {"expected_arr": ""}, {"expected_arr": "2500"},
    {"expected_arr": "11:08"}, {"expected_arr": 1108},
    {"status_source": "timetable"}, {"status_source": None},
    {"status": "cancelled"}, {"cancelled": True}, {"mode": "bus"},
    {"headcode": "OTHER"}, {"from_crs": "OTHER"}, {"to_crs": "OTHER"},
    {"dep": "1001"}, {"arr": "1101"},
])
def test_unsupported_or_mismatched_leg_never_produces_live_arrival(changes):
    data = payload()
    data["journeys"][0]["legs"][0].update(changes)
    assert normalize(data) is None


def test_departure_delay_is_not_used_to_invent_arrival_prediction():
    data = payload()
    leg = data["journeys"][0]["legs"][0]
    leg.pop("expected_arr")
    leg.update(expected_dep="1020", delay_min=20)
    assert normalize(data) is None


@pytest.mark.parametrize("changes", [
    {"date": "2026-11-03"}, {"is_today": False}, {"is_today": "true"},
    {"journeys": None},
])
def test_response_day_or_live_provenance_is_required(changes):
    assert normalize(payload() | changes) is None


def test_duplicate_or_multi_leg_matches_are_not_assumed_unique_direct_services():
    data = payload()
    data["journeys"].append(deepcopy(data["journeys"][0]))
    assert normalize(data) is None
    data = payload()
    data["journeys"][0]["changes"] = 1
    assert normalize(data) is None


def test_midnight_prediction_rollover_uses_the_booked_arrival_day():
    departure = datetime(2026, 11, 4, 23, tzinfo=UTC)
    arrival = datetime(2026, 11, 5, 0, 10, tzinfo=UTC)
    data = payload()
    data["journeys"][0]["legs"][0].update(dep="2300", arr="0010", expected_arr="0025")
    result = normalize(data, booked_departure=departure, booked_arrival=arrival)
    assert result.event_at == arrival + timedelta(minutes=15)


def test_ambiguous_autumn_arrival_clock_requires_explicit_provider_offsets():
    zone = ZoneInfo("Europe/London")
    departure = datetime(2026, 10, 25, 0, 30, tzinfo=zone)
    arrival = datetime(2026, 10, 25, 1, 10, tzinfo=zone, fold=0)
    data = payload() | {"date": "2026-10-25"}
    data["journeys"][0]["legs"][0].update(dep="0030", arr="0110", expected_arr="0115")
    assert normalize(
        data, booked_departure=departure, booked_arrival=arrival,
        expected_service=ServiceReference(
            "railinfo", service_identity("1A23", departure.date())
        ),
        observed_at=departure - timedelta(minutes=10),
    ) is None


def test_foreign_provider_identity_and_timezone_free_inputs_are_rejected():
    foreign_service = ServiceReference("other", SERVICE.identity)
    assert normalize(expected_service=foreign_service) is None
    with pytest.raises(ValueError, match="timezone_required"):
        normalize(observed_at=NOW.replace(tzinfo=None))


def test_conflicting_cancelled_duplicate_cannot_hide_behind_valid_record():
    data = payload()
    duplicate = deepcopy(data["journeys"][0])
    duplicate["status"] = "cancelled"
    data["journeys"].append(duplicate)
    assert normalize(data) is None


def test_summer_utc_booking_is_compared_to_provider_local_clocks():
    departure = datetime(2026, 7, 4, 9, tzinfo=UTC)
    arrival = departure + timedelta(hours=1)
    data = payload() | {"date": "2026-07-04"}
    result = normalize(
        data, booked_departure=departure, booked_arrival=arrival,
        expected_service=ServiceReference(
            "railinfo", service_identity("1A23", departure.date())
        ),
        observed_at=departure - timedelta(minutes=10),
    )
    assert result.event_at.astimezone(UTC) == arrival + timedelta(minutes=8)


def test_prediction_does_not_claim_to_be_live_for_another_observation_day():
    assert normalize(observed_at=NOW + timedelta(days=1)) is None


def test_mapped_arrival_drives_risk_only_with_matching_fresh_onward_evidence():
    from custom_components.journey_guardian.connection_evidence import (
        StationTimeEvidence,
        assess_connection_evidence,
    )

    incoming = normalize()
    onward_service = ServiceReference("railinfo", "fictional-dated-onward")
    onward = StationTimeEvidence(
        onward_service, "EXJ", "departure", "predicted",
        ARRIVAL + timedelta(minutes=15), NOW,
    )
    parameters = {
        "confirmed": True, "inbound": incoming, "outbound": onward,
        "expected_inbound": SERVICE, "expected_outbound": onward_service,
        "station_identity": "EXJ", "minimum_minutes": 10,
        "now": NOW, "max_age": timedelta(minutes=5),
    }
    risk = assess_connection_evidence(**parameters)
    assert risk.classification == "at_risk"
    assert risk.minutes_available == 7
    assert risk.margin_minutes == -3
    stale = assess_connection_evidence(**(parameters | {
        "now": NOW + timedelta(minutes=6),
    }))
    assert stale.classification == "unknown"
    assert stale.minutes_available is None
