"""Isolated Home Assistant rehearsals with real runtime wiring and fake I/O."""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components import persistent_notification
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.journey_guardian.const import DOMAIN
from custom_components.journey_guardian.google_routes import ROUTES_URL
from custom_components.journey_guardian.railinfo import BASE_URL

DAY = datetime(2026, 10, 20, tzinfo=ZoneInfo("Europe/London"))


def entity(domain, name):
    return ".".join((domain, "rehearsal_" + name))


CALENDAR = entity("calendar", "commute")
PERSON = entity("person", "traveller")
PHONE = entity("device_tracker", "phone")
AWAKE = entity("input_boolean", "awake")
MESSAGE = entity("input_text", "message")
ANNOUNCE = entity("script", "announce")
NAMES = ("Example Central", "Example Direct", "Sample Harbour", "Example Branch")
ZONES = tuple(entity("zone", str(i)) for i in range(4))


class EarlyTerminationAcceptanceGap(AssertionError):
    """Only this specific missing capability may be an expected failure."""


def clock(value, days=0):
    hour, minute = map(int, value.split(":"))
    return DAY.replace(hour=hour, minute=minute) + timedelta(days=days)


class Rehearsal:
    """Own one HA test entry; never connect to a user's Home Assistant."""

    def __init__(self, hass, freezer):
        self.hass, self.freezer = hass, freezer
        self.entry = None
        self.delay = 18
        self.return_delay = 7
        self.rail_status = "on_time"
        self.provider_error = None
        self.calendar_error = False
        self.delivery_error = False
        self.route_error = False
        self.awake_after = 3
        self.reload_on_pulse = None
        self.early_termination = False
        self.review_result = None
        self.pulses = []
        self.deliveries = []
        self.requests = []
        self.trace = []
        self.notifications = []
        self.calendar_refreshes = []
        self.events = [
            {
                "start": clock("09:00").isoformat(),
                "end": clock("10:00").isoformat(),
                "summary": "Example Rail - Example Central to Sample Harbour",
                "location": "Example Central [EXC]",
            }
        ]
        self.session = Mock(
            get=AsyncMock(side_effect=self.http_get),
            post=Mock(side_effect=self.route_post),
        )

    @property
    def runtime(self):
        return self.entry.runtime_data

    async def calendar(self, _call):
        if self.calendar_error:
            raise HomeAssistantError("Synthetic calendar outage")
        return {CALENDAR: {"events": self.events}}

    async def announce(self, call):
        if self.delivery_error:
            raise HomeAssistantError("Synthetic delivery failure")
        message = call.data.get("message") or self.hass.states.get(MESSAGE).state
        self.deliveries.append({"at": dt_util.now().isoformat(), "message": message})

    async def refresh_calendar(self, call):
        assert call.data["entity_id"] == CALENDAR
        self.calendar_refreshes.append(dt_util.now().isoformat())

    async def http_get(self, url, *, params, **_kwargs):
        parsed = urlparse(url)
        assert f"{parsed.scheme}://{parsed.netloc}" == BASE_URL
        self.requests.append(
            {
                "at": dt_util.now().isoformat(),
                "path": parsed.path,
                "params": dict(params),
            }
        )
        if self.provider_error == "timeout":
            raise TimeoutError("Synthetic provider timeout")
        response = Mock(status=429 if self.provider_error == "429" else 200)
        response.raise_for_status = Mock()
        if parsed.path == "/stations":
            codes = {NAMES[0]: "EXC", NAMES[2]: "SMP"}
            payload = [{"crs": codes[params["q"]], "description": params["q"]}]
        elif parsed.path == "/journeys":
            returning = params["from"] == "SMP"
            payload = {
                "date": DAY.date().isoformat(),
                "journeys": [
                    {
                        "changes": 0,
                        "legs": [
                            {
                                "from_crs": params["from"],
                                "to_crs": params["to"],
                                "to_name": NAMES[0] if returning else NAMES[2],
                                "dep": params["time"],
                                "headcode": "1B24" if returning else "1A23",
                                "atoc_code": "EX",
                                "dep_platform": "2",
                                "status": self.rail_status,
                            }
                        ],
                    }
                ],
            }
            if self.early_termination:
                leg = payload["journeys"][0]["legs"][0]
                leg.update(
                    to_crs="NTH",
                    to_name="Example Interchange",
                    status="terminated early",
                )
        elif parsed.path in {"/boards/SMP", "/boards/EXC"}:
            returning = parsed.path.endswith("EXC")
            scheduled = clock("18:00" if returning else "10:00")
            actual = scheduled + timedelta(
                minutes=self.return_delay if returning else self.delay
            )
            payload = {"crs": "EXC" if returning else "SMP", "movements": []}
            if dt_util.now() >= actual:
                payload["movements"].append(
                    {
                        "train_id": "701B24EX20" if returning else "701A23EX20",
                        "event_type": "ARRIVAL",
                        "gbtt_ts": scheduled.isoformat(),
                        "actual_ts": actual.isoformat(),
                    }
                )
        else:
            raise AssertionError(f"Unexpected fixture request: {parsed.path}")
        response.json = AsyncMock(return_value=payload)
        return response

    def route_post(self, url, *, json, **_kwargs):
        assert url == ROUTES_URL
        self.requests.append(
            {
                "at": dt_util.now().isoformat(),
                "path": "/directions/v2:computeRoutes",
                "params": {
                    "travelMode": json["travelMode"],
                    "destination": json["destination"]["address"],
                },
            }
        )
        response = AsyncMock()
        response.status = 503 if self.route_error else 200
        response.json.return_value = {
            "routes": [{"duration": "360s", "distanceMeters": 1000}]
        }
        response.__aenter__.return_value = response
        return response

    async def wake_sleep(self, seconds):
        assert seconds == 6
        self.pulses.append(seconds)
        self.freezer.tick(timedelta(seconds=seconds))
        if self.reload_on_pulse == len(self.pulses):
            self.reload_on_pulse = None
            self.hass.async_create_task(self.reload())
            # The real unload callback must cancel this old alarm's sleeper.
            await asyncio.Event().wait()
        if len(self.pulses) >= self.awake_after:
            self.hass.states.async_set(AWAKE, "on")
        await asyncio.sleep(0)

    async def load(self, *, home=True, preparation=2, start="08:44", routes=False):
        self.freezer.move_to(clock(start))
        await self.hass.config.async_set_time_zone("Europe/London")
        assert await async_setup_component(self.hass, "persistent_notification", {})
        assert await async_setup_component(
            self.hass,
            "input_text",
            {
                "input_text": {"rehearsal_message": {"max": 255}},
            },
        )
        self.hass.states.async_set(CALENDAR, "off")
        self.hass.states.async_set(
            PERSON,
            "home" if home else "not_home",
            {"source": PHONE, "latitude": 51, "longitude": 0},
        )
        self.hass.states.async_set(AWAKE, "on")
        self.hass.states.async_set("zone.home", "1", {"friendly_name": "Home"})
        for index, name in enumerate(NAMES):
            self.hass.states.async_set(
                ZONES[index],
                "0",
                {
                    "friendly_name": f"zzz {name}",
                    "latitude": 51 + index * 0.02,
                    "longitude": 0,
                    "radius": 250,
                },
            )
        self.hass.services.async_register(
            "calendar",
            "get_events",
            self.calendar,
            supports_response=SupportsResponse.ONLY,
        )
        self.hass.services.async_register("script", "rehearsal_announce", self.announce)
        self.hass.services.async_register(
            "homeassistant", "update_entity", self.refresh_calendar
        )
        self.entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "calendar_entity": CALENDAR,
                "person_entity": PERSON,
                "home_zone": "zone.home",
                "calendar_refresh_interval_minutes": 0,
                "preparation_buffer_minutes": preparation,
                "early_warning_minutes": 1,
                "station_buffer_minutes": 2,
                "station_access_fallback_minutes": 6,
                "station_access_minimum_minutes": 0,
                "station_access_mode": "driving",
                "live_rail_provider": "railinfo",
                "google_routes_api_key": "fixture-only-key" if routes else "",
                "automatic_live_rail_enabled": True,
                "live_notifications_enabled": True,
                "home_wake_enabled": True,
                "home_wake_awake_entity": AWAKE,
                "home_wake_repeat_seconds": 6,
                "home_wake_max_minutes": 15,
                "announcement_text_entity": MESSAGE,
                "announcement_script_entity": ANNOUNCE,
                "progress_zones": "\n".join(ZONES[:3]),
                "progress_alternatives": f"{ZONES[0]} > {ZONES[3]} > {ZONES[2]}",
            },
        )
        self.entry.add_to_hass(self.hass)
        assert await self.hass.config_entries.async_setup(self.entry.entry_id)
        await self.hass.async_block_till_done()
        assert not self.runtime.simulation.active
        assert not self.runtime.coordinator.data.simulation_active
        self.mark("Integration loaded with real entities and services")

    async def advance(self, value, *, days=0):
        point = clock(value, days)
        self.freezer.move_to(point)
        async_fire_time_changed(self.hass, point)
        await self.hass.async_block_till_done()
        self.mark("Timers advanced")

    async def reload(self):
        old = self.runtime
        assert await self.hass.config_entries.async_reload(self.entry.entry_id)
        await self.hass.async_block_till_done()
        assert self.runtime is not old
        self.mark("Config entry unloaded and reconstructed using persisted storage")

    async def review(self):
        result = await self.hass.services.async_call(
            DOMAIN,
            "review_now",
            {},
            blocking=True,
            return_response=True,
        )
        await self.hass.async_block_till_done()
        self.mark("Explicit calendar review completed")
        return result

    def gps(self, index, *, accuracy=10):
        self.hass.states.async_set(
            PHONE,
            "not_home",
            {
                "source_type": "gps",
                "latitude": 51 + index * 0.02,
                "longitude": 0,
                "gps_accuracy": accuracy,
            },
        )
        self.hass.states.async_set(
            PERSON,
            "not_home",
            {
                "source": PHONE,
                "latitude": 51 + index * 0.02,
                "longitude": 0,
                "gps_accuracy": accuracy,
            },
        )

    def progress(self):
        registry = er.async_get(self.hass)
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{self.entry.entry_id}_station_progress"
        )
        return self.hass.states.get(entity_id)

    def mark(self, note):
        data = self.runtime.coordinator.data
        self.review_result = self.runtime.end_of_day_review._last_review
        progress = self.progress()
        self.trace.append(
            {
                "at": dt_util.now().isoformat(),
                "note": note,
                "status": data.status,
                "phase": data.operational_phase,
                "error": data.error,
                "rail_error": data.last_live_rail_error,
                "delivery_count": len(self.deliveries),
                "request_count": len(self.requests),
                "progress": progress.state if progress else None,
                "progress_attributes": dict(progress.attributes) if progress else {},
            }
        )


