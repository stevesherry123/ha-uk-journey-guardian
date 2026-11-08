"""Fictional review-only matching; never infer a booked train from a forecast."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.journey_guardian.models import JourneyEvent
from custom_components.journey_guardian.provider_broker import (
    ProviderBrokerError,
    ProviderResult,
)
from custom_components.journey_guardian.railinfo import RailinfoClient
from custom_components.journey_guardian.railinfo_booking_match import (
    BookingMatchRequest,
    normalize_booking_match,
)

NOW = datetime(2026, 11, 7, 8, tzinfo=UTC)
BOOKING = JourneyEvent(
    NOW + timedelta(hours=1), NOW + timedelta(hours=1, minutes=22),
    "Example Central to Sample Harbour", "", "EXC", "Example Central",
    "Sample Harbour", "calendar_route",
)
REQUEST = BookingMatchRequest(BOOKING, "EXC", "SMP", "EXJ")


def route(**updates):
    return {"changes": 0, "legs": [{
        "from_crs": "EXC", "to_crs": "EXJ", "mode": "train", "headcode": "1A23",
        "dep": "0900", "arr": "0922", **updates,
    }]}


def payload(*routes):
    return {"date": "2026-11-07", "journeys": list(routes)}


def test_unique_match_retains_provenance_and_does_not_edit_booking():
    result = normalize_booking_match(
        payload(route(expected_arr="0929")), REQUEST, observed_at=NOW, now=NOW,
    )
    assert result.status == "proposal_available"
    assert result.proposal.booking_fingerprint == BOOKING.booking_fingerprint
    assert result.proposal.scheduled_arrival == BOOKING.end
    assert result.proposal.observed_at == NOW
    assert result.proposal.valid_until == NOW + timedelta(minutes=5)
    assert result.proposal.alternative_code == "EXJ"
    assert BOOKING.destination_confirmation == "Sample Harbour"


@pytest.mark.parametrize("updates", [
    {"from_crs": "EXO"}, {"to_crs": "SMP"}, {"mode": "bus"}, {"dep": "0901"},
    {"arr": "0921", "expected_arr": "0922"}, {"arr": None},
])
def test_no_proposal_without_both_scheduled_endpoint_matches(updates):
    result = normalize_booking_match(
        payload(route(**updates)), REQUEST, observed_at=NOW, now=NOW,
    )
    assert result.status == "no_match"
    assert result.proposal is None


@pytest.mark.parametrize(
    "other", [route(), route(headcode="2B34"), route(cancelled=True)]
)
def test_duplicate_or_conflicting_matches_are_ambiguous(other):
    result = normalize_booking_match(
        payload(route(), other), REQUEST, observed_at=NOW, now=NOW,
    )
    assert result.status == "ambiguous_match"
    assert result.proposal is None


@pytest.mark.parametrize("updates", [
    {"headcode": None}, {"headcode": "TEST"}, {"cancelled": True},
    {"status": "cancelled"},
])
def test_unusable_unique_row_cannot_become_a_proposal(updates):
    assert normalize_booking_match(
        payload(route(**updates)), REQUEST, observed_at=NOW, now=NOW,
    ).status == "unusable_match"


def test_oversized_wrong_date_and_stale_evidence_fail_closed():
    for data in (payload(*[route()] * 41), payload(route()) | {"date": "2026-11-08"}):
        assert normalize_booking_match(
            data, REQUEST, observed_at=NOW, now=NOW,
        ).status == "invalid_response"
    for offset in (-1, 5):
        assert normalize_booking_match(
            payload(route()), REQUEST, observed_at=NOW,
            now=NOW + timedelta(minutes=offset),
        ).status == "stale_response"


def test_repeated_local_clock_does_not_resolve_without_offset():
    start = datetime(2026, 10, 25, 0, 15, tzinfo=UTC)
    request = replace(REQUEST, booking=replace(
        BOOKING, start=start, end=start + timedelta(minutes=20),
    ))
    assert normalize_booking_match(
        payload(route(dep="0115", arr="0135")) | {"date": "2026-10-25"},
        request, observed_at=start, now=start,
    ).status == "no_match"


def test_request_requires_explicit_distinct_station_and_same_day_times():
    with pytest.raises(ValueError, match="distinct_resolved_station_codes_required"):
        replace(REQUEST, alternative_code="SMP")
    with pytest.raises(ValueError, match="booking_origin_conflict"):
        replace(REQUEST, origin_code="EXO")
    with pytest.raises(ValueError, match="same_day_booked_times_required"):
        replace(REQUEST, booking=replace(BOOKING, end=None))


async def test_client_uses_one_shared_broker_request_without_urgent_reserve():
    broker = Mock()
    broker.async_request = AsyncMock(return_value=ProviderResult(
        payload=payload(route()), observed_at=NOW,
        fresh_until=NOW + timedelta(seconds=30), freshness="current",
        source="provider", age_seconds=0,
    ))
    client = RailinfoClient(Mock(), broker)
    with patch(
        "custom_components.journey_guardian.railinfo.dt_util.utcnow", return_value=NOW
    ):
        result = await client.async_booking_match(REQUEST)
    assert result.proposal is not None
    broker.async_request.assert_awaited_once()
    call = broker.async_request.await_args
    assert call.args[0].operation == "journey_details"
    assert call.args[0].parameters == {
        "from": "EXC", "to": "EXJ", "date": "2026-11-07", "time": "0900",
    }
    assert call.kwargs == {}
    broker.async_request.side_effect = ProviderBrokerError("quota_exhausted")
    assert (await client.async_booking_match(REQUEST)).status == "provider_unavailable"
