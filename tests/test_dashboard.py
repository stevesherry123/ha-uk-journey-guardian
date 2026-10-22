"""Dashboard projection is descriptive, bounded and free of delivery effects."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.journey_guardian.dashboard import dashboard_projection
from custom_components.journey_guardian.models import (
    BudgetSnapshot,
    JourneyEvent,
    JourneySnapshot,
)
from custom_components.journey_guardian.timing import calculate_fallback_timing

NOW = datetime(2026, 10, 22, 3, tzinfo=UTC)


def snapshot():
    journey = JourneyEvent(
        start=NOW + timedelta(hours=3), end=NOW + timedelta(hours=5),
        summary="Example Rail - Example Central to Sample Harbour",
        location="", origin_code="EXC", origin_name="Example Central",
        destination_confirmation="Sample Harbour", decision_path="calendar_route",
    )
    timing = calculate_fallback_timing(
        journey, preparation_minutes=30, early_warning_minutes=15,
        station_buffer_minutes=25, station_access_minutes=40,
    )
    return JourneySnapshot(
        status="planned", checked_at=NOW, next_journey=journey,
        budget=BudgetSnapshot("2026-10-22", 0, 29, 3), timing=timing,
        operational_phase="waiting", booked_legs=(journey,), booked_leg_count=1,
    )


def test_projection_uses_engine_times_not_another_timing_calculator():
    state = snapshot()
    result = dashboard_projection(state, notification_context={"live_enabled": True})
    assert result["segments"][0]["start"] == state.timing.prepare_at.isoformat()
    assert result["segments"][1]["start"] == state.timing.leave_home_at.isoformat()
    assert result["segments"][2]["start"] == state.timing.station_arrival_at.isoformat()
    assert [event["kind"] for event in result["notifications"]] == [
        "wake_1", "wake_2", "wake_3", "leave_now"
    ]
    assert all(event["eligibility"] == "conditional"
               for event in result["notifications"])
    assert json.loads(json.dumps(result)) == result
    assert state == snapshot()


@pytest.mark.parametrize(
    "source", ["waze_sensor", "google_routes", "configured_fallback"]
)
def test_routing_uses_selected_allowance_and_provenance(source):
    state = snapshot()
    state = replace(state, timing=replace(
        state.timing, station_access_source=source,
        station_access_provider_minutes=None if source == "configured_fallback" else 40,
        station_access_fallback_reason="waze_sensor_unavailable",
    ))
    routing = dashboard_projection(state)["routing"]
    assert routing["source"] == source
    assert routing["applied_minutes"] == 40
    assert routing["fallback_reason"] == "waze_sensor_unavailable"


def test_home_alarm_is_conditional_and_bounded_not_150_guaranteed_alerts():
    result = dashboard_projection(snapshot(), notification_context={
        "live_enabled": True, "enabled": True, "person_home": True,
        "repeat_seconds": 6, "max_minutes": 15,
    })
    assert len(result["notifications"]) == 2
    alarm = result["notifications"][0]
    assert alarm["kind"] == "wake_alarm"
    assert alarm["repeat_seconds"] == 6
    assert alarm["maximum_minutes"] == 15
    assert "until awake evidence" in alarm["condition"]


@pytest.mark.parametrize("change,eligibility", [
    ({}, "disabled"), ({"status": "cancelled"}, "suppressed"),
    ({"error": "calendar_unavailable"}, "suppressed"),
])
def test_disabled_and_unhealthy_states_do_not_promise_delivery(change, eligibility):
    result = dashboard_projection(replace(snapshot(), **change))
    assert {event["eligibility"] for event in result["notifications"]} == {eligibility}


def test_elapsed_does_not_mean_delivered_or_received():
    state = snapshot()
    state = replace(state, checked_at=state.timing.leave_home_at + timedelta(minutes=1))
    result = dashboard_projection(
        state, last_notification="leave_now", last_notification_at=state.checked_at
    )
    assert all(event["elapsed"] for event in result["notifications"])
    assert result["latest_notification_record"]["receipt_confirmed"] is False
    assert "delivered" not in result["notifications"][0]


def test_idle_and_missing_timing_do_not_invent_events():
    idle = dashboard_projection(replace(snapshot(), next_journey=None))
    assert idle["segments"] == []
    assert dashboard_projection(replace(snapshot(), timing=None))["notifications"] == []


def test_simulation_does_not_claim_home_watch_alarm():
    result = dashboard_projection(replace(snapshot(), simulation_active=True),
                                  notification_context={"enabled": True,
                                                        "person_home": True})
    assert result["simulation"]
    assert result["notifications"][0]["kind"] == "wake_1"


def test_zero_preparation_window_omits_out_of_window_reminders():
    state = snapshot()
    state = replace(state, timing=replace(state.timing,
                                         prepare_at=state.timing.leave_home_at))
    events = dashboard_projection(state)["notifications"]
    assert [event["kind"] for event in events] == ["leave_now"]


def test_awake_evidence_suppresses_wake_preview_but_not_departure():
    result = dashboard_projection(snapshot(), notification_context={
        "live_enabled": True, "enabled": True, "person_home": True,
        "status": "awake", "repeat_seconds": 6, "max_minutes": 15,
    })
    assert result["notifications"][0]["eligibility"] == "suppressed"
    assert result["notifications"][1]["eligibility"] == "conditional"
    assert "Wake up now" in result["notifications"][0]["message"]
