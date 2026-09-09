"""Build a no-delivery preview of the notification plan for one journey.

This is deliberately not wired into entities, actions, or the scheduler.  It
lets the future UI show the intended sequence before a mobile target is ever
called.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import JourneySnapshot
from .notification_plan import NotificationUrgency, event_definition


@dataclass(frozen=True, slots=True)
class NotificationPreview:
    """One planned notification, suitable for a future read-only UI preview."""

    event_key: str
    due_at: datetime
    urgency: NotificationUrgency
    summary: str


def build_notification_preview(
    snapshot: JourneySnapshot,
) -> tuple[NotificationPreview, ...]:
    """Return the nominal alert timeline without registering or sending anything."""
    if snapshot.next_journey is None or snapshot.timing is None:
        return ()

    timing = snapshot.timing
    journey = snapshot.next_journey
    draft_events = (
        ("journey_detected", snapshot.checked_at, "Planned journey selected."),
        (
            "wake_1",
            timing.prepare_at,
            "Start getting ready.",
        ),
        (
            "wake_2",
            timing.prepare_at + timedelta(minutes=5),
            "Continue getting ready.",
        ),
        (
            "wake_3",
            timing.prepare_at + timedelta(minutes=10),
            "Final preparation reminder.",
        ),
        (
            "leave_now",
            timing.leave_home_at,
            f"Leave for {journey.origin_name}; aim to arrive by "
            f"{timing.station_arrival_at.strftime('%H:%M')}.",
        ),
    )
    preview: list[NotificationPreview] = []
    for event_key, due_at, summary in draft_events:
        definition = event_definition(event_key)
        if definition is None:
            continue
        preview.append(
            NotificationPreview(
                event_key=event_key,
                due_at=due_at,
                urgency=definition.urgency,
                summary=summary,
            )
        )
    return tuple(sorted(preview, key=lambda item: item.due_at))
