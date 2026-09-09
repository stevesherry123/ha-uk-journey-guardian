"""Tests for the inactive notification timeline preview."""

from datetime import UTC, datetime, timedelta

from custom_components.journey_guardian.models import (
    BudgetSnapshot,
    JourneyEvent,
    JourneySnapshot,
    JourneyTiming,
)
from custom_components.journey_guardian.notification_preview import (
    build_notification_preview,
)


def _snapshot() -> JourneySnapshot:
    now = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
    return JourneySnapshot(
        status="planned",
        checked_at=now,
        next_journey=JourneyEvent(
            start=now + timedelta(hours=3),
            end=now + timedelta(hours=4),
            summary="Example Origin to Example Destination",
            location="Example Origin",
            origin_code="EXO",
            origin_name="Example Origin",
            destination_confirmation="Example Destination",
            decision_path="calendar_route",
        ),
        timing=JourneyTiming(
            prepare_at=now + timedelta(hours=1),
            leave_home_at=now + timedelta(hours=2),
            station_arrival_at=now + timedelta(hours=2, minutes=45),
            preparation_minutes=30,
            early_warning_minutes=10,
            station_buffer_minutes=15,
            station_access_minutes=60,
            source="configured_fallback",
            classification="inferred",
        ),
        budget=BudgetSnapshot("2026-09-10", 0, 29, 3),
    )


def test_preview_is_ordered_and_contains_only_planned_operational_events() -> None:
    """Previewing a journey never needs a notifier or an entity registration."""
    preview = build_notification_preview(_snapshot())

    assert [item.event_key for item in preview] == [
        "journey_detected",
        "wake_1",
        "wake_2",
        "wake_3",
        "leave_now",
    ]
    assert preview[-1].urgency == "critical"
    assert "Example Origin" in preview[-1].summary


def test_preview_is_empty_without_a_selected_journey_timing() -> None:
    """An incomplete review cannot invent alerts in the future UI."""
    snapshot = _snapshot()

    assert build_notification_preview(
        JourneySnapshot(
            status=snapshot.status,
            checked_at=snapshot.checked_at,
            next_journey=None,
            timing=None,
            budget=snapshot.budget,
        )
    ) == ()
