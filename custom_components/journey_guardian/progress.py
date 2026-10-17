"""Local GPS station observations, independent of rail completion evidence."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import JourneySnapshot

LOCATION_MAX_AGE = timedelta(minutes=5)
MAX_ACCURACY_METRES = 100


def station_label(name: str) -> str:
    """Strip only the owner's leading map-sort prefix."""
    return name.removeprefix("zzz ").strip()


def parse_progress_zones(value: str | None) -> tuple[str, ...]:
    """Validate an explicitly ordered route without resolving personal data."""
    if not value or not value.strip():
        return ()
    zones = tuple(line.strip() for line in value.splitlines() if line.strip())
    if (
        not 2 <= len(zones) <= 100
        or len(set(zones)) != len(zones)
        or any(not re.fullmatch(r"zone\.[a-z0-9_]+", zone) for zone in zones)
    ):
        raise ValueError("invalid_progress_zones")
    return zones


def parse_progress_alternatives(
    value: str | None, base: tuple[str, ...]
) -> tuple[tuple[str, ...], ...]:
    """Validate bounded, acyclic branches anchored to the base route."""
    if not value or not value.strip():
        return ()
    paths = []
    interiors: set[str] = set()
    try:
        for line in value.splitlines():
            if not line.strip():
                continue
            path = parse_progress_zones(line.replace(">", "\n"))
            if (
                len(path) < 3
                or base.index(path[0]) >= base.index(path[-1])
                or set(path[1:-1]) & (set(base) | interiors)
            ):
                raise ValueError
            interiors.update(path[1:-1])
            paths.append(path)
        if len(paths) > 4 or len(base) + len(interiors) > 100:
            raise ValueError
    except ValueError, IndexError:
        raise ValueError("invalid_progress_alternatives") from None
    return tuple(paths)


def candidate_routes(
    zones: tuple[StationZone, ...],
    alternatives: tuple[tuple[StationZone, ...], ...],
    origin: str,
    destination: str,
) -> tuple[tuple[StationZone, ...], ...]:
    """Enumerate a small directed network, reversing it for return journeys."""
    stations = {
        zone.entity_id: zone for path in (zones, *alternatives) for zone in path
    }
    origins = [
        key
        for key, zone in stations.items()
        if _name_key(zone.name) == _name_key(origin)
    ]
    destinations = [
        key
        for key, zone in stations.items()
        if _name_key(zone.name) == _name_key(destination)
    ]
    if len(origins) != 1 or len(destinations) != 1 or origins == destinations:
        return ()
    for reverse in (False, True):
        edges: dict[str, list[str]] = {}
        for path in (zones, *alternatives):
            ordered = path[::-1] if reverse else path
            for left, right in zip(ordered, ordered[1:], strict=False):
                neighbours = edges.setdefault(left.entity_id, [])
                if right.entity_id not in neighbours:
                    neighbours.append(right.entity_id)
        routes = []

        def visit(path, edges, routes):
            if path[-1] == destinations[0]:
                routes.append(tuple(stations[key] for key in path))
                return
            for neighbour in edges.get(path[-1], []):
                if neighbour not in path and len(routes) < 16:
                    visit((*path, neighbour), edges, routes)

        visit((origins[0],), edges, routes)
        if routes:
            return tuple(routes)
    return ()


@dataclass(frozen=True)
class StationZone:
    """A configured station marker with a human-readable label."""

    entity_id: str
    name: str
    latitude: float
    longitude: float
    radius: float


