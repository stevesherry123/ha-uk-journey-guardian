"""Quota-safe provider acquisition with caching and request deduplication."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .budget import TransportAPIBudget

_LOGGER = logging.getLogger(__name__)

ProviderPayload = dict[str, Any]
ProviderFetcher = Callable[[], Awaitable[Mapping[str, Any]]]
ProviderFreshness = Literal["current", "stale"]
ProviderSource = Literal["provider", "cache"]

ERROR_QUOTA_EXHAUSTED = "quota_exhausted"
ERROR_PROVIDER_UNAVAILABLE = "provider_unavailable"
ERROR_MALFORMED_RESPONSE = "malformed_response"
ERROR_INVALID_REQUEST = "invalid_request"


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """Provider-neutral request identity used only to derive a private hash."""

    provider: str
    operation: str
    parameters: Mapping[str, Any]
    quota_controlled: bool = True

    def fingerprint(self) -> str:
        """Return a stable hash without retaining request parameters."""
        if (
            not isinstance(self.provider, str)
            or not self.provider.strip()
            or not isinstance(self.operation, str)
            or not self.operation.strip()
        ):
            raise ProviderBrokerError(ERROR_INVALID_REQUEST)
        try:
            _validate_json_value(self.parameters)
            canonical = json.dumps(
                {
                    "provider": self.provider,
                    "operation": self.operation,
                    "parameters": dict(self.parameters),
                    "quota_controlled": self.quota_controlled,
                },
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError):
            raise ProviderBrokerError(ERROR_INVALID_REQUEST) from None
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ProviderResult:
    """Validated provider data plus privacy-safe acquisition metadata."""

    payload: ProviderPayload
    observed_at: datetime
    fresh_until: datetime
    freshness: ProviderFreshness
    source: ProviderSource
    age_seconds: int
    error_category: str | None = None

    @property
    def healthy(self) -> bool:
        """Return whether current provider data was acquired successfully."""
        return self.freshness == "current" and self.error_category is None

    def metadata(self) -> dict[str, Any]:
        """Return metadata safe for diagnostics; never include raw payload."""
        return {
            "observed_at": self.observed_at.isoformat(),
            "fresh_until": self.fresh_until.isoformat(),
            "freshness": self.freshness,
            "source": self.source,
            "age_seconds": self.age_seconds,
            "error_category": self.error_category,
            "healthy": self.healthy,
        }


class ProviderBrokerError(Exception):
    """Sanitized provider acquisition failure."""

    def __init__(self, category: str) -> None:
        """Initialize with a stable, privacy-safe category only."""
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    payload: ProviderPayload
    observed_at: datetime
    fresh_until: datetime
    stale_until: datetime


@dataclass(slots=True)
class _PendingRequest:
    urgent: bool
    quota_controlled: bool
    task: asyncio.Task[ProviderResult] | None = None
    reserved_as_urgent: bool = False


class ProviderRequestBroker:
    """Own provider cache, concurrency, validation, and quota reservations."""

    def __init__(
        self,
        hass: HomeAssistant,
        budget: TransportAPIBudget,
        *,
        cache_ttl: timedelta = timedelta(seconds=30),
        stale_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        """Initialize one shared broker for a config entry."""
        if cache_ttl <= timedelta(0):
            raise ValueError("cache_ttl must be positive")
        if stale_ttl < cache_ttl:
            raise ValueError("stale_ttl must be at least cache_ttl")
        self._hass = hass
        self._budget = budget
        self._cache_ttl = cache_ttl
        self._stale_ttl = stale_ttl
        self._cache: dict[str, _CacheEntry] = {}
        self._inflight: dict[str, _PendingRequest] = {}
        self._lock = asyncio.Lock()
        self._last_request: dict[str, Any] | None = None

    def diagnostics(self) -> dict[str, Any] | None:
        """Return privacy-safe metadata for the most recent provider request."""
        return dict(self._last_request) if self._last_request else None

    async def async_request(
        self,
        request: ProviderRequest,
        fetcher: ProviderFetcher,
        *,
        urgent: bool = False,
    ) -> ProviderResult:
        """Return current or explicitly stale data through the quota guard."""
        fingerprint = request.fingerprint()
        now = dt_util.utcnow()
        self._last_request = {
            "provider": request.provider,
            "operation": request.operation,
            "request_fingerprint": fingerprint[:16],
            "urgent": urgent,
            "requested_at": now.isoformat(),
        }
        _LOGGER.debug(
            "Provider request operation=%s fingerprint=%s urgent=%s",
            request.operation,
            fingerprint[:16],
            urgent,
        )
        async with self._lock:
            cached = self._usable_cache(fingerprint, now)
            if cached is not None and now < cached.fresh_until:
                return _result_from_cache(cached, now, freshness="current")

            pending = self._inflight.get(fingerprint)
            if pending is None:
                pending = _PendingRequest(
                    urgent=urgent, quota_controlled=request.quota_controlled
                )
                task = self._hass.async_create_task(
                    self._async_acquire(fingerprint, fetcher, pending),
                    "journey_guardian provider request",
                )
                pending.task = task
                self._inflight[fingerprint] = pending
                task.add_done_callback(
                    lambda completed, key=fingerprint: self._discard_inflight(
                        key, completed
                    )
                )
            elif urgent:
                pending.urgent = True
            task = pending.task

        if task is None:  # Defensive: a pending request always owns a task.
            raise ProviderBrokerError(ERROR_PROVIDER_UNAVAILABLE)
        try:
            result = await asyncio.shield(task)
            if (
                urgent
                and result.error_category == ERROR_QUOTA_EXHAUSTED
                and not pending.reserved_as_urgent
            ):
                await asyncio.sleep(0)
                return await self.async_request(request, fetcher, urgent=True)
            return _detach_result(result)
        except ProviderBrokerError as err:
            if (
                urgent
                and err.category == ERROR_QUOTA_EXHAUSTED
                and not pending.reserved_as_urgent
            ):
                await asyncio.sleep(0)
                return await self.async_request(request, fetcher, urgent=True)
            raise

    def clear(self) -> None:
        """Discard short-lived provider data without affecting quota state."""
        self._cache.clear()

    def shutdown(self) -> None:
        """Cancel provider work when the owning config entry unloads."""
        for pending in self._inflight.values():
            if pending.task is not None:
                pending.task.cancel()
        self._inflight.clear()
        self._cache.clear()

    def _usable_cache(
        self, fingerprint: str, now: datetime
    ) -> _CacheEntry | None:
        cached = self._cache.get(fingerprint)
        if cached is not None and now <= cached.stale_until:
            return cached
        self._cache.pop(fingerprint, None)
        return None

    async def _async_acquire(
        self,
        fingerprint: str,
        fetcher: ProviderFetcher,
        pending: _PendingRequest,
    ) -> ProviderResult:
        """Perform one shared provider attempt for all concurrent waiters."""
        await asyncio.sleep(0)
        pending.reserved_as_urgent = pending.urgent
        if pending.quota_controlled:
            reserved = await self._budget.async_reserve_call(
                urgent=pending.reserved_as_urgent
            )
            if not reserved:
                return self._stale_or_raise(
                    fingerprint, ERROR_QUOTA_EXHAUSTED, dt_util.utcnow()
                )

        try:
            raw_payload = await fetcher()
        except ProviderBrokerError as err:
            if err.category == ERROR_QUOTA_EXHAUSTED and pending.quota_controlled:
                await self._budget.async_mark_exhausted()
            return self._stale_or_raise(
                fingerprint, err.category, dt_util.utcnow()
            )
        except Exception:  # Provider/library exceptions are untrusted.
            return self._stale_or_raise(
                fingerprint, ERROR_PROVIDER_UNAVAILABLE, dt_util.utcnow()
            )

        try:
            payload = _normalize_payload(raw_payload)
        except (TypeError, ValueError):
            return self._stale_or_raise(
                fingerprint, ERROR_MALFORMED_RESPONSE, dt_util.utcnow()
            )

        observed_at = dt_util.utcnow()
        cached = _CacheEntry(
            payload=payload,
            observed_at=observed_at,
            fresh_until=observed_at + self._cache_ttl,
            stale_until=observed_at + self._stale_ttl,
        )
        self._cache[fingerprint] = cached
        return _result_from_provider(cached)

    def _stale_or_raise(
        self, fingerprint: str, category: str, now: datetime
    ) -> ProviderResult:
        cached = self._usable_cache(fingerprint, now)
        if cached is not None:
            return _result_from_cache(
                cached,
                now,
                freshness="stale",
                error_category=category,
            )
        raise ProviderBrokerError(category) from None

    def _discard_inflight(
        self, fingerprint: str, completed: asyncio.Task[ProviderResult]
    ) -> None:
        pending = self._inflight.get(fingerprint)
        if pending is not None and pending.task is completed:
            self._inflight.pop(fingerprint, None)


def _normalize_payload(payload: Mapping[str, Any]) -> ProviderPayload:
    """Copy provider JSON and reject unsupported or non-finite values."""
    if not isinstance(payload, Mapping):
        raise TypeError("provider payload must be an object")
    _validate_json_value(payload)
    encoded = json.dumps(
        dict(payload),
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    normalized = json.loads(encoded)
    if not isinstance(normalized, dict):
        raise TypeError("provider payload must be an object")
    return normalized


def _validate_json_value(value: Any) -> None:
    """Reject values which cannot have originated from a JSON provider body."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("provider payload contains a non-finite number")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("provider payload keys must be strings")
            _validate_json_value(item)
        return
    raise TypeError("provider payload contains an unsupported value")


