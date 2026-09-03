"""Tests for offline rail-board normalization and journey matching."""

from datetime import UTC, datetime

import pytest

from custom_components.journey_guardian.models import JourneyEvent
from custom_components.journey_guardian.rail import (
    RailDataError,
    normalize_station_board,
)

OBSERVED = datetime(2026, 9, 3, 8, 30, tzinfo=UTC)


def _journey(start: datetime | None = None) -> JourneyEvent:
    return JourneyEvent(
        start=start or datetime(2026, 9, 3, 10, 10, tzinfo=UTC),
        end=None,
        summary="Example Rail - Example Central to Sample Harbour",
        location="Example Central",
        origin_code="EXC",
        origin_name="Example Central",
        destination_confirmation="Sample Harbour",
        decision_path="calendar_route",
    )


def _service(**changes):
    service = {
        "mode": "train",
        "service": "service-one",
        "train_uid": "uid-one",
        "operator_name": "Example Rail",
        "aimed_departure_time": "10:10",
        "expected_departure_time": "10:10",
        "destination_name": "Sample Harbour",
        "platform": "4",
        "status": "ON TIME",
    }
    service.update(changes)
    return service


def _board(*services, date: str = "2026-09-03", station_code: str = "EXC"):
    return {
        "date": date,
        "station_code": station_code,
        "departures": {"all": list(services or (_service(),))},
    }


def _normalize(payload, journey: JourneyEvent | None = None):
    return normalize_station_board(
        payload,
        journey=journey or _journey(),
        observed_at=OBSERVED,
        expected_station_code="EXC",
    )


def test_direct_service_is_normalized_without_delay() -> None:
    """A direct on-time service becomes a provider-neutral observation."""
    observation = _normalize(_board())

    assert observation.scheduled_departure == _journey().start
    assert observation.predicted_departure is None
    assert observation.delay_minutes == 0
    assert not observation.cancelled
    assert observation.platform == "4"
    assert len(observation.service_identity or "") == 16
    assert observation.match_quality == "unique_best"


def test_delayed_service_preserves_scheduled_and_predicted_times() -> None:
    """Provider prediction does not overwrite the timetable time."""
    observation = _normalize(
        _board(_service(expected_departure_time="10:27", status="LATE"))
    )

    assert observation.scheduled_departure.hour == 10
    assert observation.scheduled_departure.minute == 10
    assert observation.predicted_departure is not None
    assert observation.predicted_departure.minute == 27
    assert observation.delay_minutes == 17


def test_cancelled_service_is_explicit() -> None:
    """Cancellation is derived without inventing a predicted time."""
    observation = _normalize(
        _board(_service(expected_departure_time="Cancelled", status="CANCELLED"))
    )

    assert observation.cancelled
    assert observation.scenario == "cancelled"
    assert observation.predicted_departure is None


def test_duplicate_correction_uses_latest_record_with_stable_identity() -> None:
    """A later correction may revise prediction/platform, not service identity."""
    observation = _normalize(
        _board(
            _service(expected_departure_time="10:15", platform="4"),
            _service(expected_departure_time="10:20", platform="6"),
        )
    )
    baseline = _normalize(_board())

    assert observation.predicted_departure is not None
    assert observation.predicted_departure.minute == 20
    assert observation.platform == "6"
    assert observation.service_identity == baseline.service_identity


def test_malformed_records_are_ignored_when_one_valid_service_remains() -> None:
    """One bad list member cannot poison a valid board."""
    observation = _normalize(_board("invalid", {"mode": "bus"}, _service()))

    assert observation.scheduled_departure == _journey().start


def test_ambiguous_equal_services_are_rejected() -> None:
    """Equal evidence for two identities requires more information."""
    with pytest.raises(RailDataError, match="rail_service_ambiguous"):
        _normalize(
            _board(
                _service(train_uid="uid-one"),
                _service(train_uid="uid-two", service="service-two"),
            )
        )


def test_operator_evidence_breaks_an_equal_time_tie() -> None:
    """Only actual operator evidence may increase match confidence."""
    observation = _normalize(
        _board(
            _service(train_uid="uid-correct"),
            _service(
                train_uid="uid-unknown",
                service="service-unknown",
                operator_name="",
            ),
        )
    )

    expected = _normalize(_board(_service(train_uid="uid-correct")))
    assert observation.service_identity == expected.service_identity


def test_conflicting_duplicate_identity_is_rejected() -> None:
    """A provider identity cannot describe two different scheduled services."""
    with pytest.raises(RailDataError, match="rail_record_conflict"):
        _normalize(
            _board(
                _service(),
                _service(aimed_departure_time="10:11"),
            )
        )


def test_overnight_board_date_aligns_to_next_calendar_day() -> None:
    """An after-midnight journey can match a late-night board service date."""
    journey = _journey(datetime(2026, 9, 4, 0, 5, tzinfo=UTC))
    observation = _normalize(
        _board(
            _service(
                aimed_departure_time="00:05",
                expected_departure_time="00:05",
            )
        ),
        journey,
    )

    assert observation.scheduled_departure == journey.start


def test_station_mismatch_and_malformed_payload_use_stable_errors() -> None:
    """Unsafe responses fail with public categories, never raw content."""
    with pytest.raises(RailDataError, match="rail_station_mismatch"):
        _normalize(_board(station_code="WRG"))
    with pytest.raises(RailDataError, match="rail_response_malformed"):
        _normalize({"station_code": "EXC", "date": "not-a-date"})