@pytest.fixture
async def rehearsal(hass, freezer, request):
    harness = Rehearsal(hass, freezer)
    proxy = Mock(wraps=asyncio)
    proxy.sleep = harness.wake_sleep
    remove = persistent_notification.async_register_callback(
        hass,
        lambda _kind, updates: harness.notifications.extend(
            dict(value) for value in updates.values()
        ),
    )
    with (
        patch(
            "custom_components.journey_guardian.async_get_clientsession",
            return_value=harness.session,
        ),
        patch("custom_components.journey_guardian.notification.asyncio", proxy),
    ):
        try:
            yield harness
        finally:
            if harness.entry:
                harness.mark("Rehearsal finished")
                if harness.entry.state.value == "loaded":
                    assert await hass.config_entries.async_unload(
                        harness.entry.entry_id
                    )
                    await hass.async_block_till_done()
            remove()
            if folder := os.environ.get("JG_REHEARSAL_OUTPUT"):
                output = Path(folder)
                output.mkdir(parents=True, exist_ok=True)
                name = re.sub(r"[^a-zA-Z0-9_.-]", "_", request.node.name)
                (output / f"{name}.json").write_text(
                    json.dumps(
                        {
                            "trace": harness.trace,
                            "requests": harness.requests,
                            "deliveries": harness.deliveries,
                            "wake_sleeps": harness.pulses,
                            "notifications": harness.notifications,
                            "nightly_review": harness.review_result,
                            "calendar_refreshes": harness.calendar_refreshes,
                        },
                        indent=2,
                        default=str,
                    )
                    + "\n"
                )


