"""Tests for privacy-safe Journey Guardian engine failures."""

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from custom_components.journey_guardian.engine import JourneyGuardianEngine
from custom_components.journey_guardian.models import (
    BudgetSnapshot,
    JourneyEvent,
    JourneySnapshot,
)
from custom_components.journey_guardian.provider_broker import ProviderResult
from custom_components.journey_guardian.timing import calculate_fallback_timing

CHECKED_AT = datetime(2026, 8, 28, 16, 34, tzinfo=UTC)
CALENDAR_ENTITY = ".".join(("calendar", "example_travel"))


def _budget() -> Mock:
    budget = Mock()
    budget.snapshot.return_value = BudgetSnapshot(
        date="2026-08-28",
        calls_used=0,
        daily_limit=30,
        urgent_reserve=3,
    )
    return budget


def _calendar_snapshot(*, origin_name: str = "Example Central"):
    journey = JourneyEvent(
        start=datetime(2026, 9, 3, 10, 10, tzinfo=UTC),
        end=datetime(2026, 9, 3, 11, 10, tzinfo=UTC),
        summary=f"Example Rail - {origin_name} to Sample Harbour",
        location=origin_name,
        origin_code="CALENDAR",
        origin_name=origin_name,
        destination_confirmation="Sample Harbour",
        decision_path="calendar_route",
    )
    return JourneySnapshot(
        status="planned",
        checked_at=datetime(2026, 9, 3, 8, 30, tzinfo=UTC),
        next_journey=journey,
        budget=BudgetSnapshot("2026-09-03", 0, 30, 3),
        timing=calculate_fallback_timing(
            journey,
            preparation_minutes=30,
            early_warning_minutes=10,
            station_buffer_minutes=15,
            station_access_minutes=60,
        ),
    )


def _provider_result(payload):
    observed = datetime(2026, 9, 3, 8, 31, tzinfo=UTC)
    return ProviderResult(
        payload=payload,
        observed_at=observed,
        fresh_until=observed + timedelta(seconds=30),
        freshness="current",
        source="provider",
        age_seconds=0,
    )


def _board():
    return {
        "date": "2026-09-03",
        "station_code": "crs:EXC",
        "departures": {
            "all": [
                {
                    "mode": "train",
                    "train_uid": "uid-one",
                    "operator_name": "Example Rail",
                    "aimed_departure_time": "10:10",
                    "expected_departure_time": "10:18",
                    "destination_name": "Sample Harbour",
                    "platform": "3",
                    "status": "LATE",
                }
            ]
        },
    }


async def test_calendar_error_is_sanitized(caplog) -> None:
    """Private exception details never enter coordinator data."""
    caplog.set_level(
        logging.WARNING,
        logger="custom_components.journey_guardian.engine",
    )
    hass = Mock()
    hass.services.async_call = AsyncMock(
        side_effect=RuntimeError("private calendar entity and request details")
    )
    budget = _budget()
    engine = JourneyGuardianEngine(
        hass,
        calendar_entity=".".join(("calendar", "private_example")),
        budget=budget,
    )

    snapshot = await engine.async_review()

    assert snapshot.status == "error"
    assert snapshot.error == "calendar_unavailable"
    assert "private" not in str(snapshot.as_dict()).casefold()
    assert "private" not in caplog.text.casefold()
    assert "RuntimeError" in caplog.text


async def test_active_calendar_journey_remains_selected() -> None:
    """An underway calendar leg remains available for follow-up monitoring."""
    hass = Mock()
    hass.services.async_call = AsyncMock(
        return_value={
            CALENDAR_ENTITY: {
                "events": [
                    {
                        "start": "2026-08-28T16:30:00+00:00",
                        "end": "2026-08-28T17:30:00+00:00",
                        "summary": "Rail - Example Central to Example Junction",
                        "location": "Example Central",
                    }
                ]
            }
        }
    )
    engine = JourneyGuardianEngine(
        hass,
        calendar_entity=CALENDAR_ENTITY,
        budget=_budget(),
    )

    with patch(
        "custom_components.journey_guardian.engine.dt_util.now",
        return_value=CHECKED_AT,
    ):
        snapshot = await engine.async_review()

    assert snapshot.status == "active"
    assert snapshot.next_journey is not None
    assert snapshot.next_journey.end == datetime(
        2026, 8, 28, 17, 30, tzinfo=UTC
    )


