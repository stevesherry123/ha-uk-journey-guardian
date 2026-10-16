"""An explicit travel briefing using the shared journey and provider engine."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from .const import DEFAULT_LOOKAHEAD_HOURS
from .models import JourneySnapshot
from .progress import station_label

_LOGGER = logging.getLogger(__name__)
REVIEW_COOLDOWN = timedelta(seconds=30)
LIVE_WINDOW = timedelta(hours=3)

RAIL_MESSAGES = {
    "not_configured": "Live rail is not configured.",
    "outside_window": "Live departure checking starts three hours before departure.",
    "underway": "Scheduled departure has passed; boarding is unconfirmed.",
    "station_code_unresolved": "Origin or destination station could not be resolved.",
    "station_not_found": "The origin or destination station could not be found.",
    "station_code_conflict": "Station details conflict; check the calendar and ticket.",
    "station_match_ambiguous": "The station match is ambiguous; check your ticket.",
    "rail_service_ambiguous": "Several services match; check your ticket and board.",
    "rail_schedule_mismatch": "Provider timetable does not match your booked train.",
    "rail_service_not_found": "Booked train is absent from the board; check manually.",
    "rail_response_no_services": "The board returned no services; check manually.",
    "quota_exhausted": "The provider allowance is exhausted; check the train manually.",
    "review_timeout": "Travel review timed out; check the train manually.",
    "review_failed": "Travel review could not be completed; check manually.",
    "provider_unavailable": "Live rail could not be confirmed; check manually.",
}


def _clock(value: datetime) -> str:
    return dt_util.as_local(value).strftime("%H:%M")


def _label(value: str) -> str:
    return " ".join(station_label(value).split())


def _underway(snapshot: JourneySnapshot) -> bool:
    journey = snapshot.next_journey
    if journey is None:
        return False
    observation = snapshot.rail_observation
    departure = (
        observation.predicted_departure or observation.scheduled_departure
        if observation
        else journey.start
    )
    return departure <= snapshot.checked_at


def _error_category(snapshot: JourneySnapshot) -> str:
    error = snapshot.last_live_rail_error or ""
    return next(
        (category for category in RAIL_MESSAGES if error.endswith(f"_{category}")),
        "provider_unavailable",
    )


def render_travel_review(
    snapshot: JourneySnapshot, rail_check: str, *, calendar_refresh_failed: bool = False
) -> tuple[str, str]:
    """Return full local report and a bounded phone/watch message."""
    warning = (
        "Calendar source refresh failed; saved calendar data may be outdated. "
        if calendar_refresh_failed
        else ""
    )
    journey = snapshot.next_journey
    if snapshot.error == "calendar_unavailable":
        message = "Travel review: calendar unavailable. Your journey cannot be checked."
        return message, message
    if journey is None:
        if rail_check in {"review_timeout", "review_failed"}:
            message = f"Travel review: {RAIL_MESSAGES[rail_check]}"
            return message, message
        message = (
            f"{warning}Travel review: no timed rail journey found in the next "
            f"{DEFAULT_LOOKAHEAD_HOURS} hours."
        )
        return message, message

    observation = snapshot.rail_observation
    rail = RAIL_MESSAGES.get(rail_check, "Live rail has not been confirmed.")
    rail_brief = rail
    if observation is not None:
        if observation.cancelled:
            reported = "Cancelled. Choose another service."
        elif observation.delay_minutes > 0:
            reported = f"Delayed by {observation.delay_minutes} minutes."
            if observation.predicted_departure:
                reported += f" Expected {_clock(observation.predicted_departure)}."
        else:
            reported = "On time."
        if observation.platform:
            reported += f" Platform {str(observation.platform)[:12]}."
        current = (
            rail_check in {"checked", "simulation"}
            and observation.provider_available
            and observation.freshness == "current"
            and not observation.retained
            and timedelta(seconds=-30)
            <= snapshot.checked_at - observation.observed_at
            <= timedelta(minutes=5)
        )
        if current:
            rail = reported
            rail_brief = reported
        else:
            rail += (
                " This is not a current confirmation."
                f" Earlier report at {_clock(observation.observed_at)}: {reported}"
            )

    origin = _label(journey.origin_name)
    destination = _label(journey.destination_confirmation)
    route = (
        f"{dt_util.as_local(journey.start).strftime('%a %d %b %H:%M')} "
        f"from {origin} to {destination}."
    )
    timing = snapshot.timing
    access = ""
    if (
        timing is not None
        and not _underway(snapshot)
        and snapshot.status != "cancelled"
    ):
        mode = {
            "driving": "Drive",
            "walking": "Walk",
            "bicycling": "Cycle",
            "transit": "Public transport",
        }.get(timing.station_access_mode, "Station access")
        fallback = timing.station_access_source == "configured_fallback"
        provenance = "configured fallback" if fallback else "provider route estimate"
        if not fallback and timing.station_access_classification.startswith("cached"):
            provenance = "cached route estimate"
        access = (
            f"{mode}: allow {timing.station_access_minutes} minutes ({provenance}). "
            f"Leave by {_clock(timing.leave_home_at)}; "
            f"arrive at the station by {_clock(timing.station_arrival_at)}."
        )
        if timing.leave_home_at <= snapshot.checked_at:
            access += (
                " The planned leave time has passed; leave now if not already there."
            )
    elif _underway(snapshot):
        access = "The calendar journey window is underway. Boarding is not confirmed."

    prefix = (
        "Simulation travel review" if snapshot.simulation_active else "Travel review"
    )
    message = f"{warning}{prefix}: {route}\n{rail}"
    if access:
        message += f"\n{access}"
    # Put failures/cancellation first so a small watch screen cannot hide them.
    summary = (
        f"{warning}{prefix}: {rail_brief} {_clock(journey.start)} from {origin[:40]}."
    )
    if (
        timing is not None
        and not _underway(snapshot)
        and snapshot.status != "cancelled"
    ):
        fallback_label = (
            " fallback" if timing.station_access_source == "configured_fallback" else ""
        )
        summary += (
            f" Access {timing.station_access_minutes} min"
            f"{fallback_label};"
            f" leave {_clock(timing.leave_home_at)}."
        )
    if len(summary) > 255:
        summary = summary[:234].rsplit(" ", 1)[0] + ". Full review in HA."
    return message, summary


class ManualTravelReview:
    """Serialize explicit reviews and briefly reuse a completed response."""

    def __init__(self, coordinator, notifications) -> None:
        self._coordinator = coordinator
        self._notifications = notifications
        self._lock = asyncio.Lock()
        self._completed_at: datetime | None = None
        self._snapshot: JourneySnapshot | None = None
        self._result: dict | None = None
        self._delivery: str | None = None

    async def async_run(self, *, notify: bool = True) -> dict:
        """Refresh, review and respond even when no journey/provider is available."""
        async with self._lock:
            now = dt_util.now()
            cached = bool(
                self._result is not None
                and self._completed_at is not None
                and timedelta(0) <= now - self._completed_at < REVIEW_COOLDOWN
                and self._snapshot == self._coordinator.data
            )
            if not cached:
                rail_check = "provider_unavailable"
                try:
                    async with asyncio.timeout(60):
                        snapshot = (
                            await self._coordinator.async_refresh_calendar_and_review(
                                force_station_access=True
                            )
                        )
                        if snapshot.simulation_active:
                            rail_check = "simulation"
                        elif snapshot.next_journey is None:
                            rail_check = "no_journey"
                        elif _underway(snapshot):
                            rail_check = "underway"
                        elif (
                            snapshot.next_journey.start - snapshot.checked_at
                            > LIVE_WINDOW
                        ):
                            rail_check = "outside_window"
                        elif not self._coordinator.engine.live_rail_configured:
                            rail_check = "not_configured"
                        else:
                            snapshot = await self._coordinator.async_review_live_rail(
                                decision_path="travel_review_manual", snapshot=snapshot
                            )
                            rail_check = (
                                _error_category(snapshot)
                                if snapshot.last_live_rail_error
                                else "checked"
                            )
                except TimeoutError:
                    snapshot = self._coordinator.data
                    rail_check = "review_timeout"
                except (
                    Exception
                ) as err:  # Never expose provider/service exception text.
                    _LOGGER.warning("Travel review failed with %s", type(err).__name__)
                    snapshot = self._coordinator.data
                    rail_check = "review_failed"
                message, summary = render_travel_review(
                    snapshot,
                    rail_check,
                    calendar_refresh_failed=bool(
                        self._coordinator.last_calendar_source_refresh_error
                    ),
                )
                self._snapshot = snapshot
                self._completed_at = dt_util.now()
                self._delivery = None
                self._result = {
                    "checked_at": self._completed_at.isoformat(),
                    "status": snapshot.status,
                    "rail_check": rail_check,
                    "message": message,
                    "summary": summary,
                    "simulation_active": snapshot.simulation_active,
                }
            if notify and self._delivery is None:
                self._delivery = await self._notifications.async_manual_review(
                    self._result["message"],
                    self._result["summary"],
                    simulation=self._result["simulation_active"],
                )
            return {
                **self._result,
                "cached": cached,
                "delivery": self._delivery if notify else "not_requested",
            }
