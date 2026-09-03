"""Tests for deterministic, quota-free journey simulation."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

from custom_components.journey_guardian.engine import JourneyGuardianEngine
from custom_components.journey_guardian.models import BudgetSnapshot
from custom_components.journey_guardian.simulation import JourneySimulation

NOW = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)
BUDGET = BudgetSnapshot(
    date="2026-09-03",
    calls_used=4,
    daily_limit=30,
    urgent_reserve=3,
)


def _activate(scenario: str, *, delay_minutes: int = 15) -> JourneySimulation:
    simulation = JourneySimulation()
    simulation.activate(
        scenario=scenario,
        now=NOW,
        departure_in_minutes=90,
        delay_minutes=delay_minutes,
        duration_minutes=60,
    )
    return simulation


def _snapshot(simulation: JourneySimulation, *, now: datetime = NOW):
    return simulation.snapshot(
        now=now,
        budget=BUDGET,
        preparation_minutes=30,
        early_warning_minutes=10,
        station_buffer_minutes=15,
        station_access_minutes=60,
    )


def test_delayed_scenario_preserves_scheduled_and_predicted_times() -> None:
    """Simulated predictions remain distinguishable from the timetable."""
    snapshot = _snapshot(_activate("delayed", delay_minutes=20))

    assert snapshot is not None
    assert snapshot.status == "delayed"
    assert snapshot.simulation_active
    assert snapshot.data_healthy
    assert snapshot.rail_observation is not None
    assert snapshot.rail_observation.scheduled_departure == NOW + timedelta(
        minutes=90
    )
    assert snapshot.rail_observation.predicted_departure == NOW + timedelta(
        minutes=110
    )
    assert snapshot.timing is not None
    assert snapshot.timing.station_arrival_at == NOW + timedelta(minutes=95)
    assert snapshot.timing.source == "simulation"
    assert snapshot.timing.classification == "simulated_predicted"


def test_cancelled_scenario_suppresses_actionable_timing() -> None:
    """A cancelled service cannot continue to advertise leave instructions."""
    snapshot = _snapshot(_activate("cancelled"))

    assert snapshot is not None
    assert snapshot.status == "cancelled"
    assert snapshot.timing is None
    assert snapshot.rail_observation is not None
    assert snapshot.rail_observation.cancelled


def test_provider_outage_is_unhealthy_but_retains_fallback_timing() -> None:
    """Provider failure is visible while conservative calendar advice remains."""
    snapshot = _snapshot(_activate("provider_unavailable"))

    assert snapshot is not None
    assert snapshot.status == "error"
    assert snapshot.error == "simulated_provider_unavailable"
    assert not snapshot.data_healthy
    assert snapshot.timing is not None
    assert snapshot.rail_observation is not None
    assert not snapshot.rail_observation.provider_available


def test_split_scenario_is_explicit_without_claiming_live_monitoring() -> None:
    """The simulator records two legs while retaining a simulated source."""
    snapshot = _snapshot(_activate("split_on_time"))

    assert snapshot is not None
    assert snapshot.status == "planned"
    assert snapshot.rail_observation is not None
    assert snapshot.rail_observation.leg_count == 2
    assert snapshot.rail_observation.classification == "simulated"


def test_completed_simulation_expires_automatically() -> None:
    """A forgotten synthetic journey cannot isolate live inputs indefinitely."""
    simulation = _activate("on_time")
    snapshot = _snapshot(simulation, now=NOW + timedelta(minutes=151))

    assert snapshot is None
    assert not simulation.active


def test_simulation_can_be_cleared_explicitly() -> None:
    """The user can restore live calendar mode before a scenario completes."""
    simulation = _activate("on_time")

    simulation.clear()
    assert not simulation.active
    assert _snapshot(simulation) is None


async def test_active_simulation_bypasses_calendar_and_provider_budget() -> None:
    """A simulation review cannot consume live-input or provider allowance."""
    hass = Mock()
    hass.services.async_call = AsyncMock()
    budget = Mock()
    budget.snapshot.return_value = BUDGET
    simulation = _activate("on_time")
    engine = JourneyGuardianEngine(
        hass,
        calendar_entity=".".join(("calendar", "example_travel")),
        budget=budget,
        simulation=simulation,
    )

    with patch(
        "custom_components.journey_guardian.engine.dt_util.now",
        return_value=NOW,
    ):
        snapshot = await engine.async_review()

    assert snapshot.simulation_active
    hass.services.async_call.assert_not_awaited()
    assert not budget.async_reserve_call.called
    assert snapshot.budget.calls_used == BUDGET.calls_used
