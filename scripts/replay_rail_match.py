"""Replay one saved TransportAPI board locally without Home Assistant writes.

Usage:
    python scripts/replay_rail_match.py board.json 2026-09-10T10:32:00+01:00 \
        CTR Chester "Avanti West Coast - Chester to London Euston" "London Euston"
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from custom_components.journey_guardian.models import JourneyEvent
from custom_components.journey_guardian.rail import (
    RailDataError,
    normalize_station_board,
)


def main(arguments: list[str]) -> int:
    """Print a sanitized match result for one locally supplied provider board."""
    if len(arguments) != 7:
        print(__doc__, file=sys.stderr)
        return 2
    board_path, departure_text, origin_code, origin_name, summary, destination = (
        arguments[1:]
    )
    departure = datetime.fromisoformat(departure_text)
    payload = json.loads(Path(board_path).read_text())
    journey = JourneyEvent(
        start=departure,
        end=None,
        summary=summary,
        location=origin_name,
        origin_code=origin_code,
        origin_name=origin_name,
        destination_confirmation=destination,
        decision_path="replay",
    )
    try:
        observation = normalize_station_board(
            payload,
            journey=journey,
            observed_at=departure,
            expected_station_code=origin_code,
        )
    except RailDataError as err:
        print(
            json.dumps(
                {
                    "outcome": "rejected",
                    "category": err.category,
                    "schedule_offset_minutes": err.schedule_offset_minutes,
                },
                indent=2,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "outcome": "matched",
                "scheduled_departure": observation.scheduled_departure.isoformat(),
                "predicted_departure": (
                    observation.predicted_departure.isoformat()
                    if observation.predicted_departure
                    else None
                ),
                "platform": observation.platform,
                "schedule_offset_minutes": observation.schedule_offset_minutes,
                "match_quality": observation.match_quality,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
