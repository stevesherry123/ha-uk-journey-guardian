"""A side-effect-free notification vocabulary for the next delivery slice.

This module deliberately does not register Home Assistant services, change
notifications, or add configuration fields.  It gives the UI and delivery
adapters a stable, reviewable contract before either is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

NotificationUrgency = Literal["routine", "time_sensitive", "critical"]


@dataclass(frozen=True, slots=True)
class NotificationEventDefinition:
    """Describe one user-facing notification event without delivering it."""

    key: str
    title: str
    urgency: NotificationUrgency
    description: str
    default_enabled: bool
    requires_live_opt_in: bool = True


# This catalogue is intentionally independent of the current persistent
# notification scheduler.  Wiring it is a future, explicitly reviewed change.
NOTIFICATION_EVENT_CATALOG: tuple[NotificationEventDefinition, ...] = (
    NotificationEventDefinition(
        "journey_detected",
        "Journey found",
        "routine",
        "Confirm the selected calendar journey and its planned departure.",
        True,
    ),
    NotificationEventDefinition(
        "wake_1",
        "Wake-up reminder",
        "time_sensitive",
        "First preparation reminder.",
        True,
    ),
    NotificationEventDefinition(
        "wake_2",
        "Wake-up reminder",
        "time_sensitive",
        "Second preparation reminder.",
        True,
    ),
    NotificationEventDefinition(
        "wake_3",
        "Wake-up reminder",
        "time_sensitive",
        "Final preparation reminder.",
        True,
    ),
    NotificationEventDefinition(
        "leave_now",
        "Leave now",
        "critical",
        "Actionable station-access reminder with the selected access mode.",
        True,
    ),
    NotificationEventDefinition(
        "rail_on_time",
        "Rail status",
        "routine",
        "Checkpoint confirmation with platform and calling-point evidence.",
        False,
    ),
    NotificationEventDefinition(
        "rail_change",
        "Rail change",
        "time_sensitive",
        "A material platform, delay, cancellation, or calling-point change.",
        True,
    ),
    NotificationEventDefinition(
        "connection_at_risk",
        "Connection at risk",
        "critical",
        "A live arrival leaves too little time for the configured interchange.",
        True,
    ),
    NotificationEventDefinition(
        "provider_unavailable",
        "Live rail unavailable",
        "routine",
        "Live data is unavailable; conservative calendar timing remains active.",
        True,
    ),
    NotificationEventDefinition(
        "journey_cancelled",
        "Service cancelled",
        "critical",
        "The selected service is reported cancelled by the live provider.",
        True,
    ),
)


def event_definition(key: str) -> NotificationEventDefinition | None:
    """Return a planned event definition without raising for unknown events."""
    return next(
        (event for event in NOTIFICATION_EVENT_CATALOG if event.key == key),
        None,
    )


def default_enabled_event_keys() -> frozenset[str]:
    """Return the future default event selection for an explicit user opt-in."""
    return frozenset(
        event.key for event in NOTIFICATION_EVENT_CATALOG if event.default_enabled
    )
