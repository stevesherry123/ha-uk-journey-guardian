"""Two-leg evidence acquisition remains separate from selected-journey planning."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.journey_guardian.connection_evidence import (
    ServiceReference,
    StationTimeEvidence,
)
from custom_components.journey_guardian.connection_review import async_review_connection
from custom_components.journey_guardian.travel_plan import RetainedLeg

NOW = datetime(2026, 11, 4, 10, tzinfo=UTC)


def leg(identity, origin, destination, start, end):
    return RetainedLeg(
        identity * 64,
        start.isoformat(),
        end.isoformat(),
        origin,
        destination,
        NOW.isoformat(),
        NOW.isoformat(),
    )


def engine():
    client = Mock()
    client.async_station_board = AsyncMock(
        return_value=SimpleNamespace(healthy=True, payload={}, observed_at=NOW)
    )
    client.async_arrival_prediction = AsyncMock(
        return_value=StationTimeEvidence(
            ServiceReference("railinfo", "incoming"),
            "EXJ",
            "arrival",
            "predicted",
            NOW + timedelta(minutes=23),
            NOW,
        )
    )
    client.async_departure_prediction = AsyncMock(
        return_value=StationTimeEvidence(
            ServiceReference("railinfo", "onward"),
            "EXJ",
            "departure",
            "predicted",
            NOW + timedelta(minutes=30),
            NOW,
        )
    )
    state = Mock()
    state._live_rail_provider = "railinfo"
    state._railinfo_client = client
    names = {
        "Example Origin": "EXC",
        "Example Junction": "EXJ",
        "Sample Harbour": "SMP",
    }
    state._async_resolve_station = AsyncMock(
        side_effect=lambda **kw: SimpleNamespace(code=names[kw["name"]])
    )
    return state, client


async def test_two_leg_review_uses_arrival_and_onward_prediction_without_replanning():
    state, client = engine()
    inbound = leg(
        "a",
        "Example Origin",
        "Example Junction",
        NOW - timedelta(hours=1),
        NOW + timedelta(minutes=15),
    )
    outbound = leg(
        "b",
        "Example Junction",
        "Sample Harbour",
        NOW + timedelta(minutes=30),
        NOW + timedelta(hours=2),
    )
    with (
        patch(
            "custom_components.journey_guardian.connection_review.normalize_station_board",
            side_effect=[
                Mock(service_identity="incoming", cancelled=False),
                Mock(service_identity="onward", cancelled=False),
            ],
        ),
        patch(
            "custom_components.journey_guardian.connection_review.dt_util.now",
            return_value=NOW,
        ),
    ):
        risk, expiry = await async_review_connection(
            state, inbound, outbound, minimum_minutes=10, now=NOW
        )
    assert risk.classification == "at_risk"
    assert risk.minutes_available == 7
    assert expiry == NOW + timedelta(minutes=5)
    assert client.async_station_board.await_count == 2
    client.async_arrival_prediction.assert_awaited_once()
    client.async_departure_prediction.assert_awaited_once()
    state.async_review_live_rail.assert_not_called()


async def test_invalidated_context_stops_before_acquisition():
    state, client = engine()
    inbound = leg(
        "a", "Example Origin", "Example Junction", NOW, NOW + timedelta(minutes=15)
    )
    with pytest.raises(ValueError, match="no_longer_current"):
        await async_review_connection(
            state,
            inbound,
            inbound,
            minimum_minutes=10,
            now=NOW,
            still_current=lambda: False,
        )
    state._async_resolve_station.assert_not_called()
    client.async_station_board.assert_not_awaited()