async def test_flights_never_reach_routing_rail_alarms_or_arrival_collection(rehearsal):
    h = rehearsal
    h.events = [{
        "start": clock("09:00").isoformat(),
        "end": clock("10:00").isoformat(),
        "summary": "ZZ1234 AAA to BBB",
        "description": "[Flight] AAA to BBB",
        "location": "Example Airport (AAA)",
    }]
    await h.load(routes=True)
    h.hass.states.async_set(AWAKE, "off")
    for point in ("08:50", "08:59", "09:00", "09:15", "10:05"):
        await h.advance(point)
        await h.review()
    await h.reload()
    await h.runtime.coordinator.async_test_station_access()
    with pytest.raises(ValueError, match="rail_journey_unavailable"):
        await h.runtime.coordinator.engine.async_review_live_rail()
    report = await h.hass.services.async_call(
        DOMAIN, "travel_review_now", {"notify": False},
        blocking=True, return_response=True,
    )
    await h.hass.async_block_till_done()
    snapshot = h.runtime.coordinator.data
    assert snapshot.status == "idle"
    assert snapshot.next_journey is None
    assert snapshot.timing is None
    assert snapshot.booked_legs == ()
    retained = h.runtime.coordinator.travel_plan.attributes(dt_util.now())
    assert retained["retained_booked_leg_count"] == 0
    assert h.runtime.arrival_collector.diagnostics()["pending_count"] == 0
    assert not h.requests
    assert not h.deliveries
    assert not h.pulses
    assert not h.runtime.check_history.records()
    assert "ZZ1234" not in str(report)


