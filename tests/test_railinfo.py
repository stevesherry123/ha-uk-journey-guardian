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
                            "from_crs": "EUS",
                            "to_crs": "CRE",
                            "to_name": "Crewe",
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
        "eus", NOW, calling_at="CRE", urgent=True
    )

    assert result.payload["station_code"] == "EUS"
    record = result.payload["departures"]["all"][0]
    assert record["aimed_departure_time"] == "12:00"
    assert record["platform"] == "7"
    request = broker.async_request.await_args.args[0]
    assert request.provider == "railinfo"
    assert request.quota_controlled is False
    assert broker.async_request.await_args.kwargs["urgent"] is True
    assert session.get.await_args.args[0] == f"{BASE_URL}/journeys"
    assert session.get.await_args.kwargs["params"] == {
        "from": "EUS",
        "to": "CRE",
        "date": NOW.date().isoformat(),
        "time": "0900",
    }


async def test_station_search_is_made_compatible_with_shared_resolution() -> None:
    """Railinfo station records become the shared results format."""
    client, _session, broker = _client(
        [{"crs": "CTR", "description": "Chester"}]
    )

    result = await client.async_places("Chester")

    assert result.payload == {"results": [{"code": "CTR", "name": "Chester"}]}
    request = broker.async_request.await_args.args[0]
    assert request.operation == "stations"
    assert request.quota_controlled is False


async def test_through_service_to_chester_is_not_confused_with_terminator() -> None:
    """Crewe→Chester keeps the Wrexham-through service's scheduled time."""
    client, _session, _broker = _client(
        {
            "date": "2026-09-11",
            "journeys": [
                {
                    "changes": 0,
                    "legs": [
                        {
                            "from_crs": "CRE",
                            "to_crs": "CTR",
                            "to_name": "Chester",
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
                            "from_crs": "CRE",
                            "to_crs": "CTR",
                            "to_name": "Chester",
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
        "CRE",
        datetime(2026, 9, 11, 14, 23, tzinfo=UTC),
        calling_at="CTR",
    )

    assert result.payload["departures"]["all"][0]["aimed_departure_time"] == "14:23"
    assert result.payload["departures"]["all"][0]["platform"] == "9"


async def test_railinfo_rate_limit_has_a_stable_error() -> None:
    """A public-provider 429 does not look like malformed rail data."""
    client, session, _broker = _client([])
    session.get.return_value.status = 429

    with pytest.raises(ProviderBrokerError) as raised:
        await client.async_places("Chester")

    assert raised.value.category == ERROR_QUOTA_EXHAUSTED
