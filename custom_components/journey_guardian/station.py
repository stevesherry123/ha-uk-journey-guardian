"""Privacy-safe station identity resolution from calendar and provider data."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

_CRS_PATTERNS = (
    re.compile(r"(?:\[|\()([A-Z]{3})(?:\]|\))\s*$", re.IGNORECASE),
    re.compile(r"\bCRS\s*[:=-]\s*([A-Z]{3})\b", re.IGNORECASE),
)


class StationResolutionError(ValueError):
    """A station could not be resolved without guessing."""

    def __init__(self, category: str) -> None:
        """Expose only a stable, privacy-safe error category."""
        super().__init__(category)
        self.category = category


@dataclass(frozen=True, slots=True)
class StationResolution:
    """A resolved station identity and its provenance."""

    code: str
    name: str
    source: str
    confidence: str


def resolve_station(
    *,
    origin_name: str,
    origin_code: str = "CALENDAR",
    location: str = "",
    places_payload: Mapping[str, Any] | None = None,
) -> StationResolution:
    """Resolve a CRS code explicitly or from a saved provider Places response."""
    configured_code = _valid_crs(origin_code)
    embedded_codes = {
        code
        for text in (origin_name, location)
        if (code := _extract_explicit_code(text)) is not None
    }
    if configured_code is not None and origin_code not in {"CALENDAR", "SIM"}:
        if embedded_codes and embedded_codes != {configured_code}:
            raise StationResolutionError("station_code_conflict")
        return StationResolution(
            code=configured_code,
            name=_strip_explicit_code(origin_name),
            source="configured",
            confidence="explicit",
        )

    if len(embedded_codes) > 1:
        raise StationResolutionError("station_code_conflict")
    if embedded_codes:
        return StationResolution(
            code=embedded_codes.pop(),
            name=_strip_explicit_code(origin_name),
            source="calendar",
            confidence="explicit",
        )

    if places_payload is None:
        raise StationResolutionError("station_code_unresolved")

    places = _places(places_payload)
    wanted = _normalise_name(origin_name)
    if not wanted:
        raise StationResolutionError("station_not_found")
    matches: dict[str, str] = {}
    for place in places:
        place_type = str(place.get("type", "")).casefold()
        if place_type and place_type not in {"train_station", "station"}:
            continue
        name = str(
            place.get("name")
            or place.get("station_name")
            or place.get("description")
            or ""
        ).strip()
        code = _valid_crs(
            str(place.get("station_code") or place.get("code") or "")
        )
        if code is not None and _normalise_name(name) == wanted:
            matches[code] = name

    if not matches:
        raise StationResolutionError("station_not_found")
    if len(matches) > 1:
        raise StationResolutionError("station_match_ambiguous")
    code, name = next(iter(matches.items()))
    return StationResolution(
        code=code,
        name=name,
        source="provider_places",
        confidence="exact_name",
    )


def _places(payload: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    for key in ("member", "places", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            if not all(isinstance(item, Mapping) for item in value):
                raise StationResolutionError("places_response_malformed")
            return value
    raise StationResolutionError("places_response_malformed")


def _valid_crs(value: str) -> str | None:
    candidate = value.strip().upper()
    return candidate if re.fullmatch(r"[A-Z]{3}", candidate) else None


def _extract_explicit_code(value: str) -> str | None:
    for pattern in _CRS_PATTERNS:
        if match := pattern.search(value):
            return match.group(1).upper()
    return None


def _strip_explicit_code(value: str) -> str:
    cleaned = value.strip()
    for pattern in _CRS_PATTERNS:
        cleaned = pattern.sub("", cleaned).strip(" ,-;")
    return cleaned


def _normalise_name(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode(
        "ascii", "ignore"
    ).decode()
    words = re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).split()
    if words and words[-1] == "station":
        words.pop()
    return " ".join(words)
