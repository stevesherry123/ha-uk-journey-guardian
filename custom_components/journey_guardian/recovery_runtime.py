"""Home Assistant entry point for a user-confirmed recovery review."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from functools import partial

from homeassistant.util import dt as dt_util

from .connection import TransferAllowance
from .connection_evidence import ServiceReference, assess_connection_evidence
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

    def __init__(self, coordinator, client, tracking=None, *, alerts=None):
        self.coordinator = coordinator
        self.client = client
        self.tracking = tracking
        self.alerts = alerts
        self.next_tracking_check_at = None
        self._transfer_assessment = None
        self._live_tracking = None
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

    async def async_approve(self, *, option_id, revision):
        if self._busy:
            return "search_in_progress"
        self._busy = True
        try:
            if not self._tracking_allowed():
                return "tracking_unavailable"
            now = dt_util.utcnow()
            existing = self.tracking.record
            if (
                existing is not None
                and not existing.stopped
                and not existing.finished
                and now < existing.expires_at
                and (existing.option_id, existing.revision) == (option_id, revision)
            ):
                return "replacement_approved"
            review = self.review.current()
            if review.context is None or review.selected_option_id != option_id:
                return "selection_expired"
            route = next(
                (
                    item
                    for item in review.routes
                    if (item.option_id, item.revision) == (option_id, revision)
                ),
                None,
            )
            if route is None:
                return "selection_expired"
            await self.tracking.async_approve(
                route, review.context.affected_booking_ids, now=now
            )
            self.invalidate()
            self._live_tracking = None
            self._transfer_assessment = None
            snapshot = self.coordinator.data
            current = self.coordinator.suppress_superseded(snapshot)
            if current is not snapshot:
                self.coordinator.async_set_updated_data(current)
            await self.coordinator.async_request_refresh()
            return "replacement_approved"
        except ValueError, OSError:
            return "approval_unavailable"
        finally:
            self._busy = False
            if not self._stopped:
                self.coordinator.async_update_listeners()

    def is_booking_superseded(self, booking_id, now):
        record = self.tracking.record if self.tracking is not None else None
        return bool(
            record
            and not record.stopped
            and now < record.expires_at
            and booking_id in record.affected_booking_ids
        )

    def _tracking_allowed(self):
        snapshot = self.coordinator.data
        return (
            not self._stopped
            and self.tracking is not None
            and self.tracking.available
            and snapshot is not None
            and not snapshot.simulation_active
        )

    async def async_progress(self, *, tracking_id, leg_index=None):
        if not self._tracking_allowed() or self._busy:
            return "tracking_unavailable"
        self._busy = True
        try:
            if leg_index is None:
                await self.tracking.async_stop(tracking_id)
                await self.coordinator.async_request_refresh()
            else:
                await self.tracking.async_confirm_arrival(
                    tracking_id, leg_index, now=dt_util.utcnow()
                )
            self._live_tracking = None
            self._transfer_assessment = None
            return "tracking_updated"
        except ValueError, OSError:
            return "tracking_unavailable"
        finally:
            self._busy = False
            if not self._stopped:
                self.coordinator.async_update_listeners()

    def active_tracking(self, now):
        if not self._tracking_allowed():
            return None
        record = self.tracking.record
        if (
            record is None
            or record.stopped
            or record.finished
            or now >= record.expires_at
        ):
            return None
        return record

    @staticmethod
    def _prediction_arguments(leg):
        return {
            "origin_code": leg.origin,
            "destination_code": leg.destination,
            "expected_service_identity": leg.service_identity,
            "booked_departure": leg.instant("scheduled_departure"),
            "booked_arrival": leg.instant("scheduled_arrival"),
        }

    @staticmethod
    def _alert_pair(record):
        return (record.tracking_id, record.option_id)

    async def async_check_tracking(self, *, tracking_id, leg_index):
        record = self.active_tracking(dt_util.utcnow())
        if (
            self._busy
            or record is None
            or record.tracking_id != tracking_id
            or record.leg_index != leg_index
        ):
            return "tracking_unavailable"
        self._busy = True
        self._live_tracking = None
        self._transfer_assessment = None
        try:
            leg = record.legs[leg_index]
            arguments = self._prediction_arguments(leg)
            queries = [
                self.client.async_departure_prediction(**arguments),
                self.client.async_arrival_prediction(**arguments),
            ]
            onward = None
            if leg_index == 0 and record.transfer_minutes is not None:
                onward = record.legs[1]
                queries.append(
                    self.client.async_departure_prediction(
                        **self._prediction_arguments(onward)
                    )
                )
            departure, arrival, *onward_predictions = await asyncio.gather(*queries)
            now = dt_util.utcnow()
            if self.active_tracking(now) is not record:
                return "tracking_unavailable"
            self._live_tracking = {
                name: evidence
                for name, evidence in (
                    ("departure", departure),
                    ("arrival", arrival),
                )
                if evidence is not None
                and now < evidence.event_at
                and timedelta(0) <= now - evidence.observed_at < MAX_AGE
            }
            if onward is not None:
                await self._async_check_transfer(
                    record, leg, onward, arrival, onward_predictions[0], now
                )
            return (
                "tracking_checked" if self._live_tracking else "prediction_unavailable"
            )
        except ValueError, OSError, TimeoutError, ProviderBrokerError:
            return "prediction_unavailable"
        finally:
            self._busy = False
            if not self._stopped:
                self.coordinator.async_update_listeners()

    async def _async_check_transfer(self, record, leg, onward, arrival, departure, now):
        assessment = assess_connection_evidence(
            confirmed=True,
            inbound=arrival,
            outbound=departure,
            expected_inbound=ServiceReference("railinfo", leg.service_identity),
            expected_outbound=ServiceReference("railinfo", onward.service_identity),
            station_identity=leg.destination,
            minimum_minutes=record.transfer_minutes,
            now=now,
            max_age=MAX_AGE,
        )
        expires = None
        if assessment.classification in ("at_risk", "viable"):
            expires = min(
                arrival.observed_at + MAX_AGE,
                departure.observed_at + MAX_AGE,
                arrival.event_at,
                departure.event_at,
            )
        self._transfer_assessment = (assessment, expires)
        if self.alerts is not None:
            try:
                await self.alerts.async_process(
                    self._alert_pair(record),
                    assessment,
                    expires,
                    station=leg.destination,
                    expires_at=record.expires_at,
                    is_current=lambda: self.active_tracking(dt_util.utcnow()) is record,
                )
            except Exception:
                self.coordinator.connection_alert_error = True

    def _tracking_dashboard(self, now):
        if not self._tracking_allowed():
            return None
        record = self.tracking.record
        if record is None or now >= record.expires_at:
            return None
        active = not record.stopped and not record.finished
        live = {}
        for name, evidence in (self._live_tracking or {}).items():
            if now < min(evidence.event_at, evidence.observed_at + MAX_AGE):
                live[name] = evidence.event_at.isoformat()
                live[f"{name}_valid_until"] = min(
                    evidence.event_at, evidence.observed_at + MAX_AGE
                ).isoformat()
        transfer = None
        last_alert = None
        if active and record.leg_index == 0 and record.transfer_minutes is not None:
            transfer = {
                "classification": "unknown",
                "minimum_minutes": record.transfer_minutes,
            }
            if self._transfer_assessment is not None:
                assessment, expiry = self._transfer_assessment
                if expiry is not None and now < expiry:
                    transfer = assessment.as_dict()
                    transfer["valid_until"] = expiry.isoformat()
            if self.alerts is not None:
                last_alert = self.alerts.ledger.status(
                    self._alert_pair(record), now=now
                )
        return {
            "id": record.tracking_id,
            "transfer": transfer,
            "last_alert": last_alert,
            "next_check_at": (
                self.next_tracking_check_at.isoformat()
                if active and self.next_tracking_check_at is not None
                else None
            ),
            "state": "stopped"
            if record.stopped
            else ("completed" if record.finished else "tracking"),
            "leg_index": record.leg_index,
            "can_confirm_arrival": active
            and now >= record.legs[record.leg_index].instant("approved_departure"),
            "legs": [
                {
                    "origin": leg.origin,
                    "destination": leg.destination,
                    "departure": leg.approved_departure,
                    "arrival": leg.approved_arrival,
                }
                for leg in record.legs
            ],
            "live": live if active else {},
        }

    def dashboard(self, now):
        tracking = self._tracking_dashboard(now)
        try:
            bookings = self._bookings(now)
        except ValueError:
            if self._busy:
                self.invalidate()
            else:
                self.review.current()
            return {"tracking": tracking} if tracking else {}
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
            "tracking": tracking,
            "can_approve": self._tracking_allowed()
            and (tracking is None or tracking["state"] != "tracking"),
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
