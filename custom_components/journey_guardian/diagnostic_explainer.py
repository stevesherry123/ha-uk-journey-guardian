"""Turn sanitized live-check records into short human review notes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def explain_live_checks(records: Sequence[Mapping[str, object]]) -> list[str]:
    """Explain only stable diagnostic categories; never expose journey text."""
    notes: list[str] = []
    for record in records:
        if record.get("error_category") != "rail_schedule_mismatch":
            continue
        offset = record.get("schedule_offset_minutes")
        if isinstance(offset, int):
            direction = "later" if offset > 0 else "earlier"
            notes.append(
                "Provider candidate was "
                f"{abs(offset)} minutes {direction} than the calendar departure."
            )
        else:
            notes.append("Provider timetable did not match the calendar departure.")
    return notes
