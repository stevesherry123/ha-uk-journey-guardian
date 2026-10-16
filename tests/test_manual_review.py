"""Manual review must respond honestly and bound provider/notification work."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.setup import async_setup_component

from custom_components.journey_guardian.const import DOMAIN
from custom_components.journey_guardian.manual_review import (
    ManualTravelReview,
    render_travel_review,
)
from custom_components.journey_guardian.models import (
    BudgetSnapshot,
    JourneyEvent,
    JourneySnapshot,
    RailObservation,
)
from custom_components.journey_guardian.notification import (
    JourneyNotificationScheduler,
    _should_notify_rail,
)
from custom_components.journey_guardian.timing import calculate_fallback_timing

NOW = datetime(2026, 10, 16, 9, tzinfo=UTC)


def snapshot(minutes=75):
    journey = JourneyEvent(
        start=NOW + timedelta(minutes=minutes),
        end=NOW + timedelta(minutes=minutes + 60),
        summary="Example Central to Sample Junction",
        location="Example Central",
        origin_code="CALENDAR",
        origin_name="zzz Example Central",
        destination_confirmation="Sample Junction",
        decision_path="calendar_route",
    )
    return JourneySnapshot(
        status="planned" if minutes > 0 else "active",
        checked_at=NOW,
        next_journey=journey,
        budget=BudgetSnapshot("2026-10-16", 0, 30, 3),
        timing=calculate_fallback_timing(
            journey,
            preparation_minutes=30,
            early_warning_minutes=10,
            station_buffer_minutes=15,
            station_access_minutes=45,
        ),
    )


def coordinator_for(data):
    coordinator = Mock(data=data, last_calendar_source_refresh_error=None)
    coordinator.engine.live_rail_configured = True
    coordinator.async_refresh_calendar_and_review = AsyncMock(return_value=data)
    coordinator.async_review_live_rail = AsyncMock(return_value=data)
    return coordinator


async def test_double_tap_coalesces_provider_and_delivery(freezer):
    freezer.move_to(NOW)
    data = snapshot()
    coordinator = coordinator_for(data)
    notifications = Mock(
        async_manual_review=AsyncMock(return_value="announcement_engine")
    )
    review = ManualTravelReview(coordinator, notifications)
    first, second = await asyncio.gather(review.async_run(), review.async_run())
    assert not first["cached"] and second["cached"]
    assert first["delivery"] == "announcement_engine"
    coordinator.async_refresh_calendar_and_review.assert_awaited_once_with(
        force_station_access=True
    )
    coordinator.async_review_live_rail.assert_awaited_once_with(
        decision_path="travel_review_manual", snapshot=data
    )
    notifications.async_manual_review.assert_awaited_once()
    freezer.tick(timedelta(seconds=31))
    await review.async_run()
    assert coordinator.async_review_live_rail.await_count == 2


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (replace(snapshot(), next_journey=None, status="idle"), "no_journey"),
        (snapshot(200), "outside_window"),
        (snapshot(-10), "underway"),
        (replace(snapshot(), simulation_active=True), "simulation"),
    ],
)
async def test_ineligible_review_never_calls_live_rail(data, expected):
    coordinator = coordinator_for(data)
    notifications = Mock(async_manual_review=AsyncMock())
    result = await ManualTravelReview(coordinator, notifications).async_run(
        notify=False
    )
    assert result["rail_check"] == expected
    coordinator.async_review_live_rail.assert_not_awaited()
    notifications.async_manual_review.assert_not_awaited()
    assert result["message"]


async def test_provider_failure_is_explained_without_old_on_time_claim():
    data = replace(snapshot(), last_live_rail_error="railinfo_rail_service_ambiguous")
    coordinator = coordinator_for(data)
    result = await ManualTravelReview(coordinator, Mock()).async_run(notify=False)
    assert result["rail_check"] == "rail_service_ambiguous"
    assert "Several services match" in result["message"]
    assert "On time" not in result["message"]


async def test_missing_credentials_gives_a_briefing_without_a_provider_call():
    coordinator = coordinator_for(snapshot())
    coordinator.engine.live_rail_configured = False
    result = await ManualTravelReview(coordinator, Mock()).async_run(notify=False)
    assert result["rail_check"] == "not_configured"
    coordinator.async_review_live_rail.assert_not_awaited()


async def test_timeout_gives_a_response_and_never_reports_no_journey_as_success():
    data = replace(snapshot(), next_journey=None, status="idle")
    coordinator = coordinator_for(data)
    coordinator.async_refresh_calendar_and_review.side_effect = TimeoutError()
    result = await ManualTravelReview(coordinator, Mock()).async_run(notify=False)
    assert result["rail_check"] == "review_timeout"
    assert "timed out" in result["message"]


async def test_simulation_and_delivery_failure_leave_full_local_report():
    hass = Mock()
    hass.services.async_call = AsyncMock(side_effect=RuntimeError("private-secret"))
    scheduler = JourneyNotificationScheduler(
        hass,
        Mock(),
        Mock(),
        live_notifications_enabled=False,
        announcement_text_entity="input_text.example_announcement",
        announcement_script_entity="script.example_announcement",
    )
    with patch(
        "custom_components.journey_guardian.notification.persistent_notification.async_create"
    ) as create:
        assert (
            await scheduler.async_manual_review(
                "Full report", "Summary", simulation=True
            )
            == "persistent_notification"
        )
        hass.services.async_call.assert_not_awaited()
        assert (
            await scheduler.async_manual_review(
                "Full report", "Summary", simulation=False
            )
            == "persistent_notification"
        )
        assert create.call_args.args[1] == "Full report"


async def test_exception_is_sanitized_and_silent_review_can_then_notify(freezer):
    freezer.move_to(NOW)
    coordinator = coordinator_for(snapshot())
    coordinator.async_review_live_rail.side_effect = ValueError(
        "private-provider-secret"
    )
    notifications = Mock(
        async_manual_review=AsyncMock(return_value="persistent_notification")
    )
    review = ManualTravelReview(coordinator, notifications)
    result = await review.async_run(notify=False)
    assert result["rail_check"] == "review_failed"
    assert "private-provider-secret" not in str(result)
    await review.async_run()
    notifications.async_manual_review.assert_awaited_once()


def test_cancelled_report_and_full_routing_fallback_details():
    data = snapshot()
    observation = RailObservation(
        scenario="observed",
        source="railinfo",
        classification="provider_normalized",
        observed_at=NOW,
        scheduled_departure=data.next_journey.start,
        predicted_departure=None,
        delay_minutes=0,
        cancelled=True,
        leg_count=1,
        provider_available=True,
    )
    cancelled = replace(
        data, status="cancelled", timing=None, rail_observation=observation
    )
    full, short = render_travel_review(cancelled, "checked")
    assert "Cancelled" in full and "Cancelled" in short
    manual = replace(
        cancelled,
        next_journey=replace(data.next_journey, decision_path="travel_review_manual"),
        rail_observation=replace(observation, cancelled=False),
    )
    assert not _should_notify_rail(manual)
    assert "Leave by" not in full
    assert "zzz " not in full
    full, short = render_travel_review(data, "not_configured")
    assert "configured fallback" in full and "45 minutes" in full
    assert "Leave by" in full and len(short) <= 255
    stale = replace(cancelled, rail_observation=replace(observation, retained=True))
    full, short = render_travel_review(stale, "provider_unavailable")
    assert "not a current confirmation" in full


def test_long_names_and_failure_keep_watch_message_within_helper_limit():
    data = snapshot()
    data = replace(
        data, next_journey=replace(data.next_journey, origin_name="Example " * 100)
    )
    full, short = render_travel_review(
        data, "rail_service_ambiguous", calendar_refresh_failed=True
    )
    assert len(full) > 255 and len(short) <= 255
    assert "Calendar source refresh failed" in short


async def test_explicit_review_delivers_while_auto_notifications_off():
    hass = Mock()
    scheduler = JourneyNotificationScheduler(
        hass,
        Mock(),
        Mock(),
        live_notifications_enabled=False,
        announcement_text_entity="input_text.example_announcement",
        announcement_script_entity="script.example_announcement",
    )
    hass.services.async_call = AsyncMock()
    with patch(
        "custom_components.journey_guardian.notification.persistent_notification.async_create"
    ) as create:
        channel = await scheduler.async_manual_review(
            "Full report", "Watch summary", simulation=False
        )
    assert channel == "announcement_engine"
    assert hass.services.async_call.await_args.args[2] == {"message": "Watch summary"}
    assert create.call_args.args[1] == "Full report"


async def test_public_service_calls_shared_review_and_returns_result(hass):
    assert await async_setup_component(hass, DOMAIN, {})
    runtime = Mock()
    runtime.manual_review.async_run = AsyncMock(
        return_value={"status": "idle", "message": "No journey"}
    )
    with patch("custom_components.journey_guardian._runtime", return_value=runtime):
        result = await hass.services.async_call(
            DOMAIN,
            "travel_review_now",
            {"notify": False},
            blocking=True,
            return_response=True,
        )
    runtime.manual_review.async_run.assert_awaited_once_with(notify=False)
    assert result["message"] == "No journey"
