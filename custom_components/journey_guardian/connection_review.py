"""Independent two-leg acquisition without changing selected-journey decisions."""

from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util

from .connection_evidence import (
    EvidenceConnectionAssessment,
    ServiceReference,
    assess_connection_evidence,
)
from .models import JourneyEvent
from .rail import normalize_station_board
from .travel_plan import RetainedLeg

FRESHNESS_WINDOW = timedelta(minutes=5)


async def async_review_connection(
    engine,
    inbound: RetainedLeg,
    outbound: RetainedLeg,
    *,
    minimum_minutes: int,
    now: datetime,
    still_current=lambda: True,
) -> tuple[EvidenceConnectionAssessment, datetime | None]:
    """Acquire two matched services through the existing Railinfo broker clients."""
    if engine._live_rail_provider != "railinfo" or engine._railinfo_client is None:
        raise ValueError("connection_provider_unsupported")
    client = engine._railinfo_client
    references, evidence = [], []
    for leg, event in ((inbound, "arrival"), (outbound, "departure")):
        if not still_current():
            raise ValueError("connection_no_longer_current")
        if leg.arrival is None:
            raise ValueError("booked_arrival_required")
        origin = await engine._async_resolve_station(
            name=leg.origin, code="CALENDAR", location="", client=client
        )
        if not still_current():
            raise ValueError("connection_no_longer_current")
        destination = await engine._async_resolve_station(
            name=leg.destination, code="CALENDAR", location="", client=client
        )
        journey = JourneyEvent(
            datetime.fromisoformat(leg.departure),
            datetime.fromisoformat(leg.arrival),
            f"{leg.origin} to {leg.destination}",
            "",
            origin.code,
            leg.origin,
            leg.destination,
            "confirmed_connection",
        )
        if not still_current():
            raise ValueError("connection_no_longer_current")
        board = await client.async_station_board(
            origin.code, journey.start, calling_at=destination.code
        )
        if not board.healthy:
            raise ValueError("connection_provider_unavailable")
        observation = normalize_station_board(
            board.payload,
            journey=journey,
            observed_at=board.observed_at,
            expected_station_code=origin.code,
            source="railinfo",
        )
        reference = ServiceReference("railinfo", observation.service_identity)
        references.append(reference)
        if not still_current():
            raise ValueError("connection_no_longer_current")
        getter = (
            client.async_arrival_prediction
            if event == "arrival"
            else client.async_departure_prediction
        )
        evidence.append(
            None
            if observation.cancelled
            else await getter(
                origin_code=origin.code,
                destination_code=destination.code,
                expected_service_identity=reference.identity,
                booked_departure=journey.start,
                booked_arrival=journey.end,
            )
        )
        if event == "arrival":
            interchange = destination.code
        elif interchange != origin.code:
            raise ValueError("connection_station_mismatch")
    assessment = assess_connection_evidence(
        confirmed=True,
        inbound=evidence[0],
        outbound=evidence[1],
        expected_inbound=references[0],
        expected_outbound=references[1],
        station_identity=interchange,
        minimum_minutes=minimum_minutes,
        now=dt_util.now(),
        max_age=FRESHNESS_WINDOW,
    )
    expiry = (
        min(
            *[item.observed_at + FRESHNESS_WINDOW for item in evidence],
            *[item.event_at for item in evidence if item.kind == "predicted"],
        )
        if all(item is not None for item in evidence)
        else None
    )
    return assessment, expiry
