"""Tests for the shared TransportAPI quota policy."""

from custom_components.journey_guardian.quota import can_reserve_call


def test_routine_calls_stop_before_urgent_reserve() -> None:
    assert can_reserve_call(
        calls_used=26, daily_limit=30, urgent_reserve=3, urgent=False
    )
    assert not can_reserve_call(
        calls_used=27, daily_limit=30, urgent_reserve=3, urgent=False
    )


def test_urgent_calls_can_use_reserve_but_not_exceed_limit() -> None:
    assert can_reserve_call(
        calls_used=29, daily_limit=30, urgent_reserve=3, urgent=True
    )
    assert not can_reserve_call(
        calls_used=30, daily_limit=30, urgent_reserve=3, urgent=True
    )
