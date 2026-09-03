"""Defensive normalization and matching of saved rail-board responses."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any

from .models import JourneyEvent, RailObservation

MATCH_WINDOW = timedelta(hours=2)


class RailDataError(ValueError):
    """Provider data cannot safely produce a rail observation."""

    def __init__(self, category: str) -> None:
        """Expose only a stable, privacy-safe error category."""
        super().__init__(category)
        self.category = category


@dataclass(frozen=True, slots=True)
class RailServiceCandidate:
    """Validated provider record kept separate from decision output."""

    provider_identity: str
    service_identity: str
    scheduled_departure: datetime
    predicted_departure: datetime | None
    cancelled: bool
    platform: str | None
    operator_name: str
    destination_name: str


def normalize_station_board(
    payload: Mapping[str, Any],
    *,
    journey: JourneyEvent,
    observed_at: datetime,
    expected_station_code: str,
    source: str = "transportapi",
    classification: str = "provider_normalized",
) -> RailObservation:
    """Validate, normalize and uniquely match a station board to a journey."""
    candidates = parse_station_board(
        payload,
        timezone=journey.start.tzinfo,
        expected_station_code=expected_station_code,
    )
    selected = match_journey(candidates, journey)
    delay_minutes = 0
    if selected.predicted_departure is not None:
        delay_minutes = max(
            0,
            round(
                (
                    selected.predicted_departure - selected.scheduled_departure
                ).total_seconds()
                / 60
            ),
        )
    return RailObservation(
        scenario=("cancelled" if selected.cancelled else "observed"),
        source=source,
        classification=classification,
        observed_at=observed_at,
        scheduled_departure=selected.scheduled_departure,
        predicted_departure=selected.predicted_departure,
        delay_minutes=delay_minutes,
        cancelled=selected.cancelled,
        leg_count=1,
        provider_available=True,
        service_identity=selected.service_identity,
        platform=selected.platform,
        match_quality="unique_best",
    )


def parse_station_board(
    payload: Mapping[str, Any],
    *,
    timezone: tzinfo | None,
    expected_station_code: str,
) -> tuple[RailServiceCandidate, ...]:
    """Return validated services without retaining the raw provider payload."""
    if not isinstance(payload, Mapping):
        raise RailDataError("rail_response_malformed")
    station_code = str(payload.get("station_code", "")).strip().upper()
    if station_code != expected_station_code.strip().upper():
        raise RailDataError("rail_station_mismatch")
    service_date = _parse_date(payload.get("date"))
    departures = payload.get("departures")
    records = departures.get("all") if isinstance(departures, Mapping) else None
    if not isinstance(records, list):
        raise RailDataError("rail_response_malformed")

    by_identity: dict[str, RailServiceCandidate] = {}
    for record in records:
        candidate = _parse_service(record, service_date, timezone)
        if candidate is None:
            continue
        previous = by_identity.get(candidate.provider_identity)
        if previous is not None and (
            previous.scheduled_departure != candidate.scheduled_departure
            or previous.destination_name.casefold()
            != candidate.destination_name.casefold()
            or previous.operator_name.casefold() != candidate.operator_name.casefold()
        ):
            raise RailDataError("rail_record_conflict")
        # An otherwise identical later record is a provider correction (for
        # example a revised platform or expected departure), so last wins.
        by_identity[candidate.provider_identity] = candidate
    if not by_identity:
        raise RailDataError("rail_response_no_services")
    return tuple(by_identity.values())


def match_journey(
    candidates: Sequence[RailServiceCandidate], journey: JourneyEvent
) -> RailServiceCandidate:
    """Choose one service using time, destination and operator evidence."""
    scored: list[tuple[int, RailServiceCandidate]] = []
    journey_operator = journey.summary.split(" - ", 1)[0].strip().casefold()
    destination = _normalise(journey.destination_confirmation)
    for candidate in candidates:
        aligned = _align_to_journey(candidate, journey.start)
        difference = abs(aligned.scheduled_departure - journey.start)
        if difference > MATCH_WINDOW:
            continue
        minutes = round(difference.total_seconds() / 60)
        score = 500 - minutes
        if destination and destination in _normalise(aligned.destination_name):
            score += 100
        candidate_operator = aligned.operator_name.casefold()
        if journey_operator and candidate_operator and (
            journey_operator in candidate_operator
            or candidate_operator in journey_operator
        ):
            score += 50
        scored.append((score, aligned))
    if not scored:
        raise RailDataError("rail_service_not_found")
    best_score = max(score for score, _candidate in scored)
    best = [candidate for score, candidate in scored if score == best_score]
    if len(best) != 1:
        raise RailDataError("rail_service_ambiguous")
    return best[0]


def _parse_service(
    record: Any, service_date: date, timezone: tzinfo | None
) -> RailServiceCandidate | None:
    if not isinstance(record, Mapping):
        return None
    mode = str(record.get("mode", "train")).casefold()
    if mode != "train":
        return None
    aimed = _parse_clock(record.get("aimed_departure_time"))
    destination = str(record.get("destination_name", "")).strip()
    operator = str(
        record.get("operator_name") or record.get("operator") or ""
    ).strip()
    provider_identity = str(
        record.get("train_uid") or record.get("service") or ""
    ).strip()
    if aimed is None or not destination or not provider_identity:
        return None
    scheduled = datetime.combine(service_date, aimed, tzinfo=timezone)
    expected_raw = str(record.get("expected_departure_time", "")).strip()
    status = str(record.get("status", "")).casefold()
    cancelled = "cancel" in status or "cancel" in expected_raw.casefold()
    predicted = None
    if not cancelled:
        expected = _parse_clock(expected_raw)
        if expected is not None:
            predicted = datetime.combine(service_date, expected, tzinfo=timezone)
            if predicted < scheduled - timedelta(hours=12):
                predicted += timedelta(days=1)
            if predicted == scheduled:
                predicted = None
    platform = str(record.get("platform", "")).strip() or None
    identity_input = f"{provider_identity}|{service_date.isoformat()}"
    service_identity = hashlib.sha256(identity_input.encode()).hexdigest()[:16]
    return RailServiceCandidate(
        provider_identity=provider_identity,
        service_identity=service_identity,
        scheduled_departure=scheduled,
        predicted_departure=predicted,
        cancelled=cancelled,
        platform=platform,
        operator_name=operator,
        destination_name=destination,
    )


def _align_to_journey(
    candidate: RailServiceCandidate, journey_start: datetime
) -> RailServiceCandidate:
    options = (
        candidate,
        replace(
            candidate,
            scheduled_departure=candidate.scheduled_departure - timedelta(days=1),
            predicted_departure=(
                candidate.predicted_departure - timedelta(days=1)
                if candidate.predicted_departure is not None
                else None
            ),
        ),
        replace(
            candidate,
            scheduled_departure=candidate.scheduled_departure + timedelta(days=1),
            predicted_departure=(
                candidate.predicted_departure + timedelta(days=1)
                if candidate.predicted_departure is not None
                else None
            ),
        ),
    )
    return min(
        options,
        key=lambda item: abs(item.scheduled_departure - journey_start),
    )


def _parse_date(value: Any) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as err:
        raise RailDataError("rail_response_malformed") from err


def _parse_clock(value: Any) -> time | None:
    text = str(value or "").strip()
    for pattern in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).time()
        except ValueError:
            continue
    return None


def _normalise(value: str) -> str:
    return " ".join(value.casefold().replace("&", "and").split())
