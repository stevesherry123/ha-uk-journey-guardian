"""Tests for live Google Routes station-access estimates."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

from custom_components.journey_guardian.google_routes import (
    FIELD_MASK,
    ROUTES_URL,
    GoogleRoutesClient,
)

NOW = datetime(2026, 9, 8, 8, 0, tzinfo=UTC)


async def test_driving_route_is_traffic_aware_and_minimally_scoped() -> None:
    """The provider request asks only for duration and distance."""
    response = AsyncMock()
    response.status = 200
    response.json.return_value = {
        "routes": [{"duration": "1250s", "distanceMeters": 18400}]
    }
    response.__aenter__.return_value = response
    session = Mock()
    session.post.return_value = response
    client = GoogleRoutesClient(session, "private-key")

    with patch(
        "custom_components.journey_guardian.google_routes.dt_util.now",
        return_value=NOW,
    ):
        estimate = await client.async_route(
            latitude=53.2,
            longitude=-2.9,
            destination="Chester Station, Chester, UK",
            mode="driving",
            departure_time=datetime(2026, 9, 8, 9, 0, tzinfo=UTC),
        )

    assert estimate.duration_minutes == 21
    assert estimate.distance_meters == 18400
    call = session.post.call_args
    assert call.args[0] == ROUTES_URL
    assert call.kwargs["headers"] == {
        "X-Goog-Api-Key": "private-key",
        "X-Goog-FieldMask": FIELD_MASK,
    }
    assert call.kwargs["json"]["travelMode"] == "DRIVE"
    assert call.kwargs["json"]["routingPreference"] == "TRAFFIC_AWARE"
    assert "private-key" not in str(call.kwargs["json"])


async def test_identical_route_is_cached_until_adaptive_expiry() -> None:
    """Frequent calendar polling does not multiply billable route calls."""
    response = AsyncMock()
    response.status = 200
    response.json.return_value = {"routes": [{"duration": "600s"}]}
    response.__aenter__.return_value = response
    session = Mock()
    session.post.return_value = response
    client = GoogleRoutesClient(session, "private-key")
    kwargs = {
        "latitude": 51.5,
        "longitude": -0.1,
        "destination": "London Euston",
        "mode": "transit",
        "departure_time": datetime(2026, 9, 8, 9, 0, tzinfo=UTC),
    }

    with patch(
        "custom_components.journey_guardian.google_routes.dt_util.now",
        return_value=NOW,
    ):
        first = await client.async_route(**kwargs)
        second = await client.async_route(**kwargs)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert session.post.call_count == 1


async def test_forced_route_bypasses_valid_cache() -> None:
    """The explicit test control always proves current provider access."""
    response = AsyncMock()
    response.status = 200
    response.json.return_value = {"routes": [{"duration": "600s"}]}
    response.__aenter__.return_value = response
    session = Mock()
    session.post.return_value = response
    client = GoogleRoutesClient(session, "private-key")
    kwargs = {
        "latitude": 51.5,
        "longitude": -0.1,
        "destination": "London Euston",
        "mode": "transit",
        "departure_time": datetime(2026, 9, 8, 9, 0, tzinfo=UTC),
    }

    with patch(
        "custom_components.journey_guardian.google_routes.dt_util.now",
        return_value=NOW,
    ):
        await client.async_route(**kwargs)
        forced = await client.async_route(**kwargs, force_refresh=True)

    assert forced.cache_hit is False
    assert session.post.call_count == 2
