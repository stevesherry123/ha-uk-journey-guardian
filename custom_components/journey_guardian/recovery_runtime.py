"""Home Assistant entry point for a user-confirmed recovery review."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from functools import partial

from homeassistant.util import dt as dt_util

from .connection import TransferAllowance
from .connection_preferences import station_key
from .provider_broker import ProviderBrokerError
from .recovery_context import build_user_recovery_context
from .recovery_review import (
    RecoveryReviewController,
    RecoveryReviewInputs,
    RecoverySearchPolicy,
)

MAX_AGE = timedelta(minutes=5)
MAX_CALENDAR_AGE = timedelta(minutes=15)


class RecoveryRuntime:
    """Resolve stations and rebuild current inputs around an explicit search."""

    def __init__(self, coordinator, client):
        self.coordinator = coordinator
        self.client = client
        self.review = RecoveryReviewController(
            client.async_recovery_search, clock=dt_util.utcnow
        )
        self._busy = False
        self._stopped = False
        self._generation = 0
        self._preflight_failed = False
        self._selection_status = None

    def invalidate(self):
        self._generation += 1
        self._selection_status = None
        self.review.invalidate()

    def stop(self):
        self._stopped = True
        self.invalidate()

    def _bookings(self, now):
        coordinator = self.coordinator
        snapshot = coordinator.data
        reviewed_at = coordinator.last_successful_calendar_review_at
        if (
            self._stopped
            or snapshot is None
            or snapshot.simulation_active
            or snapshot.error
            or coordinator.last_calendar_source_refresh_error
            or reviewed_at is None
            or not timedelta(0) <= now - reviewed_at <= MAX_CALENDAR_AGE
            or coordinator.connection_confirmations.persistence_error
        ):
            raise ValueError("current_calendar_required")
        return coordinator.travel_plan.recovery_bookings(now)

    async def async_search(self, *, affected_booking_id, final_booking_id, origin):
        if self._busy:
            return "search_in_progress"
        self._busy = True
        self._preflight_failed = False
        self.invalidate()
        try:
            return await self._async_search(
                affected_booking_id, final_booking_id, origin
            )
        except ValueError, OSError, TimeoutError, ProviderBrokerError:
            return "review_unavailable"
        finally:
            self._busy = False
            if not self._stopped:
                self.coordinator.async_update_listeners()

    async def _async_search(self, affected_id, final_id, origin):
        coordinator = self.coordinator
        generation = self._generation
        confirmed_at = dt_util.utcnow()
        bookings = self._bookings(confirmed_at)
        by_id = {booking.booking_id: booking for booking in bookings}
        if affected_id not in by_id or final_id not in by_id:
            raise ValueError("current_bookings_required")
        destination = station_key(by_id[final_id].destination)
        preferences = dict(coordinator.station_transfers)

        async def resolve(name):
            if generation != self._generation:
                raise ValueError("recovery_context_changed")
            station = await coordinator.engine._async_resolve_station(
                name=name, code="CALENDAR", location="", client=self.client
            )
            return station.code

        allowances = {}
        async with asyncio.timeout(20):
            origin_code = await resolve(origin)
            destination_code = await resolve(destination)
            for name, minutes in preferences.items():
                code = await resolve(name)
                allowance = TransferAllowance(minutes, "station_default")
                if code in allowances and allowances[code] != allowance:
                    raise ValueError("conflicting_station_allowances")
                allowances[code] = allowance

        def rebuild():
            now = dt_util.utcnow()
            if generation != self._generation:
                raise ValueError("recovery_context_changed")
            if coordinator.station_transfers != preferences:
                raise ValueError("station_preferences_changed")
            context = build_user_recovery_context(
                self._bookings(now),
                coordinator.connection_confirmations.active(now=now),
                affected_booking_id=affected_id,
                final_booking_id=final_id,
                confirmed_origin_code=origin_code,
                origin_confirmed_at=confirmed_at,
                ready_at=confirmed_at,
                resolved_stations={destination: destination_code},
                now=now,
                max_age=MAX_AGE,
                calendar_healthy=True,
                plan_truncated=False,
                simulation_active=False,
            )
            return RecoveryReviewInputs(
                context,
                RecoverySearchPolicy(
                    MAX_AGE,
                    timedelta(hours=2),
                    timedelta(hours=8),
                    tuple(allowances.items()),
                    coordinator.transfer_fallback,
                ),
            )

        result = await self.review.async_review(rebuild)
        return result.status

    async def async_select(self, *, option_id, revision):
        if self._busy:
            return "search_in_progress"
        self._busy = True
        generation = self._generation
        try:
            status = await self.review.async_select(
                option_id,
                revision,
                refresh=partial(self.client.async_recovery_search, force_refresh=True),
            )
            if generation == self._generation:
                self._selection_status = status
            return status
        finally:
            self._busy = False
            if not self._stopped:
                self.coordinator.async_update_listeners()

    def dashboard(self, now):
        try:
            bookings = self._bookings(now)
        except ValueError:
            if self._busy:
                self.invalidate()
            else:
                self.review.current()
            return {}
        confirmed = self.coordinator.connection_confirmations.active(now=now)
        connected_ids = {
            key
            for item in confirmed
            for key in (
                item.inbound_id,
                item.outbound_id,
            )
        }
        onward_ids = {item.inbound_id for item in confirmed}
        labels = {
            leg.booking_id: {
                "id": leg.booking_id,
                "origin": leg.origin,
                "destination": leg.destination,
                "departure": leg.departure,
                "can_affect": leg.in_latest_response,
                "can_finish": (
                    leg.in_latest_response and leg.booking_id not in onward_ids
                ),
            }
            for leg in bookings
            if leg.booking_id in connected_ids
        }
        result = self.review.current()
        return {
            "bookings": list(labels.values()),
            "selection_status": self._selection_status,
            "selected_option_id": result.selected_option_id,
            "status": "review_unavailable" if self._preflight_failed else result.status,
            "affected": [
                labels[key]
                for key in result.context.affected_booking_ids
                if key in labels
            ]
            if result.context
            else [],
            "options": [
                {
                    "option_id": route.option_id,
                    "revision": route.revision,
                    "valid_until": min(
                        route.valid_until, result.context.valid_until
                    ).isoformat(),
                    "legs": [
                        {
                            "origin": leg.origin_code,
                            "destination": leg.destination_code,
                            "departure": leg.departure.event_at.isoformat(),
                            "arrival": leg.arrival.event_at.isoformat(),
                        }
                        for leg in route.legs
                    ],
                    "transfers": [
                        {
                            "station": transfer.station_code,
                            "available": transfer.minutes_available,
                            "required": transfer.minutes_required,
                        }
                        for transfer in route.transfers
                    ],
                }
                for route in result.routes
            ],
        }
