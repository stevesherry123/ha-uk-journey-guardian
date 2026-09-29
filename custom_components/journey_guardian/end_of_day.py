"""Provider-free nightly review of saved Journey Guardian evidence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .check_history import CheckHistory

STORAGE_VERSION = 1
STORAGE_KEY = "journey_guardian.end_of_day_review"


class EndOfDayReview:
    """Summarise the local day's rail evidence without making provider calls."""

    def __init__(
        self,
        hass: HomeAssistant,
        history: CheckHistory,
        *,
        delay_repay_threshold_minutes: int = 15,
    ) -> None:
        self._hass = hass
        self._history = history
        self._delay_repay_threshold_minutes = delay_repay_threshold_minutes
        self._cancel = None
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._last_review: dict[str, Any] | None = None

    async def async_load(self) -> None:
        """Restore the latest privacy-safe review for diagnostics."""
        stored = await self._store.async_load()
        if isinstance(stored, Mapping):
            review = stored.get("last_review")
            self._last_review = dict(review) if isinstance(review, Mapping) else None

    @callback
    def start(self) -> None:
        now = dt_util.now()
        previous_day = (now.date() - timedelta(days=1)).isoformat()
        if (
            now.hour >= 4
            and (self._last_review or {}).get("review_date") != previous_day
        ):
            self._hass.async_create_task(
                self.async_review_date(now.date() - timedelta(days=1)),
                "journey_guardian recover travel-day review",
            )
        self._schedule()

    @callback
    def stop(self) -> None:
        if self._cancel:
            self._cancel()
            self._cancel = None

    @callback
    def _schedule(self) -> None:
        now = dt_util.now()
        point = datetime.combine(now.date(), time(4, 0), tzinfo=now.tzinfo)
        if point <= now:
            point += timedelta(days=1)
        self._cancel = async_track_point_in_utc_time(self._hass, self._run, point)

    async def _run(self, _now: datetime) -> None:
        await self.async_review_date(dt_util.now().date() - timedelta(days=1))
        self._schedule()

    async def async_review_date(self, review_date: date) -> dict[str, Any]:
        """Review one local travel day without contacting a provider."""
        day = review_date.isoformat()
        groups: dict[str, list[dict]] = defaultdict(list)
        for record in self._history.records():
            record_day = record.get("journey_date") or str(
                record.get("checked_at", "")
            )[:10]
            if record_day == day:
                groups[str(record.get("journey_fingerprint", "unknown"))].append(record)
        journeys = [
            _review_journey(records, self._delay_repay_threshold_minutes)
            for records in groups.values()
        ]
        delayed = sum(item["delay_observed"] for item in journeys)
        potential_claims = sum(
            item["claim_eligibility"] == "potentially_eligible"
            for item in journeys
        )
        departure_delayed = sum(item["departure_delay_observed"] for item in journeys)
        cancelled = sum(item["cancelled"] for item in journeys)
        unresolved = sum(
            item["classification"] == "insufficient_evidence" for item in journeys
        )
        attention_required = potential_claims + unresolved > 0
        review = {
            "reviewed_at": dt_util.now().isoformat(),
            "review_date": day,
            "journey_count": len(journeys),
            "delayed_count": delayed,
            "potential_claim_count": potential_claims,
            "delay_repay_threshold_minutes": self._delay_repay_threshold_minutes,
            "departure_delay_observed_count": departure_delayed,
            "cancelled_count": cancelled,
            "unresolved_count": unresolved,
            "attention_required": attention_required,
            "notification_sent": bool(groups and attention_required),
            "journeys": journeys,
        }
        self._last_review = review
        await self._store.async_save({"last_review": review})
        if groups and attention_required:
            message = (
                f"Journey Guardian nightly review: {len(groups)} journey(s), "
                f"{potential_claims} possible claim(s), {cancelled} cancelled, "
                f"{unresolved} unresolved. Review journeys needing attention. "
                "This summary used saved local evidence and made no rail API calls."
            )
            persistent_notification.async_create(
                self._hass,
                message,
                title="UK Journey Guardian nightly review",
                notification_id="journey_guardian_end_of_day",
            )
        return review

    def diagnostics(self) -> dict[str, Any] | None:
        """Return a defensive copy of the latest privacy-safe review."""
        return deepcopy(self._last_review) if self._last_review is not None else None


def _review_journey(
    records: list[dict[str, Any]], delay_repay_threshold_minutes: int
) -> dict[str, Any]:
    """Classify one journey without mistaking departure data for completion."""
    latest = records[-1]
    arrival_delay = latest.get("arrival_delay_minutes")
    has_arrival = (
        latest.get("completion_status") == "completed"
        and latest.get("scheduled_arrival") is not None
        and latest.get("actual_arrival") is not None
        and isinstance(arrival_delay, int)
    )
    cancelled = bool(latest.get("cancelled")) or latest.get("status") == "cancelled"
    departure_delay = latest.get("status") == "delayed"

    if cancelled:
        classification = "potential_claim"
        reason = "service_cancelled"
    elif has_arrival and arrival_delay >= delay_repay_threshold_minutes:
        classification = "potential_claim"
        reason = "destination_delay_meets_threshold"
    elif has_arrival and arrival_delay > 0:
        classification = "delay_below_threshold"
        reason = "destination_delay_below_threshold"
    elif has_arrival:
        classification = "not_delayed"
        reason = "destination_arrival_confirmed"
    else:
        classification = "insufficient_evidence"
        reason = (
            "latest_check_failed"
            if latest.get("outcome") != "success"
            else "actual_arrival_missing"
        )

    return {
        "journey_fingerprint": latest.get("journey_fingerprint"),
        "origin_code": latest.get("origin_code"),
        "destination_code": latest.get("destination_code"),
        "classification": classification,
        "reason": reason,
        "claim_eligibility": (
            "potentially_eligible"
            if classification == "potential_claim"
            else "unknown"
            if classification == "insufficient_evidence"
            else "not_eligible"
        ),
        "delay_repay_threshold_minutes": delay_repay_threshold_minutes,
        "scheduled_arrival": latest.get("scheduled_arrival"),
        "actual_arrival": latest.get("actual_arrival"),
        "arrival_delay_minutes": arrival_delay if has_arrival else None,
        "delay_observed": bool(has_arrival and arrival_delay > 0),
        "departure_delay_observed": departure_delay,
        "cancelled": cancelled,
        "completion_status": latest.get("completion_status") or "unknown",
        "evidence_source": latest.get("evidence_source"),
        "evidence_observed_at": latest.get("evidence_observed_at"),
        "evidence_freshness": latest.get("evidence_freshness"),
        "check_count": len(records),
        "latest_check_at": latest.get("checked_at"),
    }
