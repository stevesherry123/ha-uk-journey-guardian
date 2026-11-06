"""Reviews cannot expose options after an asynchronous context change."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.journey_guardian.connection import TransferAllowance
from custom_components.journey_guardian.connection_evidence import (
    ServiceReference,
    StationTimeEvidence,
)
from custom_components.journey_guardian.railinfo_recovery import RailinfoRecoveryResult
from custom_components.journey_guardian.recovery import (
    RecoveryLeg,
    RecoveryRequest,
    RecoveryRouteError,
    build_recovery_route,
)
from custom_components.journey_guardian.recovery_context import RecoveryContext
from custom_components.journey_guardian.recovery_review import (
    RecoveryReviewController,
    RecoveryReviewInputs,
    RecoverySearchPolicy,
)

NOW = datetime(2026, 11, 6, 10, tzinfo=UTC)
REQUEST = RecoveryRequest("connected", "EXC", "SMP", "user_confirmed", NOW, NOW, True)
CONTEXT = RecoveryContext(
    REQUEST, ("a" * 64, "b" * 64), ("a" * 64, "b" * 64), NOW + timedelta(minutes=5)
)
POLICY = RecoverySearchPolicy(
    timedelta(minutes=5), timedelta(hours=2), timedelta(hours=8)
)
INPUTS = RecoveryReviewInputs(CONTEXT, POLICY)
SERVICE = ServiceReference("railinfo", "fictional-dated-service")
DEP, ARR = NOW + timedelta(minutes=10), NOW + timedelta(hours=1)
LEG = RecoveryLeg(
    "EXC",
    "SMP",
    DEP,
    ARR,
    StationTimeEvidence(SERVICE, "EXC", "departure", "predicted", DEP, NOW),
    StationTimeEvidence(SERVICE, "SMP", "arrival", "predicted", ARR, NOW),
    False,
)
ROUTE = build_recovery_route(
    REQUEST,
    (LEG,),
    now=NOW,
    max_age=POLICY.max_age,
    max_wait=POLICY.max_wait,
    max_duration=POLICY.max_duration,
    max_changes=1,
)
RESULT = RailinfoRecoveryResult("options_available", (ROUTE,))


def controller(result=RESULT):
    search = AsyncMock(return_value=result)
    clock = Mock(return_value=NOW)
    return RecoveryReviewController(search, clock=clock), search, clock


async def test_only_explicit_command_queries_and_preserves_original_scope():
    review, search, _ = controller()
    assert review.current().status == "not_requested"
    search.assert_not_called()
    result = await review.async_review(lambda: INPUTS)
    assert result.status == "options_available"
    assert result.context.affected_booking_ids == CONTEXT.affected_booking_ids
    assert result.routes[0].request.final_destination_code == "SMP"
    assert result.routes[0].ticket_acceptance == "unknown"
    assert result.manual_fallback is False
    review.current()
    search.assert_awaited_once()


@pytest.mark.parametrize("change", ["revoked", "booking_edit", "preferences", "unload"])
async def test_change_while_searching_discards_response(change):
    review, search, _ = controller()
    current = INPUTS

    async def acquire(*args, **kwargs):
        nonlocal current
        if change == "revoked":
            current = None
        elif change == "booking_edit":
            current = replace(INPUTS, context=replace(CONTEXT, affected_booking_ids=()))
        elif change == "preferences":
            current = replace(INPUTS, policy=replace(POLICY, global_minutes=15))
        else:
            review.invalidate()
        return RESULT

    def rebuild():
        if current is None:
            raise RecoveryRouteError("revoked")
        return current

    search.side_effect = acquire
    result = await review.async_review(rebuild)
    assert result.status == "context_changed"
    assert not result.routes
    assert result.manual_fallback is True


async def test_context_changed_after_search_disappears_on_read_without_query():
    review, search, _ = controller()
    rebuild = Mock(return_value=INPUTS)
    await review.async_review(rebuild)
    rebuild.side_effect = RecoveryRouteError("edited")
    assert review.current().status == "context_changed"
    assert not review.current().routes
    search.assert_awaited_once()


async def test_context_expiry_while_searching_discards_all_options():
    review, search, clock = controller()

    async def acquire(*args, **kwargs):
        clock.return_value = NOW + timedelta(minutes=5)
        return RESULT

    search.side_effect = acquire
    assert (await review.async_review(lambda: INPUTS)).status == "context_expired"


async def test_route_expiry_on_read_does_not_trigger_background_query():
    inputs = replace(
        INPUTS, context=replace(CONTEXT, valid_until=NOW + timedelta(hours=1))
    )
    review, search, clock = controller()
    await review.async_review(lambda: inputs)
    clock.return_value = NOW + timedelta(minutes=5)
    result = review.current()
    assert result.status == "options_expired"
    assert result.manual_fallback is True
    assert not result.routes
    search.assert_awaited_once()


async def test_parallel_command_does_not_start_another_search():
    review, search, _ = controller()
    started, release = asyncio.Event(), asyncio.Event()

    async def acquire(*args, **kwargs):
        started.set()
        await release.wait()
        return RESULT

    search.side_effect = acquire
    first = asyncio.create_task(review.async_review(lambda: INPUTS))
    await started.wait()
    try:
        second = await review.async_review(lambda: INPUTS)
        assert second.status == "search_in_progress"
        search.assert_awaited_once()
    finally:
        release.set()
        await first


@pytest.mark.parametrize(
    "status",
    [
        "provider_unavailable",
        "no_complete_route_in_response",
        "stale_response",
        "unsupported_service_day",
    ],
)
async def test_unavailable_search_keeps_manual_fallback_and_original_scope(status):
    review, _, _ = controller(RailinfoRecoveryResult(status))
    result = await review.async_review(lambda: INPUTS)
    assert result.status == status
    assert result.context == CONTEXT
    assert result.manual_fallback is True
    assert not result.routes


async def test_wrong_journey_response_never_becomes_selectable():
    wrong = replace(ROUTE, request=replace(REQUEST, journey_id="unrelated-return"))
    review, _, _ = controller(RailinfoRecoveryResult("options_available", (wrong,)))
    assert (
        await review.async_review(lambda: INPUTS)
    ).status == "invalid_search_response"


async def test_old_predictions_are_revalidated_at_completion():
    expired = replace(
        ROUTE,
        legs=(
            replace(
                LEG,
                arrival=replace(LEG.arrival, observed_at=NOW - timedelta(minutes=6)),
            ),
        ),
    )
    review, _, _ = controller(RailinfoRecoveryResult("options_available", (expired,)))
    result = await review.async_review(lambda: INPUTS)
    assert result.status == "options_need_refresh"
    assert not result.routes


async def test_failed_search_releases_busy_state_and_does_not_replay_old_options():
    review, search, _ = controller()
    await review.async_review(lambda: INPUTS)
    search.side_effect = TimeoutError
    assert (await review.async_review(lambda: INPUTS)).status == "review_unavailable"
    assert not review.current().routes
    search.side_effect = None
    assert (await review.async_review(lambda: INPUTS)).status == "options_available"


@pytest.mark.parametrize(
    "changes",
    [
        {"max_age": timedelta(0)},
        {"max_wait": timedelta(minutes=-1)},
        {"global_minutes": True},
        {"station_allowances": (("bad", TransferAllowance(10, "station_default")),)},
        {"station_allowances": (("EXJ", TransferAllowance(-1, "station_default")),)},
    ],
)
def test_invalid_policy_is_rejected_before_any_search(changes):
    with pytest.raises(ValueError):
        replace(POLICY, **changes)


async def test_cancelled_command_releases_busy_state_and_clears_search_status():
    review, search, _ = controller()
    started = asyncio.Event()

    async def acquire(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    search.side_effect = acquire
    task = asyncio.create_task(review.async_review(lambda: INPUTS))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert review.current().status == "review_unavailable"
    search.side_effect = None
    assert (await review.async_review(lambda: INPUTS)).status == "options_available"


async def test_unknown_provider_status_is_not_exposed_as_user_guidance():
    review, _, _ = controller(RailinfoRecoveryResult("unexpected_private_detail"))
    assert (
        await review.async_review(lambda: INPUTS)
    ).status == "invalid_search_response"
