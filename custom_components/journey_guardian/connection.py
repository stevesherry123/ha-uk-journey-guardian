"""Pure, review-only connection-risk assessment for future split-journey work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class TransferAllowance:
    """Required transfer time with its user-visible provenance."""

    minutes: int
    source: str


def resolve_transfer_allowance(
    *,
    connection_minutes: int | None = None,
    station_minutes: int | None = None,
    global_minutes: int = 10,
) -> TransferAllowance:
    """Apply explicit connection, station, then global preferences."""
    for value in (connection_minutes, station_minutes, global_minutes):
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("invalid_transfer_allowance")
    if global_minutes is None:
        raise ValueError("global_transfer_allowance_required")
    for value, source in (
        (connection_minutes, "connection_override"),
        (station_minutes, "station_default"),
        (global_minutes, "global_fallback"),
    ):
        if value is not None:
            return TransferAllowance(value, source)
    raise ValueError("global_transfer_allowance_required")


@dataclass(frozen=True, slots=True)
class ConnectionRisk:
    """A deterministic assessment that never changes a journey decision."""

    classification: str
    minutes_available: int
    minimum_minutes: int


def assess_connection(
    *,
    inbound_arrival: datetime,
    outbound_departure: datetime,
    minimum_minutes: int,
) -> ConnectionRisk:
    """Classify a connection from its predicted arrival and next departure."""
    if type(minimum_minutes) is not int or minimum_minutes < 0:
        raise ValueError("invalid_transfer_allowance")
    if inbound_arrival.utcoffset() is None or outbound_departure.utcoffset() is None:
        raise ValueError("timezone_required")
    available = int(
        (
            outbound_departure.astimezone(UTC) - inbound_arrival.astimezone(UTC)
        ).total_seconds() // 60
    )
    # Predictions alone cannot establish a missed connection.
    classification = "at_risk" if available < minimum_minutes else "viable"
    return ConnectionRisk(
        classification=classification,
        minutes_available=available,
        minimum_minutes=minimum_minutes,
    )
