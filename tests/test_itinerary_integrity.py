"""Booking-scoped warnings never turn a failed check into an invented booking."""

import json
from dataclasses import replace
from datetime import timedelta

import pytest
from test_dashboard import snapshot

from custom_components.journey_guardian.dashboard import dashboard_projection
from custom_components.journey_guardian.models import RailCheckIssue


def failed_snapshot(category="railinfo_rail_schedule_mismatch"):
    state = snapshot()
    return replace(state, current_rail_issue=RailCheckIssue(
        booking_fingerprint=state.next_journey.booking_fingerprint,
        recorded_at=state.checked_at + timedelta(seconds=2),
        category=category,
        stage="match_timetable",
    ))


def test_failed_check_warns_without_rewriting_or_suggesting_travel():
    state = failed_snapshot()
    result = dashboard_projection(state)
    warning, = result["integrity_warnings"]
    assert warning["confirmation_required"] is True
    assert warning["suggested_service"] is None
    assert "missing onward booking" in warning["message"]
    assert (
        result["journey"]["destination"]
        == state.next_journey.destination_confirmation
    )
    assert result["rail_check_issue"] == state.current_rail_issue.as_dict()
    assert json.loads(json.dumps(result)) == result
    assert state == failed_snapshot()


@pytest.mark.parametrize("field,value", [
    ("start", snapshot().next_journey.start + timedelta(days=1)),
    ("end", snapshot().next_journey.end + timedelta(minutes=10)),
    ("destination_confirmation", "Other Example Station"),
    ("summary", "Edited booking"),
    ("location", "Edited location"),
])
def test_other_or_edited_booking_cannot_inherit_warning(field, value):
    state = failed_snapshot()
    state = replace(state, next_journey=replace(state.next_journey, **{field: value}))
    result = dashboard_projection(state)
    assert result["integrity_warnings"] == []
    assert result["rail_check_issue"] is None


@pytest.mark.parametrize("changes", [
    {"simulation_active": True}, {"next_journey": None},
    {"current_rail_issue": None},
])
def test_simulation_idle_and_success_do_not_invent_warning(changes):
    result = dashboard_projection(replace(failed_snapshot(), **changes))
    assert result["integrity_warnings"] == []
    assert result["rail_check_issue"] is None


@pytest.mark.parametrize("category", [
    "railinfo_provider_unavailable", "railinfo_rate_limited",
    "railinfo_permission_denied", "unexpected_private_error_text",
])
def test_outage_or_unrecognised_reason_does_not_claim_booking_mismatch(category):
    assert dashboard_projection(failed_snapshot(category))["integrity_warnings"] == []


def test_legacy_global_error_alone_is_not_current_booking_evidence():
    state = replace(snapshot(), last_live_rail_error="railinfo_rail_schedule_mismatch")
    assert dashboard_projection(state)["integrity_warnings"] == []


def test_scoped_issue_is_serializable_without_calendar_title_or_location():
    state = failed_snapshot()
    exported = state.as_dict()["current_rail_issue"]
    assert exported == state.current_rail_issue.as_dict()
    assert state.next_journey.summary not in json.dumps(exported)
    assert len(exported["booking_fingerprint"]) == 64
