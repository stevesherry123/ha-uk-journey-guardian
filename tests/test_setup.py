"""Tests for integration-wide Journey Guardian setup."""

from datetime import UTC, datetime
from unittest.mock import ANY, AsyncMock, Mock, patch

from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.journey_guardian import (
    async_setup_entry,
    configured_provider_credentials,
)
from custom_components.journey_guardian.const import (
    CONF_CALENDAR_ENTITY,
    DOMAIN,
    SERVICE_CLEAR_SIMULATION,
    SERVICE_REVIEW_NOW,
    SERVICE_REVIEW_RAIL_NOW,
    SERVICE_SIMULATE_JOURNEY,
)
from custom_components.journey_guardian.provider_broker import ProviderRequestBroker


async def test_entry_setup_wires_dormant_provider_broker(hass) -> None:
    """Loading the integration cannot reserve quota or contact a provider."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CALENDAR_ENTITY: ".".join(("calendar", "example_travel"))
        },
    )
    entry.add_to_hass(hass)
    budget = Mock()
    budget.async_load = AsyncMock()
    budget.async_reserve_call = AsyncMock()
    coordinator = Mock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    ledger = Mock()
    ledger.async_load = AsyncMock()
    scheduler = Mock()
    automatic_rail_ledger = Mock()
    automatic_rail_ledger.async_load = AsyncMock()
    automatic_rail_monitor = Mock()
    station_access_monitor = Mock()
    transportapi_client = Mock()

    with (
        patch(
            "custom_components.journey_guardian.TransportAPIBudget",
            return_value=budget,
        ),
        patch("custom_components.journey_guardian.JourneyGuardianEngine"),
        patch(
            "custom_components.journey_guardian.JourneyGuardianCoordinator",
            return_value=coordinator,
        ),
        patch(
            "custom_components.journey_guardian.NotificationLedger",
            return_value=ledger,
        ),
        patch(
            "custom_components.journey_guardian.JourneyNotificationScheduler",
            return_value=scheduler,
        ),
        patch(
            "custom_components.journey_guardian.AutomaticRailLedger",
            return_value=automatic_rail_ledger,
        ),
        patch(
            "custom_components.journey_guardian.AutomaticRailMonitor",
            return_value=automatic_rail_monitor,
        ),
        patch(
            "custom_components.journey_guardian.StationAccessMonitor",
            return_value=station_access_monitor,
        ),
        patch(
            "custom_components.journey_guardian.TransportAPIClient",
            return_value=transportapi_client,
        ) as client_class,
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            new=AsyncMock(),
        ),
    ):
        assert await async_setup_entry(hass, entry)

    assert isinstance(entry.runtime_data.provider_broker, ProviderRequestBroker)
    assert entry.runtime_data.provider_broker._budget is budget
    client_class.assert_called_once_with(
        ANY,
        entry.runtime_data.provider_broker,
        app_id="",
        app_key="",
    )
    budget.async_load.assert_awaited_once_with()
    budget.async_reserve_call.assert_not_awaited()
    coordinator.async_config_entry_first_refresh.assert_awaited_once_with()
    scheduler.start.assert_called_once_with()
    automatic_rail_ledger.async_load.assert_awaited_once_with()
    automatic_rail_monitor.start.assert_called_once_with()
    station_access_monitor.start.assert_called_once_with()


async def test_review_action_registered_without_entry(hass) -> None:
    """The integration action exists independently of config-entry reloads."""
    assert await async_setup_component(hass, DOMAIN, {})

    assert hass.services.has_service(DOMAIN, SERVICE_REVIEW_NOW)
    assert hass.services.has_service(DOMAIN, SERVICE_REVIEW_RAIL_NOW)
    assert hass.services.has_service(DOMAIN, SERVICE_SIMULATE_JOURNEY)
    assert hass.services.has_service(DOMAIN, SERVICE_CLEAR_SIMULATION)
    assert not hass.services.has_service(DOMAIN, "reset_api_budget")


async def test_simulation_action_uses_safe_defaults_and_returns_snapshot(hass) -> None:
    """The public action activates only the in-memory simulation controller."""
    assert await async_setup_component(hass, DOMAIN, {})
    runtime = Mock()
    runtime.coordinator.async_request_refresh = AsyncMock()
    runtime.coordinator.data.as_dict.return_value = {
        "simulation_active": True,
        "status": "planned",
    }
    now = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)

    with (
        patch(
            "custom_components.journey_guardian._runtime",
            return_value=runtime,
        ),
        patch(
            "custom_components.journey_guardian.dt_util.now",
            return_value=now,
        ),
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_SIMULATE_JOURNEY,
            {"scenario": "on_time"},
            blocking=True,
            return_response=True,
        )

    runtime.simulation.activate.assert_called_once_with(
        scenario="on_time",
        now=now,
        departure_in_minutes=180,
        delay_minutes=15,
        duration_minutes=60,
        accelerated=False,
    )
    runtime.coordinator.async_request_refresh.assert_awaited_once()
    assert response == {"simulation_active": True, "status": "planned"}


async def test_clear_simulation_action_restores_live_review(hass) -> None:
    """Clearing a scenario refreshes immediately from configured live inputs."""
    assert await async_setup_component(hass, DOMAIN, {})
    runtime = Mock()
    runtime.coordinator.async_request_refresh = AsyncMock()
    runtime.coordinator.data.as_dict.return_value = {
        "simulation_active": False,
        "status": "idle",
    }

    with patch(
        "custom_components.journey_guardian._runtime",
        return_value=runtime,
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_CLEAR_SIMULATION,
            {},
            blocking=True,
            return_response=True,
        )

    runtime.simulation.clear.assert_called_once_with()
    runtime.coordinator.async_request_refresh.assert_awaited_once()
    assert response == {"simulation_active": False, "status": "idle"}


async def test_live_rail_action_is_explicit_and_returns_snapshot(hass) -> None:
    """The provider path runs only when its dedicated action is invoked."""
    assert await async_setup_component(hass, DOMAIN, {})
    runtime = Mock()
    snapshot = Mock()
    snapshot.as_dict.return_value = {
        "status": "planned",
        "decision_path": "transportapi_manual",
    }
    runtime.coordinator.async_review_live_rail = AsyncMock(
        return_value=snapshot
    )

    with patch(
        "custom_components.journey_guardian._runtime",
        return_value=runtime,
    ):
        response = await hass.services.async_call(
            DOMAIN,
            SERVICE_REVIEW_RAIL_NOW,
            {},
            blocking=True,
            return_response=True,
        )

    runtime.coordinator.async_review_live_rail.assert_awaited_once_with()
    assert response["decision_path"] == "transportapi_manual"


def test_provider_credentials_can_be_updated_through_options() -> None:
    """Deferred credentials can be added without reinstalling the integration."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CALENDAR_ENTITY: ".".join(("calendar", "example_travel")),
            "transportapi_app_id": "original-id",
            "transportapi_app_key": "original-key",
        },
        options={
            "transportapi_app_id": "updated-id",
            "transportapi_app_key": "updated-key",
        },
    )

    credentials = configured_provider_credentials(entry)

    assert credentials["transportapi_app_id"] == "updated-id"
    assert credentials["transportapi_app_key"] == "updated-key"