async def test_future_calendar_journey_remains_planned() -> None:
    """A journey that has not started remains in the planned state."""
    hass = Mock()
    hass.services.async_call = AsyncMock(
        return_value={
            CALENDAR_ENTITY: {
                "events": [
                    {
                        "start": "2026-08-28T17:00:00+00:00",
                        "end": "2026-08-28T18:00:00+00:00",
                        "summary": "Rail - Example Central to Example Junction",
                        "location": "Example Central",
                    }
                ]
            }
        }
    )
    engine = JourneyGuardianEngine(
        hass,
        calendar_entity=CALENDAR_ENTITY,
        budget=_budget(),
    )

    with patch(
        "custom_components.journey_guardian.engine.dt_util.now",
        return_value=CHECKED_AT,
    ):
        snapshot = await engine.async_review()

    assert snapshot.status == "planned"
    assert snapshot.next_journey is not None
    assert snapshot.timing is not None
    assert snapshot.timing.station_arrival_at == datetime(
        2026, 8, 28, 16, 45, tzinfo=UTC
    )
    assert snapshot.timing.leave_home_at == datetime(
        2026, 8, 28, 15, 45, tzinfo=UTC
    )
    assert snapshot.timing.prepare_at == datetime(
        2026, 8, 28, 15, 5, tzinfo=UTC
    )


async def test_completed_calendar_journey_returns_to_idle() -> None:
    """A calendar leg is released once its timed event has completed."""
    hass = Mock()
    hass.services.async_call = AsyncMock(
        return_value={
            CALENDAR_ENTITY: {
                "events": [
                    {
                        "start": "2026-08-28T15:30:00+00:00",
                        "end": "2026-08-28T16:30:00+00:00",
                        "summary": "Rail - Example Central to Example Junction",
                        "location": "Example Central",
                    }
                ]
            }
        }
    )
    engine = JourneyGuardianEngine(
        hass,
        calendar_entity=CALENDAR_ENTITY,
        budget=_budget(),
    )

    with patch(
        "custom_components.journey_guardian.engine.dt_util.now",
        return_value=CHECKED_AT,
    ):
        snapshot = await engine.async_review()

    assert snapshot.status == "idle"
    assert snapshot.next_journey is None
    assert snapshot.timing is None


async def test_manual_live_review_resolves_and_normalizes_provider_data() -> None:
    """One explicit review joins Places, board, matcher, and timing layers."""
    client = Mock()
    client.configured = True
    client.async_places = AsyncMock(
        side_effect=[
            _provider_result(
                {
                    "member": [
                        {
                            "type": "train_station",
                            "name": "Example Central",
                            "station_code": "EXC",
                        }
                    ]
                }
            ),
            _provider_result(
                {
                    "member": [
                        {
                            "type": "train_station",
                            "name": "Sample Harbour",
                            "station_code": "SHA",
                        }
                    ]
                }
            ),
        ]
    )
    client.async_station_board = AsyncMock(
        return_value=_provider_result(_board())
    )
    budget = _budget()
    budget.snapshot.return_value = BudgetSnapshot("2026-09-03", 2, 30, 3)
    engine = JourneyGuardianEngine(
        Mock(),
        calendar_entity=CALENDAR_ENTITY,
        budget=budget,
        transportapi_client=client,
    )
    engine.async_review = AsyncMock(return_value=_calendar_snapshot())

    result = await engine.async_review_live_rail()

    assert client.async_places.await_args_list == [
        call("Example Central", urgent=False),
        call("Sample Harbour", urgent=False),
    ]
    client.async_station_board.assert_awaited_once_with(
        "EXC",
        datetime(2026, 9, 3, 10, 10, tzinfo=UTC),
        calling_at="SHA",
        urgent=False,
    )
    assert result.status == "delayed"
    assert result.next_journey is not None
    assert result.next_journey.origin_code == "EXC"
    assert result.next_journey.decision_path == "transportapi_manual"
    assert result.rail_observation is not None
    assert result.rail_observation.platform == "3"
    assert result.rail_observation.delay_minutes == 8
    assert result.timing is not None
    assert result.timing.source == "transportapi"
    assert result.timing.classification == "predicted"
    assert result.budget.calls_used == 2


