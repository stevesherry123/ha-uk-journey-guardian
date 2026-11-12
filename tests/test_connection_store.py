"""Exact booking confirmation, persistence and failed-write boundaries."""

from contextlib import suppress
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from custom_components.journey_guardian.connection_store import (
    ConfirmedConnection,
    ConnectionConfirmationStore,
)

NOW = datetime(2026, 11, 3, 8, tzinfo=UTC)
RECORD = ConfirmedConnection(
    "a" * 64, "b" * 64, NOW.isoformat(),
    (NOW + timedelta(hours=12)).isoformat(), 12,
)


async def test_confirmation_survives_restart_but_not_booking_edit_or_expiry():
    storage = AsyncMock()
    storage.async_load.return_value = None
    store = ConnectionConfirmationStore(storage, scope="fictional-scope")
    await store.async_load(NOW)
    await store.async_confirm(RECORD, now=NOW)
    storage.async_load.return_value = storage.async_save.call_args.args[0]
    restored = ConnectionConfirmationStore(storage, scope="fictional-scope")
    await restored.async_load(NOW)
    assert restored.get("a" * 64, "b" * 64, now=NOW) == RECORD
    assert restored.get("a" * 64, "c" * 64, now=NOW) is None
    assert restored.get("a" * 64, "b" * 64, now=NOW + timedelta(days=1)) is None


async def test_failed_save_does_not_confirm():
    storage = AsyncMock()
    storage.async_load.return_value = None
    storage.async_save.side_effect = OSError("fictional failure")
    store = ConnectionConfirmationStore(storage, scope="fictional-scope")
    await store.async_load(NOW)
    try:
        await store.async_confirm(RECORD, now=NOW)
    except OSError:
        pass
    else:
        raise AssertionError("Save failure hidden")
    assert store.get(RECORD.inbound_id, RECORD.outbound_id, now=NOW) is None


async def test_scope_mismatch_blocks_writes():
    storage = AsyncMock()
    storage.async_load.return_value = {"schema": 1, "scope": "other", "records": []}
    store = ConnectionConfirmationStore(storage, scope="fictional-scope")
    for action in (store.async_load(NOW), store.async_confirm(RECORD, now=NOW)):
        try:
            await action
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid storage accepted")
    storage.async_save.assert_not_called()


async def test_revocation_survives_restart_and_failed_save_keeps_confirmation():
    storage = AsyncMock()
    storage.async_load.return_value = None
    store = ConnectionConfirmationStore(storage, scope="fictional-scope")
    await store.async_load(NOW)
    await store.async_confirm(RECORD, now=NOW)
    storage.async_save.side_effect = OSError()
    with suppress(OSError):
        await store.async_revoke(RECORD.inbound_id, RECORD.outbound_id)
    assert store.get(RECORD.inbound_id, RECORD.outbound_id, now=NOW) == RECORD
    storage.async_save.side_effect = None
    await store.async_revoke(RECORD.inbound_id, RECORD.outbound_id)
    storage.async_load.return_value = storage.async_save.call_args.args[0]
    restored = ConnectionConfirmationStore(storage, scope="fictional-scope")
    await restored.async_load(NOW)
    assert restored.get(RECORD.inbound_id, RECORD.outbound_id, now=NOW) is None
