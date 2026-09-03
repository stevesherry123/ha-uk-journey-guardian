"""Tests for quota-safe provider acquisition and freshness handling."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.journey_guardian.provider_broker import (
    ERROR_INVALID_REQUEST,
    ERROR_MALFORMED_RESPONSE,
    ERROR_PROVIDER_UNAVAILABLE,
    ERROR_QUOTA_EXHAUSTED,
    ProviderBrokerError,
    ProviderRequest,
    ProviderRequestBroker,
)

NOW = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)
REQUEST = ProviderRequest(
    provider="simulated_rail",
    operation="departures",
    parameters={"origin": "Example Central", "window": 30},
)
PAYLOAD = {"services": [{"scheduled": "10:00", "status": "on_time"}]}


def _budget(*reservations: bool) -> Mock:
    budget = Mock()
    budget.async_reserve_call = AsyncMock(side_effect=reservations or (True,))
    return budget


async def test_fresh_cache_hit_uses_one_call_and_detaches_payload(hass) -> None:
    """Repeated consumers share cached data without another quota reservation."""
    budget = _budget(True)
    fetcher = AsyncMock(return_value=PAYLOAD)
    broker = ProviderRequestBroker(hass, budget)

    with patch(
        "custom_components.journey_guardian.provider_broker.dt_util.utcnow",
        return_value=NOW,
    ):
        acquired = await broker.async_request(REQUEST, fetcher)
        acquired.payload["services"][0]["status"] = "changed by caller"
        cached = await broker.async_request(REQUEST, fetcher)

    assert acquired.source == "provider"
    assert cached.source == "cache"
    assert cached.freshness == "current"
    assert cached.healthy
    assert cached.payload == PAYLOAD
    budget.async_reserve_call.assert_awaited_once_with(urgent=False)
    fetcher.assert_awaited_once_with()


async def test_concurrent_requests_share_one_inflight_fetch(hass) -> None:
    """Concurrent consumers cannot multiply provider calls or quota use."""
    budget = _budget(True)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fetcher():
        started.set()
        await release.wait()
        return PAYLOAD

    broker = ProviderRequestBroker(hass, budget)
    with patch(
        "custom_components.journey_guardian.provider_broker.dt_util.utcnow",
        return_value=NOW,
    ):
        first = asyncio.create_task(broker.async_request(REQUEST, fetcher))
        await started.wait()
        second = asyncio.create_task(broker.async_request(REQUEST, fetcher))
        await asyncio.sleep(0)
        release.set()
        results = await asyncio.gather(first, second)

    assert results[0] is not results[1]
    results[0].payload["services"][0]["status"] = "changed by first caller"
    assert results[1].payload == PAYLOAD
    budget.async_reserve_call.assert_awaited_once_with(urgent=False)


async def test_shutdown_cancels_inflight_provider_work(hass) -> None:
    """Config-entry unload cannot leave an orphaned provider request."""
    budget = _budget(True)
    started = asyncio.Event()

    async def fetcher():
        started.set()
        await asyncio.Event().wait()

    broker = ProviderRequestBroker(hass, budget)
    with patch(
        "custom_components.journey_guardian.provider_broker.dt_util.utcnow",
        return_value=NOW,
    ):
        request = asyncio.create_task(broker.async_request(REQUEST, fetcher))
        await started.wait()
        broker.shutdown()
        with pytest.raises(asyncio.CancelledError):
            await request

    assert not broker._inflight


async def test_urgent_request_can_use_reserved_allowance(hass) -> None:
    """Urgent intent reaches the one durable quota authority explicitly."""
    budget = _budget(True)
    broker = ProviderRequestBroker(hass, budget)

    with patch(
        "custom_components.journey_guardian.provider_broker.dt_util.utcnow",
        return_value=NOW,
    ):
        await broker.async_request(
            REQUEST, AsyncMock(return_value=PAYLOAD), urgent=True
        )

    budget.async_reserve_call.assert_awaited_once_with(urgent=True)


async def test_urgent_waiter_retries_routine_quota_denial(hass) -> None:
    """A joined urgent check can still use reserve after routine denial."""
    calls: list[bool] = []
    routine_reserving = asyncio.Event()
    release_routine = asyncio.Event()

    async def reserve(*, urgent: bool) -> bool:
        calls.append(urgent)
        if len(calls) == 1:
            return True
        if len(calls) == 2:
            routine_reserving.set()
            await release_routine.wait()
            return False
        return urgent

    budget = Mock()
    budget.async_reserve_call = AsyncMock(side_effect=reserve)
    fetcher = AsyncMock(side_effect=(PAYLOAD, {"services": [{"status": "updated"}]}))
    broker = ProviderRequestBroker(hass, budget)
    now = NOW

    with patch(
        "custom_components.journey_guardian.provider_broker.dt_util.utcnow",
        side_effect=lambda: now,
    ):
        await broker.async_request(REQUEST, fetcher)
        now = NOW + timedelta(seconds=31)
        routine = asyncio.create_task(broker.async_request(REQUEST, fetcher))
        await routine_reserving.wait()
        urgent = asyncio.create_task(
            broker.async_request(REQUEST, fetcher, urgent=True)
        )
        await asyncio.sleep(0)
        release_routine.set()
        routine_result, urgent_result = await asyncio.gather(routine, urgent)

    assert routine_result.freshness == "stale"
    assert routine_result.error_category == ERROR_QUOTA_EXHAUSTED
    assert urgent_result.source == "provider"
    assert urgent_result.payload == {"services": [{"status": "updated"}]}
    assert calls == [False, False, True]


async def test_quota_denial_prevents_provider_call(hass) -> None:
    """A denied reservation makes a live fetch structurally impossible."""
    budget = _budget(False)
    fetcher = AsyncMock(return_value=PAYLOAD)
    broker = ProviderRequestBroker(hass, budget)

    with (
        patch(
            "custom_components.journey_guardian.provider_broker.dt_util.utcnow",
            return_value=NOW,
        ),
        pytest.raises(ProviderBrokerError) as raised,
    ):
        await broker.async_request(REQUEST, fetcher)

    assert raised.value.category == ERROR_QUOTA_EXHAUSTED
    assert str(raised.value) == ERROR_QUOTA_EXHAUSTED
    fetcher.assert_not_awaited()


async def test_failed_refresh_returns_explicitly_stale_cache(hass) -> None:
    """A provider outage cannot make old data look current or healthy."""
    budget = _budget(True, True)
    broker = ProviderRequestBroker(hass, budget)
    fetcher = AsyncMock(
        side_effect=(PAYLOAD, RuntimeError("private provider request details"))
    )

    with patch(
        "custom_components.journey_guardian.provider_broker.dt_util.utcnow",
        side_effect=(
            NOW,
            NOW,
            NOW + timedelta(seconds=31),
            NOW + timedelta(seconds=31),
        ),
    ):
        current = await broker.async_request(REQUEST, fetcher)
        stale = await broker.async_request(REQUEST, fetcher)

    assert current.healthy
    assert stale.payload == PAYLOAD
    assert stale.freshness == "stale"
    assert stale.source == "cache"
    assert stale.age_seconds == 31
    assert stale.error_category == ERROR_PROVIDER_UNAVAILABLE
    assert not stale.healthy
    assert "private" not in str(stale.metadata()).casefold()


async def test_malformed_response_is_sanitized_and_not_cached(hass) -> None:
    """Unsupported provider shapes fail closed with a stable category."""
    budget = _budget(True, True)
    broker = ProviderRequestBroker(hass, budget)
    malformed = AsyncMock(return_value=["private unsupported record"])

    with (
        patch(
            "custom_components.journey_guardian.provider_broker.dt_util.utcnow",
            return_value=NOW,
        ),
        pytest.raises(ProviderBrokerError) as first,
    ):
        await broker.async_request(REQUEST, malformed)

    assert first.value.category == ERROR_MALFORMED_RESPONSE
    assert "private" not in str(first.value).casefold()

    valid = AsyncMock(return_value=PAYLOAD)
    with patch(
        "custom_components.journey_guardian.provider_broker.dt_util.utcnow",
        return_value=NOW,
    ):
        result = await broker.async_request(REQUEST, valid)

    assert result.source == "provider"
    valid.assert_awaited_once_with()


async def test_expired_stale_data_is_never_used_as_fallback(hass) -> None:
    """Data older than the stale limit is discarded during an outage."""
    budget = _budget(True, True)
    broker = ProviderRequestBroker(
        hass,
        budget,
        cache_ttl=timedelta(seconds=30),
        stale_ttl=timedelta(minutes=5),
    )
    fetcher = AsyncMock(side_effect=(PAYLOAD, RuntimeError("provider down")))

    with patch(
        "custom_components.journey_guardian.provider_broker.dt_util.utcnow",
        side_effect=(NOW, NOW, NOW + timedelta(minutes=6), NOW + timedelta(minutes=6)),
    ):
        await broker.async_request(REQUEST, fetcher)
        with pytest.raises(ProviderBrokerError) as raised:
            await broker.async_request(REQUEST, fetcher)

    assert raised.value.category == ERROR_PROVIDER_UNAVAILABLE


def test_request_parameters_are_replaced_by_private_hashes() -> None:
    """Request identities used by caches cannot reveal locations."""
    fingerprint = REQUEST.fingerprint()

    assert len(fingerprint) == 64
    assert "example" not in fingerprint.casefold()
    assert "central" not in fingerprint.casefold()


def test_invalid_request_identity_fails_before_quota_or_provider_work() -> None:
    """Malformed request keys are rejected before entering acquisition."""
    request = ProviderRequest(
        provider="simulated_rail",
        operation="departures",
        parameters={"unsupported": object()},
    )

    with pytest.raises(ProviderBrokerError) as raised:
        request.fingerprint()

    assert raised.value.category == ERROR_INVALID_REQUEST


def test_empty_request_identity_is_rejected() -> None:
    """Provider and operation names are mandatory parts of request identity."""
    request = ProviderRequest(provider=" ", operation="departures", parameters={})

    with pytest.raises(ProviderBrokerError) as raised:
        request.fingerprint()

    assert raised.value.category == ERROR_INVALID_REQUEST
