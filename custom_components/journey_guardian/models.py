"""Data models for Journey Guardian."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class JourneyEvent:
    """A normalized timed journey event."""

    start: datetime
    end: datetime | None
    summary: str
    location: str
    origin_code: str
    origin_name: str
    destination_confirmation: str
    decision_path: str

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable representation."""
        data = asdict(self)
        data["start"] = self.start.isoformat()
        data["end"] = self.end.isoformat() if self.end is not None else None
        return data


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    """Current TransportAPI allowance state."""

    date: str
    calls_used: int
    daily_limit: int
    urgent_reserve: int

    @property
    def calls_remaining(self) -> int:
        """Return total calls remaining."""
        return max(0, self.daily_limit - self.calls_used)

    @property
    def routine_calls_remaining(self) -> int:
        """Return calls available without consuming the urgent reserve."""
        return max(0, self.daily_limit - self.urgent_reserve - self.calls_used)

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable representation."""
        return {
            "date": self.date,
            "calls_used": self.calls_used,
            "daily_limit": self.daily_limit,
            "urgent_reserve": self.urgent_reserve,
            "calls_remaining": self.calls_remaining,
            "routine_calls_remaining": self.routine_calls_remaining,
        }


@dataclass(frozen=True, slots=True)
class JourneySnapshot:
    """Coordinator output exposed to Home Assistant."""

    status: str
    checked_at: datetime
    next_journey: JourneyEvent | None
    budget: BudgetSnapshot
    error: str | None = None

    @property
    def data_healthy(self) -> bool:
        """Return whether the most recent review completed cleanly."""
        return self.error is None

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable representation."""
        return {
            "status": self.status,
            "checked_at": self.checked_at.isoformat(),
            "next_journey": (
                self.next_journey.as_dict() if self.next_journey is not None else None
            ),
            "budget": self.budget.as_dict(),
            "data_healthy": self.data_healthy,
            "error": self.error,
        }
