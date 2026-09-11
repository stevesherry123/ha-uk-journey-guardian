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


async def test_board_is_normalized_without_transportapi_budget() -> None:
    """Railinfo board data maps into the existing conservative matcher shape."""
    client, session, broker = _client(
        {
            "crs": "EUS",
            "date": "2026-09-11",
            "departures": [
                {
                    "public_dep": "1200",
                    "destination": "Crewe",
                    "operator": "Avanti West Coast",
                    "live_train_id": "W12345|EUSTON",
                    "status": "delayed",
                    "etd": "12:08",
                    "live_platform": "7",
                    "cancelled": False,
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
    assert record["expected_departure_time"] == "12:08"
    assert record["platform"] == "7"
    request = broker.async_request.await_args.args[0]
    assert request.provider == "railinfo"
    assert request.quota_controlled is False
    assert broker.async_request.await_args.kwargs["urgent"] is True
    assert session.get.await_args.args[0] == f"{BASE_URL}/boards/EUS/departures"


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


async def test_railinfo_rate_limit_has_a_stable_error() -> None:
    """A public-provider 429 does not look like malformed rail data."""
    client, session, _broker = _client([])
    session.get.return_value.status = 429

    with pytest.raises(ProviderBrokerError) as raised:
        await client.async_places("Chester")

    assert raised.value.category == ERROR_QUOTA_EXHAUSTED