@pytest.mark.parametrize("delay", [0, 7, 18])
async def test_full_commute_to_nightly_review(rehearsal, delay):
    h = rehearsal
    h.delay = delay
    await h.load()
    assert h.runtime.coordinator.data.timing.prepare_at == clock("08:49")
    assert h.runtime.coordinator.data.timing.leave_home_at == clock("08:52")
    await h.advance("08:45")
    assert h.runtime.coordinator.data.rail_observation is not None
    assert h.runtime.coordinator.data.rail_observation.source == "railinfo"
    h.hass.states.async_set(AWAKE, "off")
    await h.advance("08:49")
    wake = [item for item in h.deliveries if "wake" in item["message"].casefold()]
    assert len(wake) == 3
    times = [datetime.fromisoformat(item["at"]) for item in wake]
    assert all(
        (right - left).total_seconds() == 6
        for left, right in zip(times, times[1:], strict=False)
    )
    assert h.runtime.notification_scheduler.diagnostics()["last_stop_reason"] == "awake"
    await h.advance("08:52")
    assert h.runtime.coordinator.data.operational_phase == "leave_now"
    count = len(h.deliveries)
    await h.reload()
    assert len(h.deliveries) == count
    h.gps(0)
    await h.advance("09:10")
    h.gps(3)
    await h.review()
    assert h.progress().attributes["candidate_route_count"] == 1
    await h.advance("10:05")
    assert h.progress().attributes["monitoring_extended"] is True
    await h.advance("10:20")
    records = h.runtime.check_history.records()
    arrivals = [
        record for record in records if record["completion_status"] == "completed"
    ]
    assert len(arrivals) == 1
    assert arrivals[0]["arrival_delay_minutes"] == delay
    requests_before = len(h.requests)
    await h.advance("04:00", days=1)
    report = h.runtime.end_of_day_review._last_review
    assert report["review_date"] == DAY.date().isoformat()
    assert report["journey_count"] == 1
    assert report["unresolved_count"] == 0
    assert report["departure_delay_observed_count"] == 0
    assert report["potential_claim_count"] == (1 if delay >= 15 else 0)
    assert report["notification_sent"] is (delay >= 15)
    assert len(h.requests) == requests_before
    await h.reload()
    assert h.runtime.end_of_day_review._last_review == report
    assert len(h.requests) == requests_before


