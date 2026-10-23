"""Tests for privacy-minimized downloadable diagnostics."""

import json
from datetime import UTC, datetime
from unittest.mock import Mock

from custom_components.journey_guardian.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.journey_guardian.models import (
    BudgetSnapshot,
    JourneyEvent,
    JourneySnapshot,
    RailObservation,
)


async def test_diagnostics_remove_journey_and_configuration_identifiers(hass) -> None:
    """A shared diagnostic payload contains outcomes, never identifying data."""
    departure = datetime(2026, 9, 28, 19, 0, tzinfo=UTC)
    journey = JourneyEvent(
        start=departure,
        end=departure,
        summary="Private calendar title",
        location="Private home address",
        origin_code="EXC",
        origin_name="Private origin",
        destination_confirmation="Private destination",
        decision_path="calendar_route",
    )
    observation = RailObservation(
        scenario="observed",
        source="railinfo",
        classification="provider_normalized",
        observed_at=departure,
        scheduled_departure=departure,
        predicted_departure=None,
        delay_minutes=12,
        cancelled=False,
        leg_count=1,
        provider_available=True,
        service_identity="private-service-identity",
        platform="9",
        destination_code="SMP",
    )
    snapshot = JourneySnapshot(
        status="delayed",
        checked_at=departure,
        next_journey=journey,
        budget=BudgetSnapshot("2026-09-28", 1, 30, 3),
        rail_observation=observation,
        flight_preview={"legs": [{"service": "private-flight-service"}]},
    )
    runtime = Mock()
    runtime.coordinator.data = snapshot
    runtime.check_history.records.return_value = [
        {
            "checked_at": departure.isoformat(),
            "journey_date": "2026-09-28",
            "journey_fingerprint": "private-fingerprint",
            "origin_code": "EXC",
            "destination_code": "SMP",
            "service_identity": "private-service-identity",
            "scheduled_arrival": departure.isoformat(),
            "actual_arrival": departure.isoformat(),
            "outcome": "success",
            "status": "delayed",
        }
    ]
    runtime.end_of_day_review.diagnostics.return_value = {
        "journey_count": 1,
        "delayed_count": 1,
    }
    runtime.arrival_collector.diagnostics.return_value = {
        "pending_count": 1,
        "completed_count": 0,
        "pending_attempt_counts": {"1": 1},
    }
    runtime.notification_scheduler.diagnostics.return_value = {
        "enabled": True,
        "status": "waiting",
        "awake_evidence_configured": False,
        "announcement_engine_configured": True,
        "repeat_seconds": 6,
        "max_minutes": 15,
        "delivery_count": 0,
        "last_delivery": None,
        "last_stop_reason": None,
    }
    entry = Mock()
    entry.runtime_data = runtime
    entry.as_dict.return_value = {
        "entry_id": "private-entry-id",
        "unique_id": "private-unique-id",
        "data": {
            "progress_zones": "zone.private_station_a\nzone.private_station_b",
            "calendar_entity": "private-calendar-entity",
            "person_entity": "private-person-entity",
            "announcement_text_entity": "private-text-entity",
            "announcement_script_entity": "private-script-entity",
            "home_wake_awake_entity": "private-awake-entity",
            "transportapi_app_key": "private-transport-key",
            "google_routes_api_key": "private-routes-key",
            "station_access_profiles": "EXC|Private origin=waze:sensor.private_route",
            "airport_timezones": "AAA=Private/Timezone",
        },
    }

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    serialized = json.dumps(diagnostics, sort_keys=True)

    assert diagnostics["engine"]["next_journey"] == "REDACTED"
    assert diagnostics["engine"]["flight_preview"] == "REDACTED"
    assert diagnostics["engine"]["rail_observation"]["delay_minutes"] == 12
    assert diagnostics["recent_live_checks"][0]["outcome"] == "success"
    assert diagnostics["home_wake_alarm"]["status"] == "waiting"
    for private_value in (
        "private_station_a",
        "private_station_b",
        "private-entry-id",
        "private-unique-id",
        "private-calendar-entity",
        "private-person-entity",
        "private-text-entity",
        "private-script-entity",
        "private-awake-entity",
        "private-transport-key",
        "private-routes-key",
        "sensor.private_route",
        "private-service-identity",
        "private-fingerprint",
        "private-flight-service",
        "Private/Timezone",
        "Private calendar title",
        "Private home address",
        "Private origin",
        "Private destination",
        "EXC",
        "SMP",
        departure.isoformat(),
    ):
        assert private_value not in serialized
