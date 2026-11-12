"""Tests for the public, non-credit-consuming Railinfo client."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.journey_guardian.provider_broker import (
    ERROR_QUOTA_EXHAUSTED,
    ProviderBrokerError,
    ProviderResult,
)
from custom_components.journey_guardian.railinfo import BASE_URL, RailinfoClient

NOW = datetime(2026, 9, 11, 9, 0, tzinfo=UTC)


def _result(payload):
    return ProviderResult(
        payload=dict(payload),
        observed_at=NOW,
        fresh_until=NOW + timedelta(seconds=30),
        freshness="current",
        source="provider",
        age_seconds=0,
    )


def _client(payload):
    response = Mock(status=200)
    response.raise_for_status = Mock()
    response.json = AsyncMock(return_value=payload)
    session = Mock()
    session.get = AsyncMock(return_value=response)
    broker = Mock()

    async def acquire(_request, fetcher, *, urgent=False):
        return _result(await fetcher())

    broker.async_request = AsyncMock(side_effect=acquire)
    return RailinfoClient(session, broker), session, broker


async def test_journey_leg_is_normalized_without_transportapi_budget() -> None:
    """A through service maps to the calendar's intermediate destination."""
    client, session, broker = _client(
        {
            "date": "2026-09-11",
            "journeys": [
                {
                    "changes": 0,
                    "legs": [
                        {
                            "from_crs": "EXC",
                            "to_crs": "SMP",
                            "to_name": "Sample Harbour",
                            "dep": "1200",
                            "atoc_code": "VT",
                            "headcode": "1H67",
                            "status": "on_time",
                            "dep_platform": "7",
                        }
                    ],
                }
            ],
        }
    )

    result = await client.async_station_board(
        "exc", NOW, calling_at="SMP", urgent=True
    )

    assert result.payload["station_code"] == "EXC"
    record = result.payload["departures"]["all"][0]
    assert record["aimed_departure_time"] == "12:00"
    assert record["platform"] == "7"
    request = broker.async_request.await_args.args[0]
    assert request.provider == "railinfo"
    assert request.quota_controlled is False
    assert broker.async_request.await_args.kwargs["urgent"] is True
    assert session.get.await_args.args[0] == f"{BASE_URL}/journeys"
    assert session.get.await_args.kwargs["params"] == {
        "from": "EXC",
        "to": "SMP",
        "date": NOW.date().isoformat(),
        "time": "0900",
    }


async def test_station_search_is_made_compatible_with_shared_resolution() -> None:
    """Railinfo station records become the shared results format."""
    client, _session, broker = _client(
        [{"crs": "EXC", "description": "Example Central"}]
    )

    result = await client.async_places("Example Central")

    assert result.payload == {
        "results": [{"code": "EXC", "name": "Example Central"}]
    }
    request = broker.async_request.await_args.args[0]
    assert request.operation == "stations"
    assert request.quota_controlled is False


async def test_live_board_exposes_reported_arrivals_without_credit_usage() -> None:
    """Destination movement checks use Railinfo's non-credit live board."""
    client, session, broker = _client({"crs": "EXC", "movements": []})

    result = await client.async_live_board("exc", window_hours=12)

    assert result.payload == {"crs": "EXC", "movements": []}
    request = broker.async_request.await_args.args[0]
    assert request.operation == "live_board"
    assert request.quota_controlled is False
    assert session.get.await_args.args[0] == f"{BASE_URL}/boards/EXC"
    assert session.get.await_args.kwargs["params"] == {"window_hours": 12}


