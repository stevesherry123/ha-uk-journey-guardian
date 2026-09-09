"""Station-specific travel-mode preferences without personal location data."""

from __future__ import annotations

import re
from collections.abc import Mapping

from .models import JourneyEvent
from .station import StationResolutionError, resolve_station

VALID_MODES = frozenset({"driving", "walking", "bicycling", "transit"})


class StationAccessProfileError(ValueError):
    """A configured station access profile could not be safely understood."""


def parse_station_access_profiles(value: object) -> dict[str, str]:
    """Parse one ``CRS=mode`` preference per line into a stable mapping."""
    if isinstance(value, Mapping):
        pairs = value.items()
    elif value is None or not str(value).strip():
        return {}
    else:
        pairs = []
        for line in str(value).splitlines():
            cleaned = line.split("#", 1)[0].strip()
            if not cleaned:
                continue
            code, separator, mode = cleaned.partition("=")
            if not separator:
                raise StationAccessProfileError("invalid_station_access_profiles")
            pairs.append((code, mode))

    profiles: dict[str, str] = {}
    for raw_code, raw_mode in pairs:
        code = str(raw_code).strip().upper()
        mode = str(raw_mode).strip().casefold()
        if not re.fullmatch(r"[A-Z]{3}", code) or mode not in VALID_MODES:
            raise StationAccessProfileError("invalid_station_access_profiles")
        if code in profiles:
            raise StationAccessProfileError("duplicate_station_access_profile")
        profiles[code] = mode
    return profiles


def mode_for_journey(
    journey: JourneyEvent, profiles: Mapping[str, str]
) -> str | None:
    """Return a profile mode only when the origin has a deterministic CRS hint."""
    try:
        station = resolve_station(
            origin_name=journey.origin_name,
            origin_code=journey.origin_code,
            location=journey.location,
        )
    except StationResolutionError:
        return None
    return profiles.get(station.code)
