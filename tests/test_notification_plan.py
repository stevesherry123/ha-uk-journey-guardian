"""Tests for the inactive notification delivery foundation."""

from custom_components.journey_guardian.notification_plan import (
    NOTIFICATION_EVENT_CATALOG,
    default_enabled_event_keys,
    event_definition,
)


def test_notification_plan_has_unique_stable_event_keys() -> None:
    """The future UI and delivery ledger can safely rely on the vocabulary."""
    keys = [event.key for event in NOTIFICATION_EVENT_CATALOG]

    assert len(keys) == len(set(keys))
    assert event_definition("leave_now").urgency == "critical"  # type: ignore[union-attr]
    assert event_definition("not_an_event") is None


def test_default_plan_prioritises_actionable_events_over_reassurance() -> None:
    """Routine on-time updates stay opt-in to prevent notification fatigue."""
    enabled = default_enabled_event_keys()

    assert {"wake_1", "wake_2", "wake_3", "leave_now"} <= enabled
    assert "rail_change" in enabled
    assert "rail_on_time" not in enabled
