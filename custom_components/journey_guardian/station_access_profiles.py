"""Explicit origin-station preferences for modes and local routing sensors."""

from __future__ import annotations

import re
from collections.abc import Mapping

from .models import JourneyEvent
from .station import StationResolutionError, resolve_station

VALID_MODES = frozenset({"driving", "walking", "bicycling", "transit"})
WAZE_SENSOR = re.compile(r"waze:(sensor\.[a-z0-9_]+)")


class StationAccessProfileError(ValueError):
    """A configured station access profile could not be safely understood."""


def parse_station_access_profiles(value: object) -> dict[str, str]:
    """Parse legacy modes or explicit local Waze sensors, with optional aliases."""
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
    codes: set[str] = set()
    aliases: set[str] = set()
    for raw_code, raw_mode in pairs:
        code, _, alias = str(raw_code).strip().partition("|")
        code, alias = code.strip().upper(), alias.strip()
        mode = str(raw_mode).strip().casefold()
        if (
            not re.fullmatch(r"[A-Z]{3}", code)
            or (mode not in VALID_MODES and not WAZE_SENSOR.fullmatch(mode))
            or ("|" in str(raw_code) and not alias)
            or len(alias) > 100
            or any(char in alias for char in "|=#\n")
        ):
            raise StationAccessProfileError("invalid_station_access_profiles")
        normalized_alias = _alias(alias)
        if code in codes or (alias and normalized_alias in aliases):
            raise StationAccessProfileError("duplicate_station_access_profile")
        codes.add(code)
        if alias:
            aliases.add(normalized_alias)
        profiles[f"{code}|{alias}" if alias else code] = mode
    return profiles


def mode_for_journey(journey: JourneyEvent, profiles: Mapping[str, str]) -> str | None:
    """Return the selected physical mode without choosing a different provider."""
    value = _profile_for_journey(journey, profiles)
    return "driving" if value and WAZE_SENSOR.fullmatch(value) else value


def waze_sensor_for_journey(
    journey: JourneyEvent, profiles: Mapping[str, str]
) -> str | None:
    """Return only the sensor explicitly bound to this train's origin station."""
    value = _profile_for_journey(journey, profiles)
    match = WAZE_SENSOR.fullmatch(value or "")
    return match[1] if match else None


def _alias(value: str) -> str:
    return " ".join(value.casefold().split()).removeprefix("zzz ")


def _profile_for_journey(
    journey: JourneyEvent, profiles: Mapping[str, str]
) -> str | None:
    try:
        station = resolve_station(
            origin_name=journey.origin_name,
            origin_code=journey.origin_code,
            location=journey.location,
        )
    except StationResolutionError as err:
        if err.category != "station_code_unresolved":
            return None
        matches = [
            value
            for key, value in profiles.items()
            if "|" in key
            and _alias(key.split("|", 1)[1]) == _alias(journey.origin_name)
        ]
        return matches[0] if len(matches) == 1 else None
    return next(
        (
            value
            for key, value in profiles.items()
            if key.split("|", 1)[0] == station.code
        ),
        None,
    )
