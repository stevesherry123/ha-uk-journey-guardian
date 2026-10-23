"""Calendar-only flight projection. No routing, live status or notifications."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_ROUTE = re.compile(
    r"^(?:(?P<service>[A-Z0-9]{2,3}\s?\d{1,4}[A-Z]?)\s+)?"
    r"(?P<origin>[A-Z]{3})\s+to\s+(?P<destination>[A-Z]{3})$",
    re.I,
)
_TAG = re.compile(r"^\s*\[Flight\]\s*", re.I | re.M)
_TERMINAL = re.compile(r"\bTerminal\s+([A-Z0-9]{1,4})\b", re.I)
_OPERATOR = re.compile(
    r"^([A-Za-z][A-Za-z .&-]{1,40}\s+\d{1,4}[A-Z]?),\s*Terminal\b", re.I | re.M
)
MAX_FLIGHTS = 12
MAX_CONNECTION = timedelta(hours=24)


def airport_timezones(value: object) -> dict[str, str]:
    """Validate explicit IATA=IANA profiles; never infer an airport's time zone."""
    if not isinstance(value, str):
        if value is None:
            return {}
        raise ValueError("invalid_airport_timezones")
    result = {}
    for line in value.splitlines():
        if not line.strip():
            continue
        code, separator, name = line.strip().partition("=")
        code, name = code.strip().upper(), name.strip()
        if not separator or not re.fullmatch(r"[A-Z]{3}", code) or code in result:
            raise ValueError("invalid_airport_timezones")
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError) as err:
            raise ValueError("invalid_airport_timezones") from err
        result[code] = name
    if len(result) > 100:
        raise ValueError("invalid_airport_timezones")
    return result