async def test_active_calendar_outage_recovers_intent_after_runtime_reload(rehearsal):
    h = rehearsal
    await h.load()
    await h.advance("08:45")
    await h.advance("09:10")
    h.calendar_error = True
    await h.review()
    requests, messages = len(h.requests), len(h.deliveries)
    await h.reload()
    data = h.runtime.coordinator.data
    assert data.next_journey is not None
    assert data.next_journey.origin_name == NAMES[0]
    assert data.next_journey.decision_path == "calendar_recovered"
    assert data.status == "active"
    assert data.error == "calendar_unavailable"
    assert not data.data_healthy
    assert data.rail_observation.retained
    assert data.rail_observation.freshness == "historical"
    assert len(h.requests) == requests
    assert len(h.deliveries) == messages
    await h.advance("09:15")
    assert len(h.requests) == requests
    h.calendar_error = False
    await h.advance("09:16")
    await h.review()
    assert h.runtime.coordinator.data.data_healthy
    assert h.runtime.coordinator.data.next_journey.summary == h.events[0]["summary"]
    # The newly healthy calendar may now run its one due +15-minute checkpoint.
    assert h.runtime.coordinator.data.rail_observation.source == "railinfo"
    h.events = []
    await h.advance("09:17")
    await h.review()
    assert h.runtime.coordinator.data.next_journey is None
    h.calendar_error = True
    await h.reload()
    assert h.runtime.coordinator.data.next_journey is None


async def test_four_bookings_visible_without_new_provider_calls_or_plan_changes(
    rehearsal,
):
    h = rehearsal
    h.events[0]["end"] = clock("09:30").isoformat()
    for start, end, origin, destination in (
        ("09:40", "10:30", NAMES[2], NAMES[3]),
        ("17:00", "17:40", NAMES[3], NAMES[2]),
        ("18:00", "19:00", NAMES[2], NAMES[0]),
    ):
        h.events.append({
            "start": clock(start).isoformat(), "end": clock(end).isoformat(),
            "summary": f"Example Rail - {origin} to {destination}",
            "location": origin,
        })
    await h.load()
    assert len(h.requests) == 0
    registry = er.async_get(h.hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{h.entry.entry_id}_status"
    )
    attributes = h.hass.states.get(entity_id).attributes
    assert attributes["upcoming_booked_leg_count"] == 4
    assert not attributes["booking_overview_truncated"]
    assert [
        item["relationship_to_previous"]
        for item in attributes["upcoming_booked_legs"]
    ] == ["first_booking", "possible_connection", "separate_booking",
          "possible_connection"]
    leave = h.runtime.coordinator.data.timing.leave_home_at
    await h.advance("08:45")
    assert h.runtime.coordinator.data.next_journey.start == clock("09:00")
    assert h.runtime.coordinator.data.timing.leave_home_at == leave
    requests = len(h.requests)
    await h.reload()
    assert len(h.requests) == requests
    assert h.runtime.coordinator.data.booked_leg_count == 4
    # Diagnostics must not acquire the new private calendar overview.
    from custom_components.journey_guardian.diagnostics import (
        async_get_config_entry_diagnostics,
    )
    diagnostics = await async_get_config_entry_diagnostics(h.hass, h.entry)
    assert "upcoming_booked_legs" not in str(diagnostics)
    assert NAMES[0] not in str(diagnostics)
    assert "retained_booked_legs" not in str(diagnostics)
    ids = [item["booking_id"] for item in attributes["retained_booked_legs"]]
    for point, remaining in (("09:31", 3), ("10:31", 2),
                             ("17:41", 1), ("19:01", 0)):
        await h.advance(point)
        await h.review()
        await h.reload()
        attributes = h.hass.states.get(entity_id).attributes
        assert attributes["upcoming_booked_leg_count"] == remaining
        assert [item["booking_id"] for item in
                attributes["retained_booked_legs"]] == ids
        assert attributes["retained_booked_leg_count"] == 4
        assert all(item["outcome"] == "unconfirmed" for item in
                   attributes["retained_booked_legs"])
    assert all(item["booked_window"] == "booked_window_elapsed" for item in
               attributes["retained_booked_legs"])