def finite_number(value: object) -> float | None:
    """Reject missing, boolean, and non-finite location attributes."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def distance_metres(lat: float, lon: float, zone: StationZone) -> float:
    """Great-circle distance suitable for local zone containment."""
    delta_lat = math.radians(zone.latitude - lat)
    delta_lon = math.radians(zone.longitude - lon)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(math.radians(lat))
        * math.cos(math.radians(zone.latitude))
        * math.sin(delta_lon / 2) ** 2
    )
    return 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, a))))


def _name_key(name: str) -> str:
    return " ".join(station_label(name).casefold().split())


class StationProgress:
    """Keep only positively observed waypoints for the current calendar leg."""

    def __init__(self) -> None:
        self.key: str | None = None
        self.last_index: int | None = None
        self.observed_at: datetime | None = None
        self.candidate_positions: dict[str, int] = {}

    def reset(self) -> None:
        self.key = None
        self.last_index = None
        self.observed_at = None
        self.candidate_positions = {}

    def update(
        self,
        snapshot: JourneySnapshot,
        zones: tuple[StationZone, ...],
        *,
        now: datetime,
        latitude: object = None,
        longitude: object = None,
        accuracy: object = None,
        location_time: datetime | None = None,
        alternatives: tuple[tuple[StationZone, ...], ...] = (),
    ) -> dict:
        """Describe GPS proximity without inferring boarding or station passage."""
        base = {"evidence": "gps_proximity", "rail_arrival_confirmed": False}
        journey = snapshot.next_journey
        if snapshot.simulation_active or journey is None:
            self.reset()
            return {**base, "status": "idle"}
        if not zones:
            self.reset()
            return {**base, "status": "route_unavailable"}
        routes = candidate_routes(
            zones, alternatives, journey.origin_name, journey.destination_confirmation
        )
        if not routes:
            self.reset()
            return {**base, "status": "route_unmatched"}
        route = routes[0]
        identities = {
            hashlib.sha256(
                repr(tuple(zone.entity_id for zone in path)).encode()
            ).hexdigest(): path
            for path in routes
        }
        identity = repr(
            (
                journey.start.isoformat(),
                journey.end,
                route if len(routes) == 1 else routes,
            )
        )
        key = hashlib.sha256(identity.encode()).hexdigest()
        if self.key != key:
            self.reset()
            self.key = key
        if (
            self.candidate_positions
            and any(
                token not in identities
                or isinstance(index, bool)
                or not isinstance(index, int)
                or not 0 <= index < len(identities[token])
                for token, index in self.candidate_positions.items()
            )
        ) or (
            self.last_index is not None
            and not 0 <= self.last_index < max(map(len, routes))
        ):
            self.reset()
            self.key = key
        # A future booking must not interpret an unrelated station visit as travel.
        if now < journey.start - timedelta(hours=2):
            return {**base, "status": "waiting"}
        if journey.end is None or now > journey.end + timedelta(hours=12):
            self.reset()
            return {**base, "status": "idle"}

        def result(status: str, current: str | None = None) -> dict:
            active = (
                {token: identities[token] for token in self.candidate_positions}
                if self.candidate_positions
                else identities
            )
            next_names = []
            last_names = []
            for token, path in active.items():
                index = self.candidate_positions.get(
                    token, self.last_index if len(routes) == 1 else None
                )
                next_index = 0 if index is None else index + 1
                next_names.append(
                    station_label(path[next_index].name)
                    if next_index < len(path)
                    else None
                )
                last_names.append(
                    station_label(path[index].name) if index is not None else None
                )
            counts = sorted({len(path) for path in active.values()})
            return {
                **base,
                "status": status,
                "current_station": current,
                "last_observed_station": (
                    last_names[0] if len(set(last_names)) == 1 else None
                ),
                "last_observed_at": (
                    self.observed_at.isoformat() if self.observed_at else None
                ),
                "next_waypoint": (next_names[0] if len(set(next_names)) == 1 else None),
                "next_waypoints": list(
                    dict.fromkeys(name for name in next_names if name is not None)
                ),
                "waypoint_count": counts[0] if len(counts) == 1 else None,
                "candidate_route_count": len(active),
                "route_waypoints": (
                    [station_label(zone.name) for zone in next(iter(active.values()))]
                    if len(active) == 1
                    else []
                ),
                "route_selection": "ambiguous"
                if len(active) > 1
                else ("observed" if len(routes) > 1 else "configured"),
                "location_age_seconds": (
                    max(0, int((now - location_time).total_seconds()))
                    if location_time
                    else None
                ),
            }

        lat, lon, error = map(finite_number, (latitude, longitude, accuracy))
        if (
            lat is None
            or lon is None
            or error is None
            or not -90 <= lat <= 90
            or not -180 <= lon <= 180
            or error < 0
            or location_time is None
        ):
            return result("location_unavailable")
        if location_time > now + timedelta(seconds=30):
            return result("location_unavailable")
        if now - location_time > LOCATION_MAX_AGE:
            return result("location_stale")
        if error > MAX_ACCURACY_METRES:
            return result("location_inaccurate")
        all_zones = {zone.entity_id: zone for path in routes for zone in path}
        matches = [
            zone.entity_id
            for zone in all_zones.values()
            if distance_metres(lat, lon, zone) + error <= zone.radius
        ]
        if len(matches) > 1:
            return result("location_ambiguous")
        if not matches:
            return result("between_observations")
        if self.observed_at is not None and location_time < self.observed_at:
            return result("location_out_of_order")
        station = matches[0]
        compatible = {}
        contains = False
        for token, path in identities.items():
            if self.candidate_positions and token not in self.candidate_positions:
                continue
            ids = [zone.entity_id for zone in path]
            if station in ids:
                contains = True
                index = ids.index(station)
                previous = self.candidate_positions.get(
                    token, self.last_index if len(routes) == 1 else None
                )
                if previous is None or index >= previous:
                    compatible[token] = index
        if not compatible:
            return result("direction_conflict" if contains else "route_conflict")
        self.candidate_positions = compatible
        self.last_index = next(iter(compatible.values()))
        self.observed_at = location_time
        return result("near_station", station_label(all_zones[station].name))
