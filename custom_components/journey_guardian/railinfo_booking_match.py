"""Review-only timetable evidence for a suspected calendar destination mismatch."""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .models import JourneyEvent
from .rail import service_identity
from .railinfo_arrival import _clock, _instant

_ZONE = ZoneInfo("Europe/London")
_MAX_ROWS = 40
_MAX_AGE = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class BookingMatchRequest:
    """Explicit stations; never infer the alternative from a missing calendar leg."""

    booking: JourneyEvent
    origin_code: str
    booked_destination_code: str
    alternative_code: str

    def __post_init__(self) -> None:
        codes = (self.origin_code, self.booked_destination_code, self.alternative_code)
        if any(
            not isinstance(code, str)
            or len(code) != 3
            or not code.isascii()
            or not code.isalpha()
            or code != code.upper()
            for code in codes
        ) or len(set(codes)) != 3:
            raise ValueError("distinct_resolved_station_codes_required")
        start, end = self.booking.start, self.booking.end
        if (
            end is None or start.utcoffset() is None or end.utcoffset() is None
            or end.astimezone(UTC) <= start.astimezone(UTC)
            or end.astimezone(_ZONE).date() != start.astimezone(_ZONE).date()
        ):
            raise ValueError("same_day_booked_times_required")
        if (
            self.booking.origin_code != "CALENDAR"
            and self.booking.origin_code != self.origin_code
        ):
            raise ValueError("booking_origin_conflict")

    @property
    def departure(self) -> datetime:
        """Use the provider's UK service day and local timetable clock."""
        return self.booking.start.astimezone(_ZONE)


@dataclass(frozen=True, slots=True)
class BookingMatchProposal:
    """Timetable match only, not booked intent, live status or ticket evidence."""

    booking_fingerprint: str
    service_identity: str
    origin_code: str
    alternative_code: str
    scheduled_departure: datetime
    scheduled_arrival: datetime
    observed_at: datetime
    valid_until: datetime

    @property
    def proposal_id(self) -> str:
        """Identify this exact service, endpoint and evidence revision."""
        fields = (
            self.booking_fingerprint, self.service_identity, self.origin_code,
            self.alternative_code, self.scheduled_departure.isoformat(),
            self.scheduled_arrival.isoformat(), self.observed_at.isoformat(),
        )
        return hashlib.sha256("|".join(fields).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class BookingMatchResult:
    """Only a unique candidate has a proposal; all other outcomes stay unresolved."""

    status: str
    proposal: BookingMatchProposal | None = None
    confirmed: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Expose a response-only proposal, without raw provider or calendar data."""
        proposal = self.proposal
        return {
            "status": self.status,
            "proposal": None if proposal is None else {
                "proposal_id": proposal.proposal_id,
                "booking_fingerprint": proposal.booking_fingerprint,
                "service_identity": proposal.service_identity,
                "origin_code": proposal.origin_code,
                "alternative_code": proposal.alternative_code,
                "scheduled_departure": proposal.scheduled_departure.isoformat(),
                "scheduled_arrival": proposal.scheduled_arrival.isoformat(),
                "observed_at": proposal.observed_at.isoformat(),
                "valid_until": proposal.valid_until.isoformat(),
                "confirmation_required": not self.confirmed,
            },
        }


def normalize_booking_match(
    payload: Mapping[str, Any],
    request: BookingMatchRequest,
    *,
    observed_at: datetime,
    now: datetime,
) -> BookingMatchResult:
    """Find exactly one direct train matching both scheduled endpoint clocks."""
    if observed_at.utcoffset() is None or now.utcoffset() is None:
        raise ValueError("timezone_required")
    if not timedelta(0) <= now.astimezone(UTC) - observed_at.astimezone(UTC) < _MAX_AGE:
        return BookingMatchResult("stale_response")
    day = request.departure.date()
    if (
        not isinstance(payload, Mapping)
        or payload.get("date") != day.isoformat()
        or not isinstance(payload.get("journeys"), list)
        or len(payload["journeys"]) > _MAX_ROWS
    ):
        return BookingMatchResult("invalid_response")

    matches = []
    for route in payload["journeys"]:
        if not isinstance(route, Mapping):
            continue
        legs = route.get("legs")
        if (
            type(route.get("changes")) is not int or route["changes"] != 0
            or not isinstance(legs, list) or len(legs) != 1
            or not isinstance(legs[0], Mapping)
        ):
            continue
        leg = legs[0]
        if (
            leg.get("from_crs") != request.origin_code
            or leg.get("to_crs") != request.alternative_code
            or leg.get("mode") != "train"
        ):
            continue
        dep, arr = _clock(leg.get("dep")), _clock(leg.get("arr"))
        if dep is None or arr is None:
            continue
        departure, arrival = _instant(day, dep, _ZONE), _instant(day, arr, _ZONE)
        if (
            departure is not None and arrival is not None
            and departure.astimezone(UTC) == request.booking.start.astimezone(UTC)
            and arrival.astimezone(UTC) == request.booking.end.astimezone(UTC)
        ):
            matches.append((route, leg, departure, arrival))

    if len(matches) != 1:
        return BookingMatchResult("ambiguous_match" if matches else "no_match")
    route, leg, departure, arrival = matches[0]
    headcode = leg.get("headcode")
    if (
        not isinstance(headcode, str)
        or re.fullmatch(r"[0-9][A-Z][0-9]{2}", headcode) is None
        or any(
            (item.get("cancelled") is not None and item.get("cancelled") is not False)
            or "cancel" in str(item.get("status", "")).casefold()
            for item in (route, leg)
        )
    ):
        return BookingMatchResult("unusable_match")
    return BookingMatchResult("proposal_available", BookingMatchProposal(
        request.booking.booking_fingerprint,
        service_identity(headcode, day),
        request.origin_code, request.alternative_code, departure, arrival,
        observed_at, observed_at.astimezone(UTC) + _MAX_AGE,
    ))
