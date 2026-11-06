"""Fictional complete-route responses; no real user itineraries."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.journey_guardian.railinfo_recovery import (
    normalize_railinfo_recovery,
)
from custom_components.journey_guardian.recovery import RecoveryRequest

NOW = datetime(2026, 11, 4, 9, tzinfo=UTC)
REQUEST = RecoveryRequest("confirmed", "EXC", "SMP", "user_confirmed", NOW, NOW, True)


def leg(origin="EXC", destination="SMP", dep="1000", arr="1100", headcode="1A23"):
    return {
        "from_crs": origin, "to_crs": destination, "dep": dep, "arr": arr,
        "expected_dep": dep, "expected_arr": arr, "headcode": headcode,
        "mode": "train", "status": "on_time", "status_source": "darwin",
    }


def payload(legs=None):
    legs = [leg()] if legs is None else legs
    return {"date": "2026-11-04", "is_today": True, "journeys": [{
        "changes": len(legs) - 1, "status": "on_time", "legs": legs,
    }]}


def normalize(data=None, **changes):
    return normalize_railinfo_recovery(
        payload() if data is None else data, REQUEST, **({
        "observed_at": NOW, "now": NOW, "max_age": timedelta(minutes=5),
        "max_wait": timedelta(hours=2), "max_duration": timedelta(hours=8),
        } | changes))


def test_direct_route_preserves_evidence_age_and_ticket_uncertainty():
    result = normalize()
    assert result.status == "options_available"
    route, = result.routes
    assert route.legs[-1].destination_code == "SMP"
    assert route.legs[0].arrival.observed_at == NOW
    assert route.valid_until == NOW + timedelta(minutes=5)
    assert route.ticket_acceptance == "unknown"


def test_one_search_response_validates_whole_route_with_change():
    result = normalize(payload([
        leg(destination="EXJ", arr="1030"),
        leg(origin="EXJ", dep="1045", arr="1130", headcode="2B34"),
    ]))
    assert result.status == "options_available"
    assert len(result.routes[0].legs) == 2
    assert result.routes[0].transfers[0].minutes_required == 10
    assert result.supported_changes == 1


@pytest.mark.parametrize("update", [
    {"to_crs": "EXJ"}, {"from_crs": "ABC"}, {"expected_arr": None},
    {"expected_dep": None}, {"status_source": "timetable"},
    {"cancelled": True}, {"status": "cancelled"}, {"headcode": ""},
    {"dep": "2300", "arr": "0010"}, {"from_crs": None},
])
def test_invalid_candidate_cannot_become_partial_recovery(update):
    result = normalize(payload([leg() | update]))
    assert result.status == "no_complete_route_in_response"
    assert not result.routes
    assert result.rejected_candidates == 1


def test_tight_transfer_rejects_entire_candidate_but_keeps_valid_direct():
    data = payload([
        leg(destination="EXJ", arr="1030"),
        leg(origin="EXJ", dep="1035", headcode="2B34"),
    ])
    data["journeys"].extend(payload()["journeys"])
    result = normalize(data)
    assert len(result.routes) == 1
    assert len(result.routes[0].legs) == 1
    assert result.rejected_candidates == 1


@pytest.mark.parametrize("update", [
    {"date": "2026-11-03"}, {"is_today": False}, {"journeys": None},
    {"journeys": [None] * 41},
])
def test_invalid_or_oversized_envelope_is_not_truncated(update):
    assert normalize(payload() | update).status == "invalid_response"


@pytest.mark.parametrize("offset", [-1, 6])
def test_future_or_stale_response_is_not_refreshed_by_mapping(offset):
    result = normalize(now=NOW + timedelta(minutes=offset))
    assert result.status == "stale_response"
    assert not result.routes


def test_duplicate_routes_are_ambiguous_even_with_identical_predictions():
    data = payload()
    duplicate = deepcopy(data["journeys"][0])
    data["journeys"].append(duplicate)
    assert not normalize(data).routes
    duplicate["legs"][0]["expected_arr"] = "1110"
    assert not normalize(data).routes


def test_provider_changes_above_observed_capability_are_explicitly_rejected():
    data = payload([leg(), leg(), leg()])
    result = normalize(data)
    assert not result.routes
    assert result.rejected_candidates == 1
    assert result.supported_changes == 1


def test_empty_provider_result_does_not_assert_no_route_exists():
    result = normalize(payload() | {"journeys": []})
    assert result.status == "no_complete_route_in_response"


async def test_search_uses_one_broker_query_to_final_destination(monkeypatch):
    from unittest.mock import AsyncMock, Mock

    from custom_components.journey_guardian.provider_broker import ProviderResult
    from custom_components.journey_guardian.railinfo import RailinfoClient

    monkeypatch.setattr(
        "custom_components.journey_guardian.railinfo.dt_util.utcnow", lambda: NOW
    )
    broker = Mock()
    broker.async_request = AsyncMock(return_value=ProviderResult(
        payload(), NOW, NOW + timedelta(minutes=1), "current", "cache", 0
    ))
    session = Mock()
    client = RailinfoClient(session, broker)
    result = await client.async_recovery_search(
        REQUEST, max_age=timedelta(minutes=5), max_wait=timedelta(hours=2),
        max_duration=timedelta(hours=8),
    )
    assert result.status == "options_available"
    broker.async_request.assert_awaited_once()
    query = broker.async_request.await_args.args[0]
    assert query.operation == "journey_details"
    assert query.parameters == {
        "from": "EXC", "to": "SMP", "date": "2026-11-04", "time": "0900",
    }
    assert query.quota_controlled is False
    session.get.assert_not_called()


@pytest.mark.parametrize("scenario", ["stale_origin", "late_ready", "provider_error",
                                     "stale_cache", "slow_response"])
async def test_search_never_promotes_unusable_context_or_provider_data(
    monkeypatch, scenario
):
    from dataclasses import replace
    from unittest.mock import AsyncMock, Mock

    from custom_components.journey_guardian.provider_broker import (
        ProviderBrokerError,
        ProviderResult,
    )
    from custom_components.journey_guardian.railinfo import RailinfoClient

    clock = Mock(return_value=NOW)
    monkeypatch.setattr(
        "custom_components.journey_guardian.railinfo.dt_util.utcnow", clock
    )
    request = REQUEST
    expected = "provider_unavailable"
    if scenario == "stale_origin":
        request = replace(REQUEST, origin_observed_at=NOW - timedelta(minutes=6))
        expected = "recovery_origin_not_current"
    elif scenario == "late_ready":
        request = replace(REQUEST, ready_at=NOW + timedelta(hours=3))
        expected = "readiness_exceeds_wait_limit"
    elif scenario == "slow_response":
        clock.side_effect = [NOW, NOW + timedelta(minutes=6)]
        expected = "stale_response"
    broker = Mock()
    broker.async_request = AsyncMock(return_value=ProviderResult(
        payload(), NOW, NOW + timedelta(minutes=1),
        "stale" if scenario == "stale_cache" else "current", "cache", 0,
    ))
    if scenario == "provider_error":
        broker.async_request.side_effect = ProviderBrokerError("provider_unavailable")
    result = await RailinfoClient(Mock(), broker).async_recovery_search(
        request, max_age=timedelta(minutes=5), max_wait=timedelta(hours=2),
        max_duration=timedelta(hours=8),
    )
    assert result.status == expected
    assert not result.routes
    if scenario in ("stale_origin", "late_ready"):
        broker.async_request.assert_not_called()
    else:
        broker.async_request.assert_awaited_once()


def test_cancelled_duplicate_cannot_be_hidden_by_a_healthy_copy():
    data = payload()
    cancelled = deepcopy(data["journeys"][0])
    cancelled["legs"][0]["cancelled"] = True
    data["journeys"].append(cancelled)
    result = normalize(data)
    assert not result.routes
    assert result.rejected_candidates == 2