async def test_manual_review_reuses_in_memory_station_resolution() -> None:
    """Repeated checks do not spend another Places call for the same origin."""
    client = Mock()
    client.configured = True
    client.async_places = AsyncMock(
        side_effect=[
            _provider_result(
                {
                    "member": [
                        {
                            "type": "train_station",
                            "name": "Example Central Station",
                            "station_code": "EXC",
                        }
                    ]
                }
            ),
            _provider_result(
                {
                    "member": [
                        {
                            "type": "train_station",
                            "name": "Sample Harbour Station",
                            "station_code": "SHA",
                        }
                    ]
                }
            ),
        ]
    )
    client.async_station_board = AsyncMock(
        return_value=_provider_result(_board())
    )
    engine = JourneyGuardianEngine(
        Mock(),
        calendar_entity=CALENDAR_ENTITY,
        budget=_budget(),
        transportapi_client=client,
    )
    engine.async_review = AsyncMock(return_value=_calendar_snapshot())

    await engine.async_review_live_rail()
    await engine.async_review_live_rail()

    assert client.async_places.await_count == 2
    assert client.async_station_board.await_count == 2
    client.async_station_board.assert_awaited_with(
        "EXC",
        datetime(2026, 9, 3, 10, 10, tzinfo=UTC),
        calling_at="SHA",
        urgent=False,
    )


async def test_normal_calendar_review_never_invokes_transportapi_client() -> None:
    """Scheduled polling stays provider-free even with credentials configured."""
    hass = Mock()
    hass.services.async_call = AsyncMock(return_value={CALENDAR_ENTITY: {}})
    client = Mock()
    client.configured = True
    engine = JourneyGuardianEngine(
        hass,
        calendar_entity=CALENDAR_ENTITY,
        budget=_budget(),
        transportapi_client=client,
    )

    with patch(
        "custom_components.journey_guardian.engine.dt_util.now",
        return_value=CHECKED_AT,
    ):
        await engine.async_review()

    client.async_places.assert_not_called()
    client.async_station_board.assert_not_called()


async def test_manual_live_review_requires_credentials_without_calling_api() -> None:
    """Missing credentials fail before station resolution or quota use."""
    client = Mock()
    client.configured = False
    engine = JourneyGuardianEngine(
        Mock(),
        calendar_entity=CALENDAR_ENTITY,
        budget=_budget(),
        transportapi_client=client,
    )
    engine.async_review = AsyncMock(return_value=_calendar_snapshot())

    with pytest.raises(ValueError, match="transportapi_credentials_missing"):
        await engine.async_review_live_rail()

    client.async_places.assert_not_called()
    client.async_station_board.assert_not_called()


async def test_manual_review_rejects_materially_later_service() -> None:
    """A unique nearby train cannot silently make conservative advice later."""
    client = Mock()
    client.configured = True
    client.async_places = AsyncMock(
        side_effect=[
            _provider_result(
                {
                    "member": [
                        {
                            "type": "train_station",
                            "name": "Example Central",
                            "station_code": "EXC",
                        }
                    ]
                }
            ),
            _provider_result(
                {
                    "member": [
                        {
                            "type": "train_station",
                            "name": "Sample Harbour",
                            "station_code": "SHA",
                        }
                    ]
                }
            ),
        ]
    )
    mismatched_board = _board()
    service = mismatched_board["departures"]["all"][0]
    service["aimed_departure_time"] = "10:21"
    service["expected_departure_time"] = "10:21"
    client.async_station_board = AsyncMock(
        return_value=_provider_result(mismatched_board)
    )
    base = _calendar_snapshot()
    budget = _budget()
    budget.snapshot.return_value = BudgetSnapshot("2026-09-03", 3, 30, 3)
    engine = JourneyGuardianEngine(
        Mock(),
        calendar_entity=CALENDAR_ENTITY,
        budget=budget,
        transportapi_client=client,
    )
    engine.async_review = AsyncMock(return_value=base)

    result = await engine.async_review_live_rail()

    assert result.status == "planned"
    assert result.error is None
    assert (
        result.last_live_rail_error
        == "transportapi_rail_schedule_mismatch"
    )
    assert result.next_journey == base.next_journey
    assert result.timing == base.timing
    assert result.rail_observation is None
    assert result.budget.calls_used == 3

    engine.async_review = JourneyGuardianEngine.async_review.__get__(engine)
    engine._hass.services.async_call = AsyncMock(
        return_value={CALENDAR_ENTITY: {"events": []}}
    )
    with patch(
        "custom_components.journey_guardian.engine.dt_util.now",
        return_value=datetime(2026, 9, 3, 8, 40, tzinfo=UTC),
    ):
        calendar_result = await engine.async_review()

    assert calendar_result.status == "idle"
    assert calendar_result.error is None
    assert calendar_result.data_healthy
    assert (
        calendar_result.last_live_rail_error
        == "transportapi_rail_schedule_mismatch"
    )
