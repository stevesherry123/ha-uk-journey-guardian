"""Rail actions fail closed when Home Assistant cannot verify a durable write."""

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.journey_guardian.verified_rail_store import VerifiedRailStore


async def test_logged_storage_failure_cannot_authorize_new_state(hass):
    store = VerifiedRailStore(hass, "journey_guardian.fictional")
    original = {"schema": 1, "keys": ["original"]}
    await store.async_save(original)
    with (
        patch.object(store, "_async_write_data", AsyncMock(return_value=None)),
        pytest.raises(OSError, match="rail_storage_write_unverified"),
    ):
        await store.async_save({"schema": 1, "keys": ["original", "new"]})
    assert await store.async_load() == original
