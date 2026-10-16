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

    def reset(self) -> None:
        self.key = None
        self.last_index = None
        self.observed_at = None

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
        origins = [
            i
            for i, zone in enumerate(zones)
            if _name_key(zone.name) == _name_key(journey.origin_name)
        ]
        destinations = [
            i
            for i, zone in enumerate(zones)
            if _name_key(zone.name) == _name_key(journey.destination_confirmation)
        ]
        if len(origins) != 1 or len(destinations) != 1 or origins == destinations:
            self.reset()
            return {**base, "status": "route_unmatched"}
        start, end = origins[0], destinations[0]
        route = zones[start : end + 1] if start < end else zones[end : start + 1][::-1]
        identity = repr((journey.start.isoformat(), journey.end, route))
        key = hashlib.sha256(identity.encode()).hexdigest()
        if self.key != key:
            self.reset()
            self.key = key
        if self.last_index is not None and not 0 <= self.last_index < len(route):
            self.reset()
            self.key = key
        # A future booking must not interpret an unrelated station visit as travel.
        if now < journey.start - timedelta(hours=2):
            return {**base, "status": "waiting"}
        if journey.end is None or now > journey.end + timedelta(hours=12):
            self.reset()
            return {**base, "status": "idle"}

        def result(status: str, current: str | None = None) -> dict:
            next_index = 0 if self.last_index is None else self.last_index + 1
            return {
                **base,
                "status": status,
                "current_station": current,
                "last_observed_station": (
                    station_label(route[self.last_index].name)
                    if self.last_index is not None
                    else None
                ),
                "last_observed_at": (
                    self.observed_at.isoformat() if self.observed_at else None
                ),
                "next_waypoint": (
                    station_label(route[next_index].name)
                    if next_index < len(route)
                    else None
                ),
                "waypoint_count": len(route),
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
        matches = [
            i
            for i, zone in enumerate(route)
            if distance_metres(lat, lon, zone) + error <= zone.radius
        ]
        if len(matches) > 1:
            return result("location_ambiguous")
        if not matches:
            return result("between_observations")
        index = matches[0]
        if self.last_index is not None and index < self.last_index:
            return result("direction_conflict")
        if self.observed_at is not None and location_time < self.observed_at:
            return result("location_out_of_order")
        self.last_index = index
        self.observed_at = location_time
        return result("near_station", station_label(route[index].name))