async def test_home_wake_ten_pulses_per_minute_and_mid_alarm_reload(rehearsal):
    h = rehearsal
    h.awake_after = 10
    h.reload_on_pulse = 2
    await h.load()
    h.hass.states.async_set(AWAKE, "off")
    await h.advance("08:49")
    wake = [item for item in h.deliveries if item["message"].startswith("Wake up now.")]
    assert len(wake) == 10
    times = [datetime.fromisoformat(item["at"]) for item in wake]
    assert [
        (right - left).total_seconds()
        for left, right in zip(times, times[1:], strict=False)
    ] == [6] * 9
    assert sum("reconstructed" in point["note"] for point in h.trace) == 1
    assert h.runtime.notification_scheduler._home_wake_task is None
    count = len(h.deliveries)
    await h.review()
    assert not any(
        "wake" in item["message"].casefold() for item in h.deliveries[count:]
    )


async def test_away_uses_three_bounded_reminders_not_home_buzzing(rehearsal):
    h = rehearsal
    await h.load(home=False, preparation=20, start="08:20")
    for point in ("08:31", "08:36", "08:41"):
        await h.advance(point)
    reminders = [
        item["message"]
        for item in h.deliveries
        if item["message"].startswith("Wake-up reminder")
    ]
    assert len(reminders) == 3
    assert [f"{number}/3" in reminders[number - 1] for number in (1, 2, 3)] == [
        True
    ] * 3
    assert not h.pulses
    assert not any(item["message"].startswith("Wake up now.") for item in h.deliveries)
    await h.review()
    await h.reload()
    assert (
        sum(item["message"].startswith("Wake-up reminder") for item in h.deliveries)
        == 3
    )


async def test_calendar_outage_and_diversion_recover_after_booked_end(rehearsal):
    h = rehearsal
    await h.load(home=False)
    await h.advance("09:10")
    h.gps(3)
    await h.review()
    assert h.progress().attributes["candidate_route_count"] == 1
    h.calendar_error = True
    await h.advance("09:11")
    await h.review()
    assert h.runtime.coordinator.data.error == "calendar_unavailable"
    assert h.progress().attributes["monitoring_extended"] is True
    h.gps(2, accuracy=150)
    await h.hass.async_block_till_done()
    assert h.progress().state == "location_inaccurate"
    assert h.progress().attributes["last_observed_station"] == NAMES[3]
    h.hass.states.async_set(PHONE, "unavailable")
    h.hass.states.async_set(PERSON, "unknown", {"source": PHONE})
    await h.hass.async_block_till_done()
    assert h.progress().state == "location_unavailable"
    await h.advance("09:12")
    h.gps(3)
    await h.hass.async_block_till_done()
    assert h.progress().state == "near_station"
    await h.advance("10:06")
    await h.reload()
    assert h.progress().attributes["monitoring_extended"] is True
    assert h.progress().attributes["candidate_route_count"] == 1
    assert h.progress().state == "location_stale"
    h.calendar_error = False
    await h.advance("10:07")
    await h.review()
    assert h.runtime.coordinator.data.error is None
    h.gps(2)
    await h.hass.async_block_till_done()
    assert h.progress().attributes["current_station"] == NAMES[2]
    assert h.progress().attributes["rail_arrival_confirmed"] is False
    await h.advance("10:08")
    assert h.progress().state == "idle"


@pytest.mark.parametrize("failure", ["timeout", "429"])
async def test_provider_outage_retains_plan_and_recovers_without_burst(
    rehearsal, failure
):
    h = rehearsal
    h.provider_error = failure
    await h.load(home=False)
    await h.advance("08:45")
    data = h.runtime.coordinator.data
    assert data.last_live_rail_error
    assert "Synthetic" not in data.last_live_rail_error
    assert data.timing.leave_home_at == clock("08:52")
    count = len(h.requests)
    await h.reload()
    assert len(h.requests) == count
    h.provider_error = None
    await h.advance("08:50")
    assert h.runtime.coordinator.data.rail_observation is not None
    assert h.runtime.coordinator.data.last_live_rail_error is None
    assert len(h.requests) <= count + 2
    assert h.runtime.budget.snapshot().calls_used == 0


