"""Tests for evidence-led travel-day review."""

from datetime import date
from unittest.mock import AsyncMock, Mock, patch

from custom_components.journey_guardian.end_of_day import EndOfDayReview


def _record(**overrides):
    record = {
        "checked_at": "2026-09-28T19:03:00+01:00",
        "journey_fingerprint": "safe-fingerprint",
        "origin_code": "EUS",
        "destination_code": "CTR",
        "outcome": "success",
        "status": "active",
    }
    record.update(overrides)
    return record


async def _review(hass, records):
    history = Mock()
    history.records.return_value = records
    reviewer = EndOfDayReview(hass, history)
    reviewer._store.async_save = AsyncMock()
    with patch(
        "custom_components.journey_guardian.end_of_day."
        "persistent_notification.async_create"
    ) as notify:
        result = await reviewer.async_review_date(date(2026, 9, 28))
    return reviewer, result, notify


async def test_successful_departure_check_is_not_completion_evidence(hass) -> None:
    """A matched active service cannot be reported as an on-time arrival."""
    reviewer, result, notify = await _review(hass, [_record()])

    assert result["unresolved_count"] == 1
    assert result["delayed_count"] == 0
    assert result["attention_required"] is True
    assert result["journeys"][0]["classification"] == "insufficient_evidence"
    assert result["journeys"][0]["reason"] == "actual_arrival_missing"
    notify.assert_called_once()
    assert reviewer.diagnostics() == result


async def test_confirmed_on_time_arrival_is_silent(hass) -> None:
    """A fully evidenced normal journey is retained without notification noise."""
    _reviewer, result, notify = await _review(
        hass,
        [
            _record(
                completion_status="completed",
                scheduled_arrival="2026-09-28T21:10:00+01:00",
                actual_arrival="2026-09-28T21:10:00+01:00",
                arrival_delay_minutes=0,
            )
        ],
    )

    assert result["unresolved_count"] == 0
    assert result["attention_required"] is False
    assert result["notification_sent"] is False
    assert result["journeys"][0]["classification"] == "not_delayed"
    notify.assert_not_called()


async def test_confirmed_arrival_delay_is_exposed_but_not_declared_eligible(
    hass,
) -> None:
    """Delay evidence is actionable while policy eligibility remains conservative."""
    _reviewer, result, notify = await _review(
        hass,
        [
            _record(
                completion_status="completed",
                scheduled_arrival="2026-09-28T21:10:00+01:00",
                actual_arrival="2026-09-28T21:28:00+01:00",
                arrival_delay_minutes=18,
                evidence_source="railinfo",
            )
        ],
    )

    assert result["delayed_count"] == 1
    assert result["journeys"][0]["classification"] == "potential_claim"
    assert result["journeys"][0]["claim_eligibility"] == "potentially_eligible"
    assert result["potential_claim_count"] == 1
    notify.assert_called_once()


async def test_confirmed_small_delay_is_recorded_without_claim_alert(hass) -> None:
    """A destination delay below the configured threshold remains silent."""
    _reviewer, result, notify = await _review(
        hass,
        [
            _record(
                completion_status="completed",
                scheduled_arrival="2026-09-28T21:10:00+01:00",
                actual_arrival="2026-09-28T21:17:00+01:00",
                arrival_delay_minutes=7,
            )
        ],
    )

    assert result["delayed_count"] == 1
    assert result["potential_claim_count"] == 0
    assert result["attention_required"] is False
    assert result["journeys"][0]["classification"] == "delay_below_threshold"
    notify.assert_not_called()


async def test_review_groups_each_leg_of_split_journey(hass) -> None:
    """An intentional break remains two independently reviewed legs."""
    _reviewer, result, _notify = await _review(
        hass,
        [
            _record(journey_fingerprint="leg-one", destination_code="CRE"),
            _record(
                checked_at="2026-09-28T06:32:00+01:00",
                journey_fingerprint="leg-two",
                origin_code="CRE",
                destination_code="EUS",
            ),
        ],
    )

    assert result["journey_count"] == 2
    assert result["unresolved_count"] == 2
