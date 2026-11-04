"""Connection alerts remain meaningful, bounded and restart-safe."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.journey_guardian.connection_alerts import (
    ConnectionAlertController,
    ConnectionAlertLedger,
    connection_message,
)
from custom_components.journey_guardian.connection_evidence import (
    EvidenceConnectionAssessment,
)

NOW = datetime(2026, 11, 4, 10, tzinfo=UTC)
PAIR = ("a" * 64, "b" * 64)
EXPIRY = NOW + timedelta(days=2)
RISK = EvidenceConnectionAssessment(
    "at_risk", "below_transfer_allowance", NOW, 10, 8, -2
)


async def ledger(data=None):
    storage = AsyncMock()
    storage.async_load.return_value = data
    result = ConnectionAlertLedger(storage, scope="fictional")
    await result.async_load(NOW)
    return result, storage


async def claim(store, assessment=RISK, minutes=0):
    return await store.async_claim(
        PAIR, assessment, now=NOW + timedelta(minutes=minutes), expires_at=EXPIRY
    )


async def test_first_risk_then_unchanged_and_small_changes_stay_silent():
    store, storage = await ledger()
    first = await claim(store)
    assert first[2] == "risk"
    await store.async_record_delivery(first, "announcement_engine")
    assert await claim(store, minutes=5) is None
    assert await claim(store, replace(RISK, minutes_available=7), minutes=10) is None
    assert storage.async_save.await_count == 2
    assert store.status(PAIR, now=NOW)["receipt_confirmed"] is False


async def test_meaningful_update_recovery_hysteresis_and_new_risk():
    store, _ = await ledger()
    await claim(store)
    assert (await claim(store, replace(RISK, minutes_available=3), minutes=5))[
        2
    ] == "update"
    barely_viable = replace(
        RISK, classification="viable", minutes_available=11, margin_minutes=1
    )
    assert await claim(store, barely_viable, minutes=10) is None
    recovered = replace(barely_viable, minutes_available=12, margin_minutes=2)
    assert (await claim(store, recovered, minutes=10))[2] == "recovered"
    assert await claim(store, recovered, minutes=15) is None
    assert (await claim(store, minutes=15))[2] == "risk"


async def test_unknown_does_not_clear_warning_or_invent_recovery():
    store, _ = await ledger()
    await claim(store)
    unknown = replace(
        RISK, classification="unknown", minutes_available=None, margin_minutes=None
    )
    assert await claim(store, unknown, minutes=5) is None
    assert await claim(store, minutes=10) is None
    assert store.status(PAIR, now=NOW)["kind"] == "risk"


async def test_restart_after_claim_does_not_replay_uncertain_delivery():
    store, storage = await ledger()
    await claim(store)
    restored, _ = await ledger(storage.async_save.call_args.args[0])
    assert await claim(restored, minutes=5) is None
    assert restored.status(PAIR, now=NOW)["delivery"] == "claimed"


async def test_failed_claim_save_blocks_delivery_until_successful_reload():
    store, storage = await ledger()
    storage.async_save.side_effect = OSError()
    with pytest.raises(OSError):
        await claim(store)
    assert not store.available
    assert store.status(PAIR, now=NOW) is None
    with pytest.raises(ValueError, match="storage_unavailable"):
        await claim(store, minutes=5)


async def test_failed_delivery_status_save_cannot_replay_the_claim():
    store, storage = await ledger()
    first = await claim(store)
    durable_claim = storage.async_save.call_args.args[0]
    storage.async_save.side_effect = OSError()
    with pytest.raises(OSError):
        await store.async_record_delivery(first, "announcement_engine")
    restored, _ = await ledger(durable_claim)
    assert await claim(restored, minutes=5) is None


async def test_alert_cooldown_and_initial_viable_do_not_send():
    store, _ = await ledger()
    viable = replace(
        RISK, classification="viable", minutes_available=15, margin_minutes=5
    )
    assert await claim(store, viable) is None
    await claim(store)
    assert await claim(store, replace(RISK, minutes_available=0), minutes=1) is None


@pytest.mark.parametrize("case", ["disabled", "expired", "revoked", "unknown"])
async def test_controller_suppresses_ineligible_alerts_before_claim(case):
    store, storage = await ledger()
    scheduler = Mock()
    scheduler.connection_notices_enabled = case != "disabled"
    scheduler.async_connection_notice = AsyncMock(return_value="announcement_engine")
    controller = ConnectionAlertController(store, scheduler)
    assessment = replace(RISK, classification="unknown") if case == "unknown" else RISK
    with patch(
        "custom_components.journey_guardian.connection_alerts.dt_util.now",
        return_value=NOW,
    ):
        await controller.async_process(
            PAIR,
            assessment,
            NOW - timedelta(seconds=1)
            if case == "expired"
            else NOW + timedelta(minutes=5),
            station="Example Junction",
            expires_at=EXPIRY,
            is_current=lambda: case != "revoked",
        )
    storage.async_save.assert_not_awaited()
    scheduler.async_connection_notice.assert_not_awaited()


async def test_controller_delivers_once_and_records_handoff_without_receipt_claim():
    store, _ = await ledger()
    scheduler = Mock(connection_notices_enabled=True)
    scheduler.async_connection_notice = AsyncMock(
        return_value="persistent_notification"
    )
    controller = ConnectionAlertController(store, scheduler)
    with patch(
        "custom_components.journey_guardian.connection_alerts.dt_util.now",
        return_value=NOW,
    ):
        for _ in range(2):
            await controller.async_process(
                PAIR,
                RISK,
                NOW + timedelta(minutes=5),
                station="Example Junction",
                expires_at=EXPIRY,
                is_current=lambda: True,
            )
    scheduler.async_connection_notice.assert_awaited_once()
    assert store.status(PAIR, now=NOW)["delivery"] == "persistent_notification"
    assert not store.status(PAIR, now=NOW)["receipt_confirmed"]


def test_negative_margin_wording_does_not_claim_missed_or_negative_transfer_time():
    message = connection_message(
        "Example Junction", replace(RISK, minutes_available=-3), "risk"
    )
    assert "3 minutes after onward departure" in message
    assert "missed" not in message
    assert "-3 minutes" not in message


async def test_wrong_scope_and_future_claim_cannot_enable_alerts():
    store, storage = await ledger()
    await claim(store)
    data = storage.async_save.call_args.args[0]
    for changed in (data | {"scope": "another"}, data | {"schema": True}):
        with pytest.raises(ValueError):
            await ledger(changed)


async def test_future_assessment_is_not_announced_after_clock_moves_back():
    store, storage = await ledger()
    scheduler = Mock(connection_notices_enabled=True)
    scheduler.async_connection_notice = AsyncMock()
    with patch(
        "custom_components.journey_guardian.connection_alerts.dt_util.now",
        return_value=NOW,
    ):
        await ConnectionAlertController(store, scheduler).async_process(
            PAIR,
            replace(RISK, assessed_at=NOW + timedelta(minutes=1)),
            NOW + timedelta(minutes=5),
            station="Example Junction",
            expires_at=EXPIRY,
            is_current=lambda: True,
        )
    storage.async_save.assert_not_awaited()
    scheduler.async_connection_notice.assert_not_awaited()


def test_warning_includes_live_times_and_remains_short_for_existing_helper():
    message = connection_message(
        "Example Junction " * 20,
        replace(
            RISK,
            inbound_event_at=NOW + timedelta(minutes=12),
            outbound_event_at=NOW + timedelta(minutes=20),
        ),
        "risk",
    )
    assert "Arrival 10:12 GMT, onward 10:20 GMT" in message
    assert len(message) <= 255


async def test_concurrent_refreshes_cannot_claim_duplicate_warning():
    import asyncio

    store, storage = await ledger()
    results = await asyncio.gather(claim(store), claim(store))
    assert sum(result is not None for result in results) == 1
    assert storage.async_save.await_count == 1
