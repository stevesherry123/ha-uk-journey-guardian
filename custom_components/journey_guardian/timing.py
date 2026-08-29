"""Pure journey timing calculations."""

from __future__ import annotations

from datetime import timedelta

from .models import JourneyEvent, JourneyTiming


def calculate_fallback_timing(
    journey: JourneyEvent,
    *,
    preparation_minutes: int,
    early_warning_minutes: int,
    station_buffer_minutes: int,
    station_access_minutes: int,
) -> JourneyTiming:
    """Calculate conservative timing from configured fallback durations."""
    station_arrival = journey.start - timedelta(minutes=station_buffer_minutes)
    leave_home = station_arrival - timedelta(minutes=station_access_minutes)
    prepare_at = leave_home - timedelta(
        minutes=preparation_minutes + early_warning_minutes
    )
    return JourneyTiming(
        prepare_at=prepare_at,
        leave_home_at=leave_home,
        station_arrival_at=station_arrival,
        preparation_minutes=preparation_minutes,
        early_warning_minutes=early_warning_minutes,
        station_buffer_minutes=station_buffer_minutes,
        station_access_minutes=station_access_minutes,
        source="configured_fallback",
        classification="inferred",
    )