def _result_from_provider(cached: _CacheEntry) -> ProviderResult:
    return ProviderResult(
        payload=_copy_payload(cached.payload),
        observed_at=cached.observed_at,
        fresh_until=cached.fresh_until,
        freshness="current",
        source="provider",
        age_seconds=0,
    )


def _result_from_cache(
    cached: _CacheEntry,
    now: datetime,
    *,
    freshness: ProviderFreshness,
    error_category: str | None = None,
) -> ProviderResult:
    return ProviderResult(
        payload=_copy_payload(cached.payload),
        observed_at=cached.observed_at,
        fresh_until=cached.fresh_until,
        freshness=freshness,
        source="cache",
        age_seconds=max(0, int((now - cached.observed_at).total_seconds())),
        error_category=error_category,
    )


def _copy_payload(payload: ProviderPayload) -> ProviderPayload:
    """Return a detached JSON copy so callers cannot mutate cached state."""
    copied = json.loads(json.dumps(payload, allow_nan=False))
    if not isinstance(copied, dict):
        raise TypeError("provider payload must be an object")
    return copied


def _detach_result(result: ProviderResult) -> ProviderResult:
    """Give each concurrent consumer an independent payload object."""
    return ProviderResult(
        payload=_copy_payload(result.payload),
        observed_at=result.observed_at,
        fresh_until=result.fresh_until,
        freshness=result.freshness,
        source=result.source,
        age_seconds=result.age_seconds,
        error_category=result.error_category,
    )
