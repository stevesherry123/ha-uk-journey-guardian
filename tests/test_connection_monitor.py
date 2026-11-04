"""Bounded connection acquisition must survive reload without provider bursts."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.journey_guardian.connection_evidence import (
    EvidenceConnectionAssessment,
)
from custom_components.journey_guardian.connection_monitor import (
    ConnectionCheckLedger,
    ConnectionMonitor,
    checkpoint_key,
)

NOW = datetime(2026, 11, 4, 10, tzinfo=UTC)
PAIR = ("a" * 64, "b" * 64)


async def ledger():
    storage = AsyncMock()
    storage.async_load.return_value = None
    result = ConnectionCheckLedger(storage, scope="fictional-scope")
    await result.async_load()
    return result, storage


def coordinator():
    result = Mock()
    result.data.simulation_active = False
    result.data.error = None
    result.engine._live_rail_provider = "railinfo"
    result.connection_dashboard.return_value = {
        "connections": [
            {
                "inbound_id": PAIR[0],
                "outbound_id": PAIR[1],
                "confirmed": True,
                "can_confirm": True,
                "allowance_minutes": 10,
                "inbound_arrival": (NOW + timedelta(minutes=15)).isoformat(),
                "outbound_departure": (NOW + timedelta(minutes=30)).isoformat(),
            }
        ]
    }
    result.connection_assessments = {}
    result.travel_plan.connection_pair.return_value = (Mock(), Mock())
    return result


async def test_claims_survive_restart_and_enforce_spacing_and_daily_limit():
    claims, storage = await ledger()
    assert await claims.async_claim("a" * 64, NOW)
    storage.async_load.return_value = storage.async_save.call_args.args[0]
    restored = ConnectionCheckLedger(storage, scope="fictional-scope")
    await restored.async_load()
    assert not await restored.async_claim("a" * 64, NOW + timedelta(minutes=6))
    assert not await restored.async_claim("b" * 64, NOW + timedelta(minutes=1))
    for index in range(1, 8):
        assert await restored.async_claim(
            f"{index:064x}", NOW + timedelta(minutes=6 * index)
        )
    assert not await restored.async_claim("f" * 64, NOW + timedelta(hours=1))
    assert await restored.async_claim("f" * 64, NOW + timedelta(days=1))


async def test_failed_claim_write_cannot_commit_or_authorize_check():
    claims, storage = await ledger()
    storage.async_save.side_effect = OSError()
    with pytest.raises(OSError):
        await claims.async_claim("a" * 64, NOW)
    assert not claims.eligible("a" * 64, NOW)


async def test_disabled_monitor_registers_no_listener_or_timer(hass):
    state = coordinator()
    claims, _ = await ledger()
    with patch(
        "custom_components.journey_guardian.connection_monitor.async_track_point_in_utc_time"
    ) as timer:
        monitor = ConnectionMonitor(hass, state, claims)
        monitor.start()
        state.async_add_listener.assert_not_called()
        timer.assert_not_called()


async def test_confirmed_pair_checks_once_and_stop_cleans_up(hass):
    state = coordinator()
    claims, storage = await ledger()
    assessment = EvidenceConnectionAssessment(
        "at_risk", "below_transfer_allowance", NOW, 10, 7, -3
    )
    with (
        patch(
            "custom_components.journey_guardian.connection_monitor.dt_util.now",
            return_value=NOW,
        ),
        patch(
            "custom_components.journey_guardian.connection_monitor.async_track_point_in_utc_time"
        ) as timer,
        patch(
            "custom_components.journey_guardian.connection_monitor.async_review_connection",
            new=AsyncMock(return_value=(assessment, NOW + timedelta(minutes=5))),
        ) as review,
    ):
        monitor = ConnectionMonitor(hass, state, claims, enabled=True)
        monitor.start()
        assert timer.call_args.args[2] == NOW
        await monitor._run(PAIR, NOW)
        await monitor._run(PAIR, NOW)
        review.assert_awaited_once()
        assert state.connection_assessments[PAIR][0] == assessment
        assert storage.async_save.await_count == 1
        monitor.stop()
        state.async_add_listener.return_value.assert_called_once()
        assert state.next_connection_check_at is None


@pytest.mark.parametrize("case", ["simulation", "calendar", "provider", "unconfirmed"])
async def test_invalid_context_never_claims_or_acquires(hass, case):
    state = coordinator()
    claims, storage = await ledger()
    if case == "simulation":
        state.data.simulation_active = True
    elif case == "calendar":
        state.data.error = "calendar_unavailable"
    elif case == "provider":
        state.engine._live_rail_provider = "transportapi"
    else:
        state.connection_dashboard.return_value["connections"][0]["confirmed"] = False
    with patch(
        "custom_components.journey_guardian.connection_monitor.async_review_connection",
        new=AsyncMock(),
    ) as review:
        monitor = ConnectionMonitor(hass, state, claims, enabled=True)
        monitor._stopped = False
        await monitor._run(PAIR, NOW)
        review.assert_not_awaited()
        storage.async_save.assert_not_awaited()


async def test_revocation_during_check_discards_result(hass):
    state = coordinator()
    claims, _ = await ledger()

    async def review(*args, **kwargs):
        state.connection_dashboard.return_value = {"connections": []}
        return Mock(), NOW + timedelta(minutes=5)

    with (
        patch(
            "custom_components.journey_guardian.connection_monitor.dt_util.now",
            return_value=NOW,
        ),
        patch(
            "custom_components.journey_guardian.connection_monitor.async_review_connection",
            side_effect=review,
        ),
    ):
        monitor = ConnectionMonitor(hass, state, claims, enabled=True)
        monitor._stopped = False
        await monitor._run(PAIR, NOW)
        assert not state.connection_assessments


def test_checkpoint_identity_uses_pair_and_instant():
    assert checkpoint_key(PAIR, NOW) != checkpoint_key(PAIR[::-1], NOW)


async def test_failed_ledger_save_pauses_monitor_without_retry_burst(hass):
    state = coordinator()
    claims, storage = await ledger()
    storage.async_save.side_effect = OSError()
    with (
        patch(
            "custom_components.journey_guardian.connection_monitor.dt_util.now",
            return_value=NOW,
        ),
        patch(
            "custom_components.journey_guardian.connection_monitor.async_track_point_in_utc_time"
        ) as timer,
        patch(
            "custom_components.journey_guardian.connection_monitor.async_review_connection",
            new=AsyncMock(),
        ) as review,
    ):
        monitor = ConnectionMonitor(hass, state, claims, enabled=True)
        monitor._stopped = False
        await monitor._run(PAIR, NOW)
        review.assert_not_awaited()
        timer.assert_not_called()
        assert state.next_connection_check_at is None
        assert state.connection_assessments[PAIR][0].classification == "unknown"


async def test_monitor_passes_fresh_risk_to_durable_alert_controller(hass):
    from custom_components.journey_guardian.connection_alerts import (
        ConnectionAlertController,
        ConnectionAlertLedger,
    )

    state = coordinator()
    claims, _ = await ledger()
    storage = AsyncMock()
    storage.async_load.return_value = None
    alert_ledger = ConnectionAlertLedger(storage, scope="fictional-scope")
    await alert_ledger.async_load(NOW)
    scheduler = Mock(connection_notices_enabled=True)
    scheduler.async_connection_notice = AsyncMock(return_value="announcement_engine")
    state.travel_plan.connection_pair.return_value[0].destination = "Example Junction"
    state.travel_plan.connection_pair.return_value[1].expiry = NOW + timedelta(days=1)
    risk = EvidenceConnectionAssessment(
        "at_risk", "below_transfer_allowance", NOW, 10, 7, -3
    )
    with (
        patch(
            "custom_components.journey_guardian.connection_monitor.dt_util.now",
            return_value=NOW,
        ),
        patch(
            "custom_components.journey_guardian.connection_monitor.async_track_point_in_utc_time"
        ),
        patch(
            "custom_components.journey_guardian.connection_monitor.async_review_connection",
            new=AsyncMock(return_value=(risk, NOW + timedelta(minutes=5))),
        ),
    ):
        monitor = ConnectionMonitor(
            hass,
            state,
            claims,
            enabled=True,
            alerts=ConnectionAlertController(alert_ledger, scheduler),
        )
        monitor._stopped = False
        await monitor._run(PAIR, NOW)
    scheduler.async_connection_notice.assert_awaited_once()
    assert alert_ledger.status(PAIR, now=NOW)["delivery"] == "announcement_engine"
