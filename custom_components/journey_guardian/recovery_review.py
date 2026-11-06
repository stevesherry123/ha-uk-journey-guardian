"""Explicit recovery review orchestration; no adoption or automatic searches."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from .connection import TransferAllowance
from .railinfo_recovery import RailinfoRecoveryResult
from .recovery import (
    RecoveryRequest,
    RecoveryRoute,
    RecoveryRouteError,
    _station,
    _utc,
    build_recovery_route,
)
from .recovery_context import RecoveryContext


@dataclass(frozen=True, slots=True)
class RecoverySearchPolicy:
    """Snapshot the exact limits and resolved preferences used for this search."""

    max_age: timedelta
    max_wait: timedelta
    max_duration: timedelta
    station_allowances: tuple[tuple[str, TransferAllowance], ...] = ()
    global_minutes: int = 10

    def __post_init__(self):
        if (
            not isinstance(self.max_age, timedelta)
            or self.max_age <= timedelta(0)
            or not isinstance(self.max_wait, timedelta)
            or self.max_wait < timedelta(0)
            or not isinstance(self.max_duration, timedelta)
            or self.max_duration <= timedelta(0)
            or type(self.global_minutes) is not int
            or not 0 <= self.global_minutes <= 1440
            or not isinstance(self.station_allowances, tuple)
            or len(self.station_allowances) > 64
        ):
            raise RecoveryRouteError("invalid_search_policy")
        seen = set()
        for code, allowance in self.station_allowances:
            _station(code)
            if (
                code in seen
                or not isinstance(allowance, TransferAllowance)
                or type(allowance.minutes) is not int
                or not 0 <= allowance.minutes <= 1440
                or allowance.source
                not in (
                    "connection_override",
                    "station_default",
                    "global_fallback",
                )
            ):
                raise RecoveryRouteError("invalid_transfer_preferences")
            seen.add(code)


@dataclass(frozen=True, slots=True)
class RecoveryReviewInputs:
    context: RecoveryContext
    policy: RecoverySearchPolicy


@dataclass(frozen=True, slots=True)
class RecoveryReview:
    """Options are advisory; affected IDs are a preview, never adopted state."""

    status: str
    context: RecoveryContext | None = None
    routes: tuple[RecoveryRoute, ...] = ()
    manual_fallback: bool = True


class RecoverySearch(Protocol):
    async def __call__(
        self,
        request: RecoveryRequest,
        *,
        max_age: timedelta,
        max_wait: timedelta,
        max_duration: timedelta,
        station_allowances: dict[str, TransferAllowance],
        global_minutes: int,
    ) -> RailinfoRecoveryResult:
        """Acquire one bounded complete-route response."""


class RecoveryReviewController:
    """One in-flight explicit review; recheck live context around acquisition.

    The inputs callback must rebuild context from the current calendar,
    confirmations and preferences without I/O. User origin confirmation must
    retain its original timestamp. Results are memory-only and expire on access.
    """

    def __init__(self, search: RecoverySearch, *, clock: Callable[[], datetime]):
        self._search = search
        self._clock = clock
        self._busy = False
        self._generation = 0
        self._inputs: RecoveryReviewInputs | None = None
        self._rebuild: Callable[[], RecoveryReviewInputs] | None = None
        self._review = RecoveryReview("not_requested")

    def invalidate(self) -> None:
        """Use on unload/revocation; in-flight completion cannot restore results."""
        self._generation += 1
        self._inputs = None
        self._rebuild = None
        self._review = RecoveryReview("context_changed")

    def current(self) -> RecoveryReview:
        """Never expose options after context changes or their validity expires."""
        if self._inputs is None or self._rebuild is None:
            return self._review
        try:
            fresh = self._rebuild()
            unchanged = fresh == self._inputs
        except ValueError:
            unchanged = False
        if not unchanged:
            self.invalidate()
            return self._review
        now = _utc(self._clock())
        if now >= self._inputs.context.valid_until:
            self._review = RecoveryReview("context_expired")
            return self._review
        if self._review.routes:
            routes = tuple(
                route
                for route in self._review.routes
                if route.checked_at <= now < route.valid_until
            )
            if not routes:
                self._review = RecoveryReview("options_expired", fresh.context)
            elif routes != self._review.routes:
                self._review = RecoveryReview(
                    "options_available", fresh.context, routes, False
                )
        return self._review

    async def async_review(
        self, rebuild: Callable[[], RecoveryReviewInputs]
    ) -> RecoveryReview:
        """Run only after an explicit command, never as a dashboard read effect."""
        if self._busy:
            return RecoveryReview("search_in_progress")
        self.invalidate()
        self._busy = True
        generation = self._generation
        try:
            try:
                inputs = rebuild()
                if not isinstance(inputs, RecoveryReviewInputs):
                    raise RecoveryRouteError("invalid_review_inputs")
                if _utc(self._clock()) >= inputs.context.valid_until:
                    raise RecoveryRouteError("context_expired")
                self._review = RecoveryReview("searching", inputs.context)
                policy = inputs.policy
                result = await self._search(
                    inputs.context.request,
                    max_age=policy.max_age,
                    max_wait=policy.max_wait,
                    max_duration=policy.max_duration,
                    station_allowances=dict(policy.station_allowances),
                    global_minutes=policy.global_minutes,
                )
            except ValueError, OSError, TimeoutError:
                if self._generation == generation:
                    self._review = RecoveryReview("review_unavailable")
                return self._review
            if self._generation != generation:
                return self._review
            self._inputs, self._rebuild = inputs, rebuild
            # Rebuild before examining the result, including failed searches.
            if self.current().status in ("context_changed", "context_expired"):
                return self._review
            if not isinstance(result, RailinfoRecoveryResult) or result.status not in (
                "options_available",
                "no_complete_route_in_response",
                "invalid_response",
                "stale_response",
                "provider_unavailable",
                "recovery_origin_not_current",
                "readiness_exceeds_wait_limit",
                "unsupported_service_day",
            ):
                self._review = RecoveryReview("invalid_search_response", inputs.context)
            elif result.status != "options_available":
                self._review = RecoveryReview(result.status, inputs.context)
            elif not 1 <= len(result.routes) <= 40 or any(
                not isinstance(route, RecoveryRoute)
                or route.request != inputs.context.request
                or route.checked_at > _utc(self._clock())
                for route in result.routes
            ):
                self._review = RecoveryReview("invalid_search_response", inputs.context)
            else:
                try:
                    now = _utc(self._clock())
                    routes = tuple(
                        build_recovery_route(
                            inputs.context.request,
                            route.legs,
                            now=now,
                            max_age=policy.max_age,
                            max_changes=1,
                            max_wait=policy.max_wait,
                            max_duration=policy.max_duration,
                            station_allowances=dict(policy.station_allowances),
                            global_minutes=policy.global_minutes,
                        )
                        for route in result.routes
                    )
                    if len({route.option_id for route in routes}) != len(routes):
                        raise RecoveryRouteError("ambiguous_options")
                except RecoveryRouteError:
                    self._review = RecoveryReview(
                        "options_need_refresh", inputs.context
                    )
                else:
                    self._review = RecoveryReview(
                        "options_available", inputs.context, routes, False
                    )
            return self.current()
        finally:
            self._busy = False
            if self._generation == generation and self._review.status == "searching":
                self._review = RecoveryReview("review_unavailable")
