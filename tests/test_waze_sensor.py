"""Explicit Waze profiles must not leak onto another leg or silently use Google."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.journey_guardian.engine import JourneyGuardianEngine
from custom_components.journey_guardian.google_routes import StationAccessEstimate
from custom_components.journey_guardian.models import JourneyEvent
from custom_components.journey_guardian.station_access_profiles import (
    StationAccessProfileError,
    mode_for_journey,
    parse_station_access_profiles,
    waze_sensor_for_journey,
)
from custom_components.journey_guardian.waze_sensor import (
    WazeSensorError,
    async_waze_estimate,
)

NOW = datetime(2026, 10, 22, 3, tzinfo=UTC)
SENSOR = ".".join(("sensor", "example_station_route"))
PERSON = ".".join(("person", "example_traveller"))
PROFILE = f"EXC|Example Central=waze:{SENSOR}\nSMP=transit"


def journey():
    return JourneyEvent(
        NOW + timedelta(hours=2),
        NOW + timedelta(hours=3),
        "Example Rail - Example Central to Sample Harbour",
        "",
        "CALENDAR",
        "Example Central",
        "Sample Harbour",
        "calendar_route",
    )


def source(hass, freezer, value="20", **attrs):
    freezer.move_to(NOW)
    hass.states.async_set(SENSOR, value, {"unit_of_measurement": "min", **attrs})
    hass.states.async_set(PERSON, "home", {"latitude": 12, "longitude": 34})
    hass.states.async_set("zone.home", "1", {"friendly_name": "Home"})


def engine(hass, **kwargs):
    google = Mock(
        configured=True,
        async_route=AsyncMock(
            return_value=StationAccessEstimate(12, None, "transit", NOW)
        ),
    )
    instance = JourneyGuardianEngine(
        hass,
        calendar_entity="calendar" + ".example",
        budget=Mock(),
        person_entity=PERSON,
        station_access_mode="transit",
        station_access_profiles=PROFILE,
        google_routes_client=google,
        station_access_minimum_minutes=30,
        **kwargs,
    )
    return instance, google


def test_profiles_bind_sensor_with_alias_without_crs_in_calendar():
    profiles = parse_station_access_profiles(PROFILE)
    assert waze_sensor_for_journey(journey(), profiles) == SENSOR
    assert mode_for_journey(journey(), profiles) == "driving"
    assert (
        waze_sensor_for_journey(
            replace(journey(), origin_name="Sample Harbour [SMP]"), profiles
        )
        is None
    )
    assert (
        waze_sensor_for_journey(
            replace(journey(), origin_name="Example Central East"), profiles
        )
        is None
    )
    assert (
        waze_sensor_for_journey(replace(journey(), origin_code="SMP"), profiles) is None
    )
    assert (
        waze_sensor_for_journey(
            replace(journey(), origin_name="Example Central [EXC]", location="CRS:SMP"),
            profiles,
        )
        is None
    )


@pytest.mark.parametrize(
    "value",
    [
        "EXC=waze:light.example",
        "EXC=waze:https://example.invalid",
        "EXC|=driving",
        "EXC|Example|Other=driving",
        "EXC|Same=driving\nSMP|same=transit",
        "EXC=driving\nEXC|Example=walking",
    ],
)
def test_invalid_or_ambiguous_bindings_rejected(value):
    with pytest.raises(StationAccessProfileError):
        parse_station_access_profiles(value)


async def test_waze_uses_live_sensor_and_existing_minimum_without_google(hass, freezer):
    source(hass, freezer)
    instance, google = engine(hass)
    timing = await instance._async_calculate_timing(journey())
    assert timing.station_access_source == "waze_sensor"
    assert timing.station_access_provider_minutes == 20
    assert timing.station_access_minutes == 30
    assert timing.station_access_mode == "driving"
    assert timing.classification == "live_driving_minimum"
    google.async_route.assert_not_awaited()
    assert instance.station_access_configured
    assert SENSOR not in str(timing.as_dict())


async def test_return_leg_keeps_its_own_provider_and_mode(hass, freezer):
    source(hass, freezer)
    instance, google = engine(hass)
    returning = replace(
        journey(),
        origin_name="Sample Harbour [SMP]",
        origin_code="SMP",
        destination_confirmation="Example Central",
    )
    timing = await instance._async_calculate_timing(returning)
    assert timing.station_access_source == "google_routes"
    assert google.async_route.await_args.kwargs["mode"] == "transit"


async def test_fixed_route_does_not_switch_to_google_when_person_leaves_home(
    hass, freezer
):
    source(hass, freezer)
    hass.states.async_set(PERSON, "not_home")
    instance, google = engine(hass)
    timing = await instance._async_calculate_timing(journey())
    assert timing.station_access_source == "waze_sensor"
    assert timing.station_access_minutes == 30
    google.async_route.assert_not_awaited()


async def test_missing_sensor_keeps_explicit_safe_fallback(hass, freezer):
    source(hass, freezer)
    hass.states.async_remove(SENSOR)
    instance, google = engine(hass)
    timing = await instance._async_calculate_timing(journey())
    assert timing.station_access_error == "waze_sensor_missing"
    assert timing.station_access_minutes == 60
    google.async_route.assert_not_awaited()


@pytest.mark.parametrize(
    "value,attrs,category",
    [
        ("unknown", {}, "sensor_unavailable"),
        ("unavailable", {}, "sensor_unavailable"),
        ("20", {"restored": True}, "sensor_unavailable"),
        ("20", {"unit_of_measurement": "km"}, "sensor_invalid"),
        ("0", {}, "sensor_invalid"),
        ("-1", {}, "sensor_invalid"),
        ("nan", {}, "sensor_invalid"),
        ("inf", {}, "sensor_invalid"),
        ("241", {}, "sensor_invalid"),
        ("broken", {}, "sensor_invalid"),
    ],
)
async def test_bad_sensor_never_becomes_a_duration(
    hass, freezer, value, attrs, category
):
    source(hass, freezer, value, **attrs)
    with pytest.raises(WazeSensorError, match=f"^{category}$"):
        await async_waze_estimate(hass, SENSOR, now=NOW)


async def test_stale_sensor_rejected_but_unchanged_fresh_report_accepted(hass, freezer):
    source(hass, freezer)
    later = NOW + timedelta(minutes=16)
    freezer.move_to(later)
    with pytest.raises(WazeSensorError, match="sensor_stale"):
        await async_waze_estimate(hass, SENSOR, now=later)
    hass.states.async_set(SENSOR, "20", {"unit_of_measurement": "min"})
    assert hass.states.get(SENSOR).last_updated < later
    estimate = await async_waze_estimate(hass, SENSOR, now=later)
    assert estimate.duration_minutes == 20
    assert estimate.observed_at == later


async def test_fractional_duration_rounds_up(hass, freezer):
    source(hass, freezer, "20.2")
    assert (await async_waze_estimate(hass, SENSOR, now=NOW)).duration_minutes == 21


async def test_forced_check_refreshes_native_sensor_once(hass, freezer):
    source(hass, freezer)

    async def update(call):
        assert call.data == {"entity_id": SENSOR}
        freezer.move_to(NOW + timedelta(seconds=2))
        hass.states.async_set(SENSOR, "22", {"unit_of_measurement": "min"})

    refresh = AsyncMock(side_effect=update)
    hass.services.async_register("homeassistant", "update_entity", refresh)
    estimate = await async_waze_estimate(hass, SENSOR, now=NOW, force_refresh=True)
    refresh.assert_awaited_once()
    assert estimate.duration_minutes == 22


async def test_refresh_failure_sanitized(hass, freezer):
    source(hass, freezer)
    refresh = AsyncMock(side_effect=HomeAssistantError("private route and address"))
    hass.services.async_register("homeassistant", "update_entity", refresh)
    with pytest.raises(WazeSensorError, match="^refresh_failed$"):
        await async_waze_estimate(hass, SENSOR, now=NOW, force_refresh=True)


async def test_known_cached_crs_applies_legacy_mode_before_new_places_work(
    hass, freezer
):
    source(hass, freezer)
    instance, google = engine(hass)
    instance._station_access_profiles = parse_station_access_profiles("EXC=driving")
    client = Mock(
        async_places=AsyncMock(
            return_value=Mock(
                payload={
                    "places": [
                        {
                            "name": "Example Central",
                            "station_code": "EXC",
                            "type": "train_station",
                        }
                    ]
                }
            )
        )
    )
    await instance._async_resolve_station(
        name="Example Central", code="CALENDAR", location="", client=client
    )
    await instance._async_calculate_timing(journey())
    assert google.async_route.await_args.kwargs["mode"] == "driving"
    client.async_places.assert_awaited_once()
