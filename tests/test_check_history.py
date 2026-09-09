"""Tests for restart-safe live-check history."""

from unittest.mock import AsyncMock

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
                "secret": "must-not-survive",
            }
        )

    records = history.records()
    assert len(records) == MAX_RECORDS
    assert records[0]["checked_at"] == "2"
    assert records[0]["schedule_offset_minutes"] == 11
    assert all("secret" not in record for record in records)


async def test_history_restores_only_mappings(hass) -> None:
    """Malformed stored values cannot break integration setup."""
    history = CheckHistory(hass)
    history._store.async_load = AsyncMock(
        return_value={"records": ["bad", {"outcome": "failed"}]}
    )

    await history.async_load()

    assert history.records() == [{"outcome": "failed"}]
