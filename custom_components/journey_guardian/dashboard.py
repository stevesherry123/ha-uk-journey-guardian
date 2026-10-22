"""Read-only dashboard projection of existing decisions; never schedules work."""

from __future__ import annotations

from datetime import timedelta

from .booking_overview import render_bookings
from .models import JourneySnapshot
from .notification import (
    WAKE_REMINDER_OFFSETS,
    _actionable_departure,
    _notification_message,
)


def dashboard_projection(
    snapshot: JourneySnapshot,
    *,
    notification_context: dict | None = None,
    last_notification: str | None = None,
    last_notification_at=None,
) -> dict:
    """Keep expected milestones separate from the limited delivery evidence."""
    context = notification_context or {}
    journey, timing = snapshot.next_journey, snapshot.timing
    result = {
        "schema_version": 1,
        "checked_at": snapshot.checked_at.isoformat(),
        "healthy": snapshot.data_healthy,
        "simulation": snapshot.simulation_active,
        "phase": snapshot.operational_phase,
        "journey": None,
        "routing": None,
        "segments": [],
        "notifications": [],
        "bookings": render_bookings(snapshot.booked_legs, snapshot.checked_at),
        "bookings_source": "retained_calendar" if snapshot.error else "calendar_only",
        "bookings_truncated": snapshot.booked_leg_count > len(snapshot.booked_legs),
        "latest_notification_record": (
            {
                "kind": last_notification,
                "recorded_at": last_notification_at.isoformat(),
                "receipt_confirmed": False,
            }
            if last_notification and last_notification_at else None
        ),
    }
    if journey is None:
        return result
    departure = _actionable_departure(snapshot)
    result["journey"] = {
        "origin": journey.origin_name,
        "destination": journey.destination_confirmation,
        "booked_departure": journey.start.isoformat(),
        "departure": departure.isoformat(),
        "booked_arrival": journey.end.isoformat() if journey.end else None,
        "cancelled": snapshot.status == "cancelled" or bool(
            snapshot.rail_observation and snapshot.rail_observation.cancelled
        ),
    }
    if timing is None:
        return result
    result["routing"] = {
        "source": timing.station_access_source,
        "mode": timing.station_access_mode,
        "provider_minutes": timing.station_access_provider_minutes,
        "applied_minutes": timing.station_access_minutes,
        "fallback_reason": timing.station_access_fallback_reason,
        "error": timing.station_access_error,
        "classification": timing.station_access_classification,
    }
    for label, start, end in (
        ("Preparation", timing.prepare_at, timing.leave_home_at),
        ("Station access", timing.leave_home_at, timing.station_arrival_at),
        ("At station", timing.station_arrival_at, departure),
        ("Booked train", departure, journey.end),
    ):
        if end is not None and end > start:
            result["segments"].append({
                "label": label, "start": start.isoformat(), "end": end.isoformat(),
            })
    enabled = context.get("live_enabled") is True or snapshot.simulation_active
    repeating = bool(
        context.get("enabled") and context.get("person_home")
        and not snapshot.simulation_active
    )
    condition = "conditional" if enabled else "disabled"
    if result["journey"]["cancelled"] or snapshot.error:
        condition = "suppressed"
    if repeating:
        events = [("wake_alarm", timing.prepare_at, "Home wake-up")]
    else:
        events = [
            (f"wake_{number}", timing.prepare_at + timedelta(minutes=offset),
             f"Preparation reminder {number}")
            for number, offset in enumerate(WAKE_REMINDER_OFFSETS, start=1)
            if timing.prepare_at + timedelta(minutes=offset) < timing.leave_home_at
        ]
    events.append(("leave_now", timing.leave_home_at, "Leave for station"))
    for key, due, label in events:
        eligibility = condition
        if key.startswith("wake_") and context.get("status") in {"awake", "completed"}:
            eligibility = "suppressed"
        result["notifications"].append({
            "kind": key, "label": label, "due_at": due.isoformat(),
            "eligibility": eligibility,
            "elapsed": due <= snapshot.checked_at,
            "repeat_seconds": context.get("repeat_seconds") if repeating else None,
            "maximum_minutes": context.get("max_minutes") if repeating else None,
            "condition": (
                "While home, until awake evidence, safety limit or leave time"
                if key == "wake_alarm" else "Subject to live state and deduplication"
            ),
            "message": _notification_message(snapshot, key),
        })
    return result
