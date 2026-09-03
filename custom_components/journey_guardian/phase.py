"""Operational phase decisions derived from normalized journey state."""

from __future__ import annotations

from datetime import datetime

from .models import JourneyTiming


def calculate_operational_phase(
    *,
    status: str,
    timing: JourneyTiming | None,
    departure: datetime | None,
    now: datetime,
    error: str | None = None,
) -> str:
    """Return the actionable phase without mixing it with journey lifecycle."""
    if error == "simulated_provider_unavailable":
        return "provider_unavailable"
    if status == "error":
        return "error"
    if status == "cancelled":
        return "cancelled"
    if departure is None:
        return "idle"
    if status == "active" or now >= departure:
        return "active"
    if timing is None or now < timing.prepare_at:
        return "waiting"
    if now < timing.leave_home_at:
        return "prepare_now"
    if now < timing.station_arrival_at:
        return "leave_now"
    return "at_station"


def future_phase_boundaries(
    timing: JourneyTiming | None,
    departure: datetime | None,
    now: datetime,
) -> tuple[tuple[str, datetime], ...]:
    """Return future boundaries that require an exact coordinator refresh."""
    if timing is None or departure is None:
        return ()
    return tuple(
        (phase, point)
        for phase, point in (
            ("prepare_now", timing.prepare_at),
            ("leave_now", timing.leave_home_at),
            ("at_station", timing.station_arrival_at),
            ("active", departure),
        )
        if point > now
    )
