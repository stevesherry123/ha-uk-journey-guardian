"""Small, privacy-conscious Google Routes station-access client."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from aiohttp import ClientError, ClientSession
from homeassistant.util import dt as dt_util

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = "routes.duration,routes.distanceMeters"
MODE_MAP = {
    "driving": "DRIVE",
    "walking": "WALK",
    "bicycling": "BICYCLE",
    "transit": "TRANSIT",
}


class GoogleRoutesError(Exception):
    """Sanitized Google Routes acquisition error."""


@dataclass(frozen=True, slots=True)
class StationAccessEstimate:
    """Normalized route duration used by the timing engine."""

    duration_minutes: int
    distance_meters: int | None
    mode: str
    observed_at: datetime
    cache_hit: bool = False


class GoogleRoutesClient:
    """Acquire and briefly cache one station-access estimate."""

    def __init__(self, session: ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key.strip()
        self._cache: dict[tuple[Any, ...], tuple[datetime, StationAccessEstimate]] = {}

    @property
    def configured(self) -> bool:
        """Return whether a credential is available."""
        return bool(self._api_key)

    async def async_route(
        self,
        *,
        latitude: float,
        longitude: float,
        destination: str,
        mode: str,
        departure_time: datetime,
        force_refresh: bool = False,
    ) -> StationAccessEstimate:
        """Return a normalized duration without exposing provider responses."""
        if not self.configured or mode not in MODE_MAP:
            raise GoogleRoutesError("not_configured")
        now = dt_util.now()
        cache_key = (
            round(latitude, 4),
            round(longitude, 4),
            destination.casefold().strip(),
            mode,
            int(departure_time.timestamp() // 900),
        )
        cached = self._cache.get(cache_key)
        if not force_refresh and cached is not None and now <= cached[0]:
            return replace(cached[1], cache_hit=True)

        request: dict[str, Any] = {
            "origin": {
                "location": {
                    "latLng": {
                        "latitude": latitude,
                        "longitude": longitude,
                    }
                }
            },
            "destination": {"address": destination},
            "travelMode": MODE_MAP[mode],
            "departureTime": departure_time.astimezone(UTC).isoformat().replace(
                "+00:00", "Z"
            ),
        }
        if mode == "driving":
            request["routingPreference"] = "TRAFFIC_AWARE"
        elif mode == "transit":
            request["transitPreferences"] = {
                "routingPreference": "FEWER_TRANSFERS"
            }
        try:
            async with self._session.post(
                ROUTES_URL,
                headers={
                    "X-Goog-Api-Key": self._api_key,
                    "X-Goog-FieldMask": FIELD_MASK,
                },
                json=request,
                timeout=15,
            ) as response:
                if response.status != 200:
                    raise GoogleRoutesError("provider_unavailable")
                payload = await response.json()
        except (ClientError, TimeoutError, ValueError) as err:
            raise GoogleRoutesError("provider_unavailable") from err

        routes = payload.get("routes")
        if not isinstance(routes, list) or not routes:
            raise GoogleRoutesError("route_unavailable")
        route = routes[0]
        if not isinstance(route, dict):
            raise GoogleRoutesError("invalid_response")
        duration = route.get("duration")
        if not isinstance(duration, str) or not duration.endswith("s"):
            raise GoogleRoutesError("invalid_response")
        try:
            duration_minutes = max(1, math.ceil(float(duration[:-1]) / 60))
        except ValueError as err:
            raise GoogleRoutesError("invalid_response") from err
        distance = route.get("distanceMeters")
        estimate = StationAccessEstimate(
            duration_minutes=duration_minutes,
            distance_meters=distance if isinstance(distance, int) else None,
            mode=mode,
            observed_at=now,
        )
        self._cache[cache_key] = (
            now + _cache_ttl(departure_time, now),
            estimate,
        )
        if len(self._cache) > 20:
            self._cache.pop(next(iter(self._cache)))
        return estimate


def _cache_ttl(departure_time: datetime, now: datetime) -> timedelta:
    """Refresh more often only as the station-access departure approaches."""
    until_departure = departure_time - now
    if until_departure > timedelta(hours=6):
        return timedelta(hours=4)
    if until_departure > timedelta(hours=2):
        return timedelta(hours=1)
    if until_departure > timedelta(minutes=45):
        return timedelta(minutes=30)
    return timedelta(minutes=10)
