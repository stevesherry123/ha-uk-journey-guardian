"""Scheduled replacement checks share durable claims and follow current progress."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from custom_components.journey_guardian.connection_alerts import (
    ConnectionAlertController,
    ConnectionAlertLedger,
)
from custom_components.journey_guardian.connection_evidence import (
    ServiceReference,
    StationTimeEvidence,
)
from custom_components.journey_guardian.connection_monitor import ConnectionCheckLedger
from custom_components.journey_guardian.recovery_runtime import RecoveryRuntime
from custom_components.journey_guardian.recovery_tracking import (
    TrackedRecovery,
    TrackedRecoveryLeg,
)
from custom_components.journey_guardian.replacement_monitor import ReplacementMonitor

NOW = datetime(2026, 11, 8, 10, tzinfo=UTC)


def leg(origin, destination, departure, arrival):
    dep = (NOW + timedelta(minutes=departure)).isoformat()
    arr = (NOW + timedelta(minutes=arrival)).isoformat()
    return TrackedRecoveryLeg(
        origin, destination, "fictional-service", dep, arr, dep, arr
    )


async def test_restart_does_not_repeat_claimed_replacement_checkpoint(hass):
    record = TrackedRecovery(
        "a" * 64,
        "b" * 64,
        ("c" * 64,),
        NOW.isoformat(),
        (leg("EXC", "EXJ", 5, 30), leg("EXJ", "SMP", 45, 65)),
        transfer_minutes=10,
    )
    runtime = Mock()
    runtime.active_tracking.return_value = record
    runtime.async_check_tracking = AsyncMock()
    storage = SimpleNamespace(
        async_load=AsyncMock(return_value=None), async_save=AsyncMock()
    )
    ledger = ConnectionCheckLedger(storage, scope="fictional")
    await ledger.async_load()
    with (
        patch(
            "custom_components.journey_guardian.replacement_monitor.dt_util.utcnow",
            return_value=NOW,
        ),
        patch(
            "custom_components.journey_guardian.replacement_monitor.async_track_point_in_utc_time",
            return_value=Mock(),
        ) as schedule,
    ):
        monitor = ReplacementMonitor(hass, runtime, ledger)
        monitor.start()
        callback = schedule.call_args.args[1]
        await callback(NOW)
        runtime.async_check_tracking.assert_awaited_once_with(
            tracking_id=record.tracking_id,
            leg_index=0,
        )
        assert schedule.call_args.args[2] == NOW + timedelta(minutes=20)
        monitor.stop()

        storage.async_load.return_value = storage.async_save.await_args.args[0]
        restored = ConnectionCheckLedger(storage, scope="fictional")
        await restored.async_load()
        monitor = ReplacementMonitor(hass, runtime, restored)
        monitor.start()
        assert schedule.call_args.args[2] == NOW + timedelta(minutes=20)
        await callback(NOW)
        runtime.async_check_tracking.assert_awaited_once()
        monitor.stop()


async def test_checkpoint_for_old_leg_does_not_spend_shared_budget(hass):
    runtime = Mock()
    runtime.active_tracking.return_value = None
    runtime.async_check_tracking = AsyncMock()
    ledger = Mock()
    ledger.async_claim = AsyncMock()
    monitor = ReplacementMonitor(hass, runtime, ledger)
    with patch(
        "custom_components.journey_guardian.replacement_monitor.dt_util.utcnow",
        return_value=NOW,
    ):
        monitor.start()
        await monitor._run(NOW, "a" * 64, 0)
        monitor.stop()
    ledger.async_claim.assert_not_awaited()
    runtime.async_check_tracking.assert_not_awaited()


async def test_replacement_transfer_alert_is_fresh_and_deduplicated():
    inbound = leg("EXC", "EXJ", 5, 30)
    outbound = replace(leg("EXJ", "SMP", 45, 65), service_identity="fictional-onward")
    record = TrackedRecovery(
        "a" * 64,
        "b" * 64,
        ("c" * 64,),
        NOW.isoformat(),
        (inbound, outbound),
        transfer_minutes=10,
    )
    store = SimpleNamespace(record=record, available=True)
    coordinator = Mock()
    coordinator.data.simulation_active = False
    arrivals = StationTimeEvidence(
        ServiceReference("railinfo", inbound.service_identity),
        "EXJ",
        "arrival",
        "predicted",
        NOW + timedelta(minutes=39),
        NOW,
    )
    onward = StationTimeEvidence(
        ServiceReference("railinfo", outbound.service_identity),
        "EXJ",
        "departure",
        "predicted",
        NOW + timedelta(minutes=45),
        NOW,
    )
    client = Mock()
    client.async_arrival_prediction = AsyncMock(return_value=arrivals)
    client.async_departure_prediction = AsyncMock(
        side_effect=[None, onward, None, onward]
    )
    storage = SimpleNamespace(
        async_load=AsyncMock(return_value=None), async_save=AsyncMock()
    )
    ledger = ConnectionAlertLedger(storage, scope="fictional-replacement")
    await ledger.async_load(NOW)
    scheduler = Mock(connection_notices_enabled=True)
    scheduler.async_connection_notice = AsyncMock(return_value="announcement_engine")
    runtime = RecoveryRuntime(
        coordinator, client, store, alerts=ConnectionAlertController(ledger, scheduler)
    )
    with (
        patch(
            "custom_components.journey_guardian.recovery_runtime.dt_util.utcnow",
            return_value=NOW,
        ),
        patch(
            "custom_components.journey_guardian.connection_alerts.dt_util.now",
            return_value=NOW,
        ),
    ):
        for _ in range(2):
            assert (
                await runtime.async_check_tracking(
                    tracking_id=record.tracking_id, leg_index=0
                )
                == "tracking_checked"
            )
        fresh = runtime._tracking_dashboard(NOW)
        stale = runtime._tracking_dashboard(NOW + timedelta(minutes=6))
    assert fresh["transfer"]["classification"] == "at_risk"
    assert fresh["transfer"]["minutes_available"] == 6
    assert stale["transfer"]["classification"] == "unknown"
    assert stale["last_alert"]["kind"] == "risk"
    scheduler.async_connection_notice.assert_awaited_once()