async def test_cancelled_train_reaches_nightly_possible_claim(rehearsal):
    h = rehearsal
    h.rail_status = "cancelled"
    await h.load()
    await h.advance("08:45")
    assert h.runtime.coordinator.data.status == "cancelled"
    assert any("cancelled" in item["message"] for item in h.deliveries)
    count = len(h.requests)
    await h.reload()
    await h.advance("04:00", days=1)
    report = h.runtime.end_of_day_review._last_review
    assert report["journey_count"] == 1
    assert report["cancelled_count"] == 1
    assert report["potential_claim_count"] == 1
    assert not any(item["path"].startswith("/boards/") for item in h.requests)
    assert len(h.requests) == count


async def test_announcement_failure_uses_local_fallback_and_manual_button(rehearsal):
    h = rehearsal
    h.delivery_error = True
    await h.load()
    await h.advance("08:45")
    assert not h.deliveries
    assert any("Platform 2" in item["message"] for item in h.notifications)
    h.delivery_error = False
    registry = er.async_get(h.hass)
    button = registry.async_get_entity_id(
        "button", DOMAIN, f"{h.entry.entry_id}_travel_review_now"
    )
    assert button is not None
    for _tap in range(2):
        await h.hass.services.async_call(
            "button", "press", {"entity_id": button}, blocking=True
        )
        await h.hass.async_block_till_done()
    assert len(h.deliveries) == 1
    assert len(h.deliveries[0]["message"]) <= 255
    assert any(
        item["notification_id"] == "journey_guardian_travel_review"
        for item in h.notifications
    )


@pytest.mark.xfail(
    strict=True,
    raises=EarlyTerminationAcceptanceGap,
    reason="Early termination lacks cancellation classification and recovery search",
)
async def test_early_termination_acceptance_gap(rehearsal):
    h = rehearsal
    h.delay = 180
    await h.load(home=False)
    await h.advance("08:45")
    h.early_termination = True
    await h.advance("09:15")
    status = h.runtime.coordinator.data.status
    assert (
        h.runtime.coordinator.data.last_live_rail_error
        == "railinfo_rail_response_no_services"
    )
    await h.advance("10:05")
    await h.advance("10:20")
    await h.advance("11:00")
    await h.advance("04:00", days=1)
    report = h.runtime.end_of_day_review._last_review
    h.mark(
        "ACCEPTANCE GAP: shortened service is not a cancellation; no recovery search"
    )
    assert report["unresolved_count"] == 1
    assert report["journeys"][0]["actual_arrival"] is None
    if status != "cancelled":
        raise EarlyTerminationAcceptanceGap(
            "Shortened service stays active/unmatched, without cancellation/recovery"
        )


@pytest.mark.parametrize(
    "preparation,start,reason,pulses",
    [
        (2, "08:49", "leave_home", 30),
        (20, "08:31", "safety_limit", 150),
    ],
)
async def test_home_alarm_stops_without_awake_evidence(
    rehearsal, preparation, start, reason, pulses
):
    h = rehearsal
    h.awake_after = 1000
    await h.load(preparation=preparation, start="08:20")
    h.hass.states.async_set(AWAKE, "off")
    await h.advance(start)
    assert len(h.pulses) == pulses
    assert h.runtime.notification_scheduler.diagnostics()["last_stop_reason"] == reason
    assert h.runtime.notification_scheduler._home_wake_task is None
    count = len(h.deliveries)
    await h.review()
    assert not any(
        "wake" in item["message"].casefold() for item in h.deliveries[count:]
    )
    await h.advance("08:52")
    assert h.runtime.coordinator.data.operational_phase == "leave_now"
    assert (
        sum(item["message"].startswith("Time to drive") for item in h.deliveries) == 1
    )


