"""HA storage scope and degraded-startup behaviour."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from custom_components.journey_guardian.connection_storage import (
    HAConnectionConfirmations,
)

NOW = datetime(2026, 11, 3, 8, tzinfo=UTC)


async def test_unreadable_storage_disables_confirmation_without_stopping_startup(hass):
    with patch(
        "custom_components.journey_guardian.connection_storage.VerifiedRailStore"
    ) as storage_class:
        storage_class.return_value.async_load = AsyncMock(side_effect=OSError())
        confirmations = HAConnectionConfirmations(hass, scope="private-calendar")
        await confirmations.async_load(NOW)
        assert confirmations.persistence_error
        assert confirmations.get("a" * 64, "b" * 64, now=NOW) is None
        storage_class.return_value.async_load = AsyncMock(return_value=None)
        await confirmations.async_load(NOW)
        assert not confirmations.persistence_error
        key = storage_class.call_args.args[1]
        assert "private-calendar" not in key
