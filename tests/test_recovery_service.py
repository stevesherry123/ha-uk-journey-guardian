"""Exercise the Home Assistant recovery command through its registered service."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from custom_components.journey_guardian import _async_register_services
from custom_components.journey_guardian.connection_store import ConfirmedConnection
from custom_components.journey_guardian.const import DOMAIN
from custom_components.journey_guardian.railinfo_recovery import (
    normalize_railinfo_recovery,
)
from custom_components.journey_guardian.recovery_runtime import RecoveryRuntime
from custom_components.journey_guardian.travel_plan import RetainedLeg

NOW = datetime(2026, 11, 7, 10, tzinfo=UTC)
COMMAND = {
    "affected_booking_id": "a" * 64,
    "final_booking_id": "b" * 64,
    "origin": "Example Central",
}


def booking(key, origin, destination, departure, arrival):
    return RetainedLeg(
        key * 64,
        (NOW + timedelta(minutes=departure)).isoformat(),
        (NOW + timedelta(minutes=arrival)).isoformat(),
        origin,
        destination,
        NOW.isoformat(),
        NOW.isoformat(),
    )


def runtime_fixture():
    first = booking("a", "Example Central", "Example Junction", 15, 45)
    final = booking("b", "Example Junction", "Sample Harbour", 60, 90)
    other = booking("c", "Sample Harbour", "Example Central", 150, 210)
    confirmed = ConfirmedConnection(
        first.booking_id,
        final.booking_id,
        NOW.isoformat(),
        (NOW + timedelta(hours=2)).isoformat(),
    )
    coordinator = Mock()
    coordinator.data = SimpleNamespace(simulation_active=False, error=None)
    coordinator.last_successful_calendar_review_at = NOW
    coordinator.last_calendar_source_refresh_error = None
    coordinator.connection_confirmations.persistence_error = False
    coordinator.connection_confirmations.active.return_value = (confirmed,)
    coordinator.travel_plan.recovery_bookings.return_value = (first, final, other)
    coordinator.station_transfers = {"example junction": 12}
    coordinator.transfer_fallback = 10
    stations = {
        "example central": "EXC",
        "sample harbour": "SMP",
        "example junction": "EXJ",
    }

    async def resolve(*, name, **_):
        return SimpleNamespace(code=stations[name.casefold()])

    async def search(request, *, force_refresh=False, **policy):
        return normalize_railinfo_recovery(
            {
                "date": "2026-11-07",
                "is_today": True,
                "journeys": [
                    {
                        "changes": 0,
                        "status": "on_time",
                        "legs": [
                            {
                                "from_crs": "EXC",
                                "to_crs": "SMP",
                                "dep": "1030",
                                "arr": "1130",
                                "expected_dep": "1030",
                                "expected_arr": "1130",
                                "headcode": "1A23",
                                "mode": "train",
                                "status": "on_time",
                                "status_source": "darwin",
                            }
                        ],
                    }
                ],
            },
            request,
            observed_at=NOW,
            now=NOW,
            **policy,
        )

    coordinator.engine._async_resolve_station = AsyncMock(side_effect=resolve)
    client = SimpleNamespace(async_recovery_search=AsyncMock(side_effect=search))
    with patch(
        "custom_components.journey_guardian.recovery_runtime.dt_util.utcnow",
        return_value=NOW,
    ):
        recovery = RecoveryRuntime(coordinator, client)
    coordinator.recovery_runtime = recovery
    return recovery, coordinator, client


async def test_service_publishes_complete_routes_and_excludes_unrelated_return(hass):
    recovery, coordinator, client = runtime_fixture()
    with (
        patch(
            "custom_components.journey_guardian._runtime",
            return_value=SimpleNamespace(coordinator=coordinator),
        ),
        patch(
            "custom_components.journey_guardian.recovery_runtime.dt_util.utcnow",
            return_value=NOW,
        ),
    ):
        _async_register_services(hass)
        result = await hass.services.async_call(
            DOMAIN,
            "review_recovery",
            COMMAND,
            blocking=True,
            return_response=True,
        )
        dashboard = recovery.dashboard(NOW)
        option = dashboard["options"][0]
        selection = await hass.services.async_call(
            DOMAIN,
            "select_recovery",
            {"option_id": option["option_id"], "revision": option["revision"]},
            blocking=True,
            return_response=True,
        )
        selected = recovery.dashboard(NOW)
    assert result == {"status": "options_available"}
    assert selection == {"status": "selection_verified"}
    assert selected["selected_option_id"] == option["option_id"]
    assert client.async_recovery_search.await_count == 2
    assert client.async_recovery_search.await_args.kwargs["force_refresh"] is True
    request = client.async_recovery_search.await_args.args[0]
    assert request.final_destination_code == "SMP"
    assert dashboard["options"][0]["legs"][-1]["destination"] == "SMP"
    assert [leg["id"] for leg in dashboard["affected"]] == ["a" * 64, "b" * 64]
    assert [leg["id"] for leg in dashboard["bookings"]] == ["a" * 64, "b" * 64]
    assert coordinator.async_update_listeners.call_count == 2


async def test_stale_calendar_blocks_station_resolution_and_search():
    recovery, coordinator, client = runtime_fixture()
    coordinator.last_successful_calendar_review_at = NOW - timedelta(minutes=16)
    with patch(
        "custom_components.journey_guardian.recovery_runtime.dt_util.utcnow",
        return_value=NOW,
    ):
        assert await recovery.async_search(**COMMAND) == "review_unavailable"
    coordinator.engine._async_resolve_station.assert_not_awaited()
    client.async_recovery_search.assert_not_awaited()


async def test_revocation_during_station_lookup_blocks_route_search():
    recovery, coordinator, client = runtime_fixture()
    original = coordinator.engine._async_resolve_station.side_effect

    async def resolve(**kwargs):
        coordinator.connection_confirmations.active.return_value = ()
        return await original(**kwargs)

    coordinator.engine._async_resolve_station.side_effect = resolve
    with patch(
        "custom_components.journey_guardian.recovery_runtime.dt_util.utcnow",
        return_value=NOW,
    ):
        assert await recovery.async_search(**COMMAND) == "review_unavailable"
        assert not recovery.dashboard(NOW)["options"]
    client.async_recovery_search.assert_not_awaited()
