"""Verify durable rail decisions before using them to authorize work."""

import json
from typing import Any

from homeassistant.core import CoreState
from homeassistant.helpers.storage import Store


class VerifiedRailStore(Store[dict[str, Any]]):
    """An atomic, private Home Assistant store with write verification."""

    def __init__(self, hass, key):
        super().__init__(hass, 1, key, private=True, atomic_writes=True)

    async def async_save(self, data: dict[str, Any]) -> None:
        # HA Store can defer a write during shutdown, or log a write failure
        # without raising. Neither path can authorize a durable decision.
        if self.hass.state is CoreState.stopping:
            raise OSError("rail_storage_stopping")
        expected = json.loads(json.dumps(data))
        await super().async_save(expected)
        if await self.async_load() != expected:
            raise OSError("rail_storage_write_unverified")