def _instant(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # A floating time is not enough evidence for an international flight.
        return parsed.astimezone(UTC) if parsed.utcoffset() is not None else None
    except (ValueError, OverflowError):
        return None


@dataclass(frozen=True, slots=True)
class FlightLeg:
    """Only allowlisted booking fields; never retain raw descriptions or URLs."""

    departure: datetime
    arrival: datetime
    origin: str
    destination: str
    service: str | None = None
    operating_service: str | None = None
    departure_terminal: str | None = None
    arrival_terminal: str | None = None

    def as_dict(self) -> dict:
        return {
            "departure": self.departure.isoformat(),
            "arrival": self.arrival.isoformat(),
            "origin": self.origin,
            "destination": self.destination,
            "service": self.service,
            "operating_service": self.operating_service,
            "departure_terminal": self.departure_terminal,
            "arrival_terminal": self.arrival_terminal,
        }


def parse_flights(
    events: Iterable[Mapping], now: datetime
) -> tuple[tuple[FlightLeg, ...], int]:
    """Read supported TripIt flight records, counting unsupported explicit flights."""
    legs: set[FlightLeg] = set()
    rejected = 0
    for event in events:
        summary = str(event.get("summary", "")).strip()
        description = str(event.get("description", ""))
        title = re.sub(r"^flight\s+", "", _TAG.sub("", summary), flags=re.I)
        title = title.rsplit(" - ", 1)[-1].strip()
        route = _ROUTE.fullmatch(title)
        tagged = bool(_TAG.search(summary + "\n" + description)) or bool(
            re.match(r"^flight\b", summary, re.I)
        )
        if not tagged and (not route or not route["service"]):
            continue
        start, end = _instant(event.get("start")), _instant(event.get("end"))
        if (
            not route
            or not start
            or not end
            or not timedelta(0) < end - start <= timedelta(hours=24)
        ):
            rejected += 1
            continue
        if end < now - MAX_CONNECTION:
            continue
        origin, destination = route["origin"].upper(), route["destination"].upper()
        if origin == destination:
            rejected += 1
            continue
        terminals = _TERMINAL.findall(description)
        operator = _OPERATOR.search(description)
        legs.add(
            FlightLeg(
                start,
                end,
                origin,
                destination,
                re.sub(r"\s+", "", route["service"]).upper()
                if route["service"]
                else None,
                operator[1].strip() if operator else None,
                terminals[0].upper() if len(terminals) == 2 else None,
                terminals[1].upper() if len(terminals) == 2 else None,
            )
        )
    return tuple(
        sorted(legs, key=lambda leg: (leg.departure, leg.origin, leg.service or ""))
    ), rejected


def restore_flight(row: Mapping, now: datetime) -> FlightLeg | None:
    """Validate the same allowlist when reloading bounded local context."""
    legs, _ = parse_flights(
        [
            {
                "start": row.get("departure"),
                "end": row.get("arrival"),
                "summary": (
                    f"{row.get('service') or ''} "
                    f"{row.get('origin')} to {row.get('destination')}"
                ),
                "description": "[Flight] ",
            }
        ],
        now,
    )
    if len(legs) != 1:
        return None
    operator = row.get("operating_service")
    terminals = [row.get(key) for key in ("departure_terminal", "arrival_terminal")]
    return replace(
        legs[0],
        operating_service=operator
        if isinstance(operator, str) and _OPERATOR.fullmatch(f"{operator}, Terminal")
        else None,
        departure_terminal=terminals[0]
        if isinstance(terminals[0], str)
        and re.fullmatch(r"[A-Z0-9]{1,4}", terminals[0])
        else None,
        arrival_terminal=terminals[1]
        if isinstance(terminals[1], str)
        and re.fullmatch(r"[A-Z0-9]{1,4}", terminals[1])
        else None,
    )


def retain_connection_context(
    current: tuple[FlightLeg, ...],
    previous: tuple[FlightLeg, ...],
    now: datetime,
) -> tuple[FlightLeg, ...]:
    """Retain past scheduled legs only when they connect to a current booking."""
    selected = {leg for leg in current if leg.arrival > now}
    past = sorted(
        {
            leg
            for leg in (*current, *previous)
            if now - MAX_CONNECTION <= leg.arrival <= now
        },
        key=lambda leg: leg.departure,
        reverse=True,
    )
    for leg in past:
        if any(
            leg.destination == following.origin
            and timedelta(0) <= following.departure - leg.arrival <= MAX_CONNECTION
            for following in selected
        ):
            selected.add(leg)
    return tuple(
        sorted(selected, key=lambda leg: (leg.departure, leg.origin, leg.service or ""))
    )


def flight_projection(
    legs: tuple[FlightLeg, ...],
    now: datetime,
    zones: Mapping[str, str],
    rejected: int = 0,
) -> dict:
    """Describe scheduled windows without claiming aircraft position or arrival."""
    rows = []
    for leg in legs[:MAX_FLIGHTS]:
        row = leg.as_dict()
        row.update(
            {
                "origin_timezone": zones.get(leg.origin),
                "destination_timezone": zones.get(leg.destination),
                "duration_minutes": int(
                    (leg.arrival - leg.departure).total_seconds() / 60
                ),
                "phase": "scheduled_time_passed"
                if now >= leg.arrival
                else "within_scheduled_flight"
                if now >= leg.departure
                else "scheduled",
            }
        )
        rows.append(row)
    connections = []
    for first, second in zip(legs[:MAX_FLIGHTS], legs[1:MAX_FLIGHTS], strict=False):
        gap = second.departure - first.arrival
        if first.destination == second.origin and timedelta(0) <= gap <= MAX_CONNECTION:
            connections.append(
                {
                    "airport": first.destination,
                    "start": first.arrival.isoformat(),
                    "end": second.departure.isoformat(),
                    "gap_minutes": int(gap.total_seconds() / 60),
                    "timezone": zones.get(first.destination),
                    "classification": "calendar_candidate",
                    "viability": "not_assessed",
                    "ticket_and_baggage": "not_read_from_calendar",
                }
            )
    state = "scheduled" if rows else "no_flights"
    if any(leg.departure <= now < leg.arrival for leg in legs):
        state = "within_scheduled_flight"
    elif any(
        _instant(item["start"]) <= now < _instant(item["end"]) for item in connections
    ):
        state = "connection_window"
    if rejected and not rows:
        state = "needs_attention"
    return {
        "schema_version": 1,
        "state": state,
        "source": "calendar_only",
        "checked_at": now.isoformat(),
        "live_tracking": False,
        "alerts_enabled": False,
        "legs": rows,
        "connections": connections,
        "unsupported_flight_count": rejected,
        "truncated": len(legs) > MAX_FLIGHTS,
        "local_timezones_complete": all(
            leg.origin in zones and leg.destination in zones for leg in legs
        ),
    }
