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
