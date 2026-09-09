"""Pure, review-only connection-risk assessment for future split-journey work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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
    available = int(
        (outbound_departure - inbound_arrival).total_seconds() // 60
    )
    if available < 0:
        classification = "missed"
    elif available < minimum_minutes:
        classification = "at_risk"
    else:
        classification = "viable"
    return ConnectionRisk(
        classification=classification,
        minutes_available=available,
        minimum_minutes=minimum_minutes,
    )
