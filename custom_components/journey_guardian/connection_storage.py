"""Home Assistant lifecycle adapter for connection confirmation storage."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .connection_store import ConnectionConfirmationStore
from .verified_rail_store import VerifiedRailStore

_LOGGER = logging.getLogger(__name__)


class HAConnectionConfirmations(ConnectionConfirmationStore):
    """Scope private storage and keep unavailable confirmations dormant."""

    def __init__(self, hass: HomeAssistant, *, scope: str) -> None:
        scope_hash = hashlib.sha256(scope.encode()).hexdigest()
        storage = VerifiedRailStore(
            hass, f"journey_guardian.connections.{scope_hash[:24]}"
        )
        super().__init__(storage, scope=scope_hash)
        self.persistence_error = False

    async def async_load(self, now: datetime) -> None:
        try:
            await super().async_load(now)
        except (HomeAssistantError, OSError, ValueError, TypeError, OverflowError):
            self.persistence_error = True
            _LOGGER.warning(
                "Connection confirmations unavailable; confirmation disabled"
            )
            return
        self.persistence_error = False