async def test_outbound_and_return_stay_separate_in_nightly_review(rehearsal):
    h = rehearsal
    h.events.append(
        {
            "start": clock("17:00").isoformat(),
            "end": clock("18:00").isoformat(),
            "summary": "Example Rail - Sample Harbour to Example Central",
            "location": "Sample Harbour [SMP]",
        }
    )
    await h.load(home=False)
    await h.advance("08:45")
    await h.advance("10:05")
    await h.advance("10:20")
    assert h.runtime.coordinator.data.next_journey.origin_name == NAMES[2]
    await h.advance("16:45")
    assert h.runtime.coordinator.data.rail_observation.destination_code == "EXC"
    await h.advance("18:05")
    await h.advance("18:20")
    count = len(h.requests)
    await h.advance("04:00", days=1)
    report = h.runtime.end_of_day_review._last_review
    assert report["journey_count"] == 2
    assert report["delayed_count"] == 2
    assert report["potential_claim_count"] == 1
    assert report["unresolved_count"] == 0
    assert sorted(item["arrival_delay_minutes"] for item in report["journeys"]) == [
        7,
        18,
    ]
    assert len(h.requests) == count


async def test_station_route_button_uses_live_estimate_and_safe_outage_fallback(
    rehearsal,
):
    h = rehearsal
    await h.load(routes=True)
    data = h.runtime.coordinator.data
    assert data.timing.source == "google_routes"
    assert data.timing.station_access_minutes == 6
    assert data.timing.leave_home_at == clock("08:52")
    button = er.async_get(h.hass).async_get_entity_id(
        "button", DOMAIN, f"{h.entry.entry_id}_test_station_access"
    )
    assert button
    h.route_error = True
    await h.hass.services.async_call(
        "button", "press", {"entity_id": button}, blocking=True
    )
    await h.hass.async_block_till_done()
    data = h.runtime.coordinator.data
    assert data.timing.source == "configured_fallback"
    assert data.timing.station_access_error == "google_routes_provider_unavailable"
    assert data.timing.leave_home_at == clock("08:52")
    h.mark("Routing outage retains conservative fallback")
    h.route_error = False
    await h.hass.services.async_call(
        "button", "press", {"entity_id": button}, blocking=True
    )
    await h.hass.async_block_till_done()
    assert h.runtime.coordinator.data.timing.source == "google_routes"
    assert (
        sum(item["path"] == "/directions/v2:computeRoutes" for item in h.requests) == 3
    )
    h.mark("Forced station-route button recovers live estimate")


async def test_unavailable_calendar_then_recovery_does_not_look_like_empty_day(
    rehearsal,
):
    h = rehearsal
    await h.load()
    original = h.runtime.coordinator.data.next_journey
    provider_calls = len(h.requests)
    h.hass.states.async_set(CALENDAR, "unavailable")
    await h.review()
    data = h.runtime.coordinator.data
    assert data.error == "calendar_unavailable"
    assert not data.data_healthy
    assert data.status != "idle"
    await h.reload()
    assert h.runtime.coordinator.data.error == "calendar_unavailable"
    assert len(h.requests) == provider_calls
    h.hass.states.async_set(CALENDAR, "off")
    await h.review()
    data = h.runtime.coordinator.data
    assert data.data_healthy
    assert data.status == "planned"
    assert data.next_journey == original
    assert len(h.requests) == provider_calls


async def test_existing_route_profile_uses_waze_sensor_through_runtime_reload(
    rehearsal,
):
    h = rehearsal
    await h.load()
    sensor = entity("sensor", "fixed_station_drive")
    h.hass.states.async_set(sensor, "20", {"unit_of_measurement": "min"})
    h.hass.config_entries.async_update_entry(h.entry, options={
        "station_access_profiles": f"EXC|{NAMES[0]}=waze:{sensor}\nSMP=transit",
        "station_access_minimum_minutes": 30,
    })
    await h.reload()
    timing = h.runtime.coordinator.data.timing
    assert timing.station_access_source == "waze_sensor"
    assert timing.station_access_provider_minutes == 20
    assert timing.station_access_minutes == 30
    assert timing.leave_home_at == clock("08:28")
    assert not h.requests
    await h.reload()
    assert h.runtime.coordinator.data.timing.station_access_source == "waze_sensor"
    assert not h.requests
