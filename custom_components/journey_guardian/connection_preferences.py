"""User transfer preferences, separate from station access and official minima."""

from __future__ import annotations

CONF_CONNECTION_MONITOR = "connection_monitor_enabled"
CONF_TRANSFER_FALLBACK = "connection_transfer_minutes"
CONF_STATION_TRANSFERS = "station_transfer_defaults"
DEFAULT_TRANSFER_MINUTES = 10


def station_key(value: str) -> str:
    """Match exact display names with the integration's optional zone prefix."""
    value = " ".join(value.strip().split())
    if value.startswith("zzz "):
        value = value[4:]
    return value.casefold()


def parse_station_transfers(value: str | None) -> dict[str, int]:
    """Read one Station name=minutes per line; reject ambiguity and invalid input."""
    if value is None or value == "":
        return {}
    if not isinstance(value, str):
        raise ValueError("invalid_station_transfers")
    result = {}
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if len(lines) > 64:
        raise ValueError("invalid_station_transfers")
    for line in lines:
        name, separator, raw = line.rpartition("=")
        key = station_key(name)
        if (
            not separator or not key or len(key) > 200 or key in result
            or not raw.strip().isascii() or not raw.strip().isdigit()
        ):
            raise ValueError("invalid_station_transfers")
        minutes = int(raw)
        if not 0 <= minutes <= 1440:
            raise ValueError("invalid_station_transfers")
        result[key] = minutes
    return result