async def test_through_service_keeps_its_scheduled_time() -> None:
    """A through service keeps its own scheduled time."""
    client, _session, _broker = _client(
        {
            "date": "2026-09-11",
            "journeys": [
                {
                    "changes": 0,
                    "legs": [
                        {
                            "from_crs": "EXC",
                            "to_crs": "SMP",
                            "to_name": "Sample Harbour",
                            "dep": "1423",
                            "atoc_code": "HL",
                            "headcode": "1D00",
                            "status": "on_time",
                            "dep_platform": "9",
                        }
                    ],
                },
                {
                    "changes": 0,
                    "legs": [
                        {
                            "from_crs": "EXC",
                            "to_crs": "SMP",
                            "to_name": "Sample Harbour",
                            "dep": "1445",
                            "atoc_code": "VT",
                            "headcode": "1A56",
                            "status": "on_time",
                            "dep_platform": "1",
                        }
                    ],
                },
            ],
        }
    )

    result = await client.async_station_board(
        "EXC",
        datetime(2026, 9, 11, 14, 23, tzinfo=UTC),
        calling_at="SMP",
    )

    assert result.payload["departures"]["all"][0]["aimed_departure_time"] == "14:23"
    assert result.payload["departures"]["all"][0]["platform"] == "9"


async def test_railinfo_rate_limit_has_a_stable_error() -> None:
    """A public-provider 429 does not look like malformed rail data."""
    client, session, _broker = _client([])
    session.get.return_value.status = 429

    with pytest.raises(ProviderBrokerError) as raised:
        await client.async_places("Example Central")

    assert raised.value.category == ERROR_QUOTA_EXHAUSTED


async def test_arrival_prediction_uses_broker_and_preserves_explicit_arrival():
    from custom_components.journey_guardian.rail import service_identity

    departure = NOW.replace(hour=11)
    arrival = NOW.replace(hour=12)
    client, session, broker = _client({
        "date": NOW.date().isoformat(), "is_today": True, "journeys": [{
            "changes": 0, "status": "on_time", "legs": [{
                "from_crs": "EXC", "to_crs": "SMP", "dep": "1200", "arr": "1300",
                "expected_arr": "1308", "headcode": "1A23", "mode": "train",
                "status_source": "darwin", "status": "late",
            }],
        }],
    })
    result = await client.async_arrival_prediction(
        origin_code="exc", destination_code="smp",
        expected_service_identity=service_identity("1A23", NOW.date()),
        booked_departure=departure, booked_arrival=arrival, urgent=True,
    )
    assert result.event_at == arrival + timedelta(minutes=8)
    assert result.observed_at == NOW
    assert result.station_identity == "SMP"
    request = broker.async_request.await_args.args[0]
    assert request.operation == "journey_details"
    assert request.quota_controlled is False
    assert request.parameters["time"] == "1200"
    assert broker.async_request.await_args.kwargs["urgent"] is True
    assert session.get.await_args.args[0] == f"{BASE_URL}/journeys"


async def test_stale_broker_result_does_not_become_arrival_evidence():
    from dataclasses import replace

    client, session, broker = _client({})
    broker.async_request.side_effect = None
    broker.async_request.return_value = replace(_result({}), freshness="stale")
    result = await client.async_arrival_prediction(
        origin_code="EXC", destination_code="SMP",
        expected_service_identity="fictional",
        booked_departure=NOW, booked_arrival=NOW + timedelta(hours=1),
    )
    assert result is None
    session.get.assert_not_called()


@pytest.mark.parametrize("changes", [
    {"origin_code": ""}, {"destination_code": "unknown"},
    {"booked_departure": NOW.replace(tzinfo=None)}, {"booked_arrival": NOW},
    {"expected_service_identity": ""},
])
async def test_invalid_arrival_request_cannot_consume_provider_work(changes):
    client, session, broker = _client({})
    parameters = {
        "origin_code": "EXC", "destination_code": "SMP",
        "expected_service_identity": "fictional-service",
        "booked_departure": NOW, "booked_arrival": NOW + timedelta(hours=1),
    }
    with pytest.raises(ValueError):
        await client.async_arrival_prediction(**(parameters | changes))
    broker.async_request.assert_not_called()
    session.get.assert_not_called()
