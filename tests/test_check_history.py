"""Tests for restart-safe live-check history."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from custom_components.journey_guardian.check_history import (
    MAX_RECORDS,
    CheckHistory,
)


async def test_history_is_bounded_and_sanitized(hass) -> None:
    """Only allow-listed metadata is retained."""
    history = CheckHistory(hass)
    history._store.async_save = AsyncMock()

    for index in range(MAX_RECORDS + 2):
        await history.async_record(
            {
                "checked_at": str(index),
                "outcome": "success",
                "schedule_offset_minutes": 11,
                "actual_arrival": "2026-09-28T21:28:00+01:00",
                "arrival_delay_minutes": 18,
                "completion_status": "completed",
                "secret": "must-not-survive",
            }
        )

    records = history.records()
    assert len(records) == MAX_RECORDS
    assert records[0]["checked_at"] == "2"
    assert records[0]["schedule_offset_minutes"] == 11
    assert records[0]["arrival_delay_minutes"] == 18
    assert records[0]["completion_status"] == "completed"
    assert all("secret" not in record for record in records)


async def test_history_restores_only_mappings(hass) -> None:
    """Malformed stored values cannot break integration setup."""
    history = CheckHistory(hass)
    history._store.async_load = AsyncMock(
        return_value={"records": ["bad", {"outcome": "failed"}]}
    )

    await history.async_load()

    assert history.records() == [{"outcome": "failed"}]


@pytest.mark.parametrize("latest", [
    {"outcome": "success"},
    {"booking_check_failure": "railinfo_provider_unavailable"},
    {"booking_check_recorded_at": "2026-11-08T08:00:00+00:00"},
    {"booking_check_recorded_at": "2026-11-07T08:00:00"},
    {"stage": "invalid"},
])
async def test_history_does_not_restore_superseded_or_invalid_warning(hass, latest):
    now = datetime(2026, 11, 7, 8, tzinfo=UTC)
    failure = {
        "operation": "station_timetables",
        "booking_check_key": "example-key",
        "booking_check_recorded_at": now.isoformat(),
        "booking_check_failure": "railinfo_rail_schedule_mismatch",
        "stage": "match_timetable",
        "outcome": "failed",
    }
    history = CheckHistory(hass)
    history._store.async_load = AsyncMock(
        return_value={"records": [failure, {**failure, **latest}]}
    )
    await history.async_load()
    assert history.booking_issue("example-key", "fingerprint", now) is None


async def test_legacy_history_cannot_restore_a_booking_warning(hass):
    history = CheckHistory(hass)
    history._store.async_load = AsyncMock(return_value={"records": [{
        "operation": "station_timetables",
        "journey_fingerprint": "legacy-fingerprint",
        "error_category": "rail_schedule_mismatch",
        "outcome": "failed",
    }]})
    await history.async_load()
    assert history.booking_issue(
        "example-key", "fingerprint", datetime(2026, 11, 7, 8, tzinfo=UTC)
    ) is None
