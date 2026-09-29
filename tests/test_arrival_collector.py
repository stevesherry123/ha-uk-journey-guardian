"""Tests for provider-confirmed destination arrival collection."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, Mock

from custom_components.journey_guardian.arrival_collector import (
    ArrivalCollector,
    _match_arrival,
)
from custom_components.journey_guardian.provider_broker import ProviderResult
from custom_components.journey_guardian.rail import service_identity

SERVICE_DATE = date(2026, 9, 28)


def _movement_payload(*, event_type="ARRIVAL", train_id="701D93ME28"):
    return {
        "crs": "CTR",
        "movements": [
            {
                "train_id": train_id,
                "event_type": event_type,
                "gbtt_ts": "2026-09-28T20:07:00+00:00",
                "actual_ts": "2026-09-28T20:19:00+00:00",
                "variation_min": 12,
            }
        ],
    }


def test_arrival_matches_departure_headcode_identity() -> None:
    """The destination movement is joined to the Railinfo journey leg."""
    arrival = _match_arrival(
        _movement_payload(),
        expected_identity=service_identity("1D93", SERVICE_DATE),
        service_date=SERVICE_DATE,
    )

    assert arrival == {
        "scheduled_arrival": "2026-09-28T20:07:00+00:00",
        "actual_arrival": "2026-09-28T20:19:00+00:00",
        "arrival_delay_minutes": 12,
    }


def test_departure_movement_cannot_complete_a_journey() -> None:
    """Only an actual arrival at the destination is completion evidence."""
    assert (
        _match_arrival(
            _movement_payload(event_type="DEPARTURE"),
            expected_identity=service_identity("1D93", SERVICE_DATE),
            service_date=SERVICE_DATE,
        )
        is None
    )


async def test_collector_records_completed_arrival(hass) -> None:
    """A matched movement becomes a reviewable arrival evidence record."""
    observed_at = datetime(2026, 9, 28, 20, 20, tzinfo=UTC)
    result = ProviderResult(
        payload=_movement_payload(),
        observed_at=observed_at,
        fresh_until=observed_at + timedelta(seconds=30),
        freshness="current",
        source="provider",
        age_seconds=0,
    )
    client = Mock()
    client.async_live_board = AsyncMock(return_value=result)
    history = Mock()
    history.async_record = AsyncMock()
    collector = ArrivalCollector(hass, Mock(), client, history)
    collector._store.async_save = AsyncMock()
    collector._pending["pending-key"] = {
        "journey_fingerprint": "journey-key",
        "journey_date": "2026-09-28",
        "origin_code": "EUS",
        "destination_code": "CTR",
        "service_identity": service_identity("1D93", SERVICE_DATE),
        "service_date": "2026-09-28",
        "scheduled_end": "2026-09-28T21:07:00+01:00",
        "attempt": 0,
    }

    await collector._async_collect("pending-key")

    record = history.async_record.await_args.args[0]
    assert record["completion_status"] == "completed"
    assert record["arrival_delay_minutes"] == 12
    assert record["scheduled_arrival"] == "2026-09-28T20:07:00+00:00"
    assert record["actual_arrival"] == "2026-09-28T20:19:00+00:00"
    assert "pending-key" not in collector._pending
    assert "pending-key" in collector._completed
