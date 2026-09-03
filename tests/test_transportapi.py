"""Tests for the dormant, brokered TransportAPI client."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

from custom_components.journey_guardian.provider_broker import ProviderResult
from custom_components.journey_guardian.transportapi import (
    BASE_URL,
    TransportAPIClient,
)

NOW = datetime(2026, 9, 3, 8, 30, tzinfo=UTC)


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
    response = Mock()
    response.raise_for_status = Mock()
    response.json = AsyncMock(return_value=payload)
    session = Mock()
    session.get = AsyncMock(return_value=response)
    broker = Mock()

    async def acquire(_request, fetcher):
        return _result(await fetcher())

    broker.async_request = AsyncMock(side_effect=acquire)
    return (
        TransportAPIClient(
            session,
            broker,
            app_id="example-id",
            app_key="example-key",
        ),
        session,
        broker,
    )


async def test_places_uses_headers_and_broker_without_query_credentials() -> None:
    """Credentials remain in headers and never enter broker identity params."""
    payload = {"member": []}
    client, session, broker = _client(payload)

    result = await client.async_places("Example Central")

    assert result.payload == payload
    request = broker.async_request.await_args.args[0]
    assert request.operation == "places"
    assert "example-key" not in str(request.parameters)
    call = session.get.await_args
    assert call.args[0] == f"{BASE_URL}/v3/uk/places.json"
    assert call.kwargs["headers"] == {
        "X-App-Id": "example-id",
        "X-App-Key": "example-key",
    }


async def test_station_board_requests_bounded_live_window() -> None:
    """A manual board request is scoped around one calendar departure."""
    payload = {"station_code": "crs:EXC", "departures": {"all": []}}
    client, session, broker = _client(payload)
    departure = datetime(2026, 9, 3, 10, 10, tzinfo=UTC)

    await client.async_station_board("exc", departure, calling_at="sha")

    request = broker.async_request.await_args.args[0]
    assert request.operation == "station_timetables"
    assert request.parameters["station_code"] == "EXC"
    call = session.get.await_args
    assert call.args[0].endswith("/station_timetables/EXC.json")
    assert call.kwargs["params"]["datetime"] == departure.isoformat()
    assert call.kwargs["params"]["from_offset"] == "-PT00:45:00"
    assert call.kwargs["params"]["to_offset"] == "PT00:45:00"
    assert call.kwargs["params"]["live"] == "true"
    assert call.kwargs["params"]["calling_at"] == "SHA"
    assert call.kwargs["params"]["station_detail"] == "calling_at"


def test_missing_credentials_leave_client_dormant() -> None:
    """An unconfigured client performs no work merely by existing."""
    client = TransportAPIClient(
        Mock(), Mock(), app_id="", app_key=""
    )

    assert not client.configured
