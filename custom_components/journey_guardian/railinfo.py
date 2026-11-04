"""Railinfo acquisition behind the shared cache and request broker."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import ClientSession, ClientTimeout

from .connection_evidence import ServiceReference, StationTimeEvidence
from .provider_broker import (
    ERROR_QUOTA_EXHAUSTED,
    ProviderBrokerError,
    ProviderRequest,
    ProviderRequestBroker,
    ProviderResult,
)
from .railinfo_arrival import normalize_railinfo_prediction

BASE_URL = "https://api.railinfo.uk"
REQUEST_TIMEOUT = ClientTimeout(total=15)


class RailinfoClient:
    """Acquire public Railinfo data without using TransportAPI credits."""

    def __init__(self, session: ClientSession, broker: ProviderRequestBroker) -> None:
        self._session = session
        self._broker = broker

    @property
    def configured(self) -> bool:
        """Railinfo needs no user credential."""
        return True

    async def async_places(
        self, query: str, *, urgent: bool = False
    ) -> ProviderResult:
        """Resolve a station name through Railinfo's public station search."""
        parameters = {"q": query.strip()}
        return await self._broker.async_request(
            ProviderRequest(
                provider="railinfo",
                operation="stations",
                parameters=parameters,
                quota_controlled=False,
            ),
            lambda: self._async_places_json(parameters),
            urgent=urgent,
        )

    async def async_station_board(
        self,
        station_code: str,
        departure: datetime,
        *,
        calling_at: str,
        urgent: bool = False,
    ) -> ProviderResult:
        """Fetch the live direct journey leg, including an intermediate stop."""
        code = station_code.strip().upper()
        destination = calling_at.strip().upper()
        parameters = {
            "from": code,
            "to": destination,
            "date": departure.date().isoformat(),
            "time": departure.strftime("%H%M"),
        }
        return await self._broker.async_request(
            ProviderRequest(
                provider="railinfo",
                operation="journeys",
                parameters=parameters,
                quota_controlled=False,
            ),
            lambda: self._async_journey_json(code, destination, parameters),
            urgent=urgent,
        )

    async def async_live_board(
        self, station_code: str, *, window_hours: int = 12
    ) -> ProviderResult:
        """Fetch reported movements used to confirm destination arrivals."""
        code = station_code.strip().upper()
        parameters = {"window_hours": max(1, min(window_hours, 12))}
        return await self._broker.async_request(
            ProviderRequest(
                provider="railinfo",
                operation="live_board",
                parameters={"station_code": code, **parameters},
                quota_controlled=False,
            ),
            lambda: self._async_live_board_json(code, parameters),
        )

    async def async_arrival_prediction(self, **kwargs) -> StationTimeEvidence | None:
        """Acquire explicit arrival prediction for a matched booked service."""
        return await self._async_station_prediction(event="arrival", **kwargs)

    async def async_departure_prediction(self, **kwargs) -> StationTimeEvidence | None:
        """Acquire explicit departure prediction, including on-time predictions."""
        return await self._async_station_prediction(event="departure", **kwargs)

    async def _async_station_prediction(
        self,
        *,
        origin_code: str,
        destination_code: str,
        expected_service_identity: str,
        event: str,
        booked_departure: datetime,
        booked_arrival: datetime,
        urgent: bool = False,
    ) -> StationTimeEvidence | None:
        """Acquire explicit matched arrival evidence; no automatic caller yet."""
        if booked_departure.utcoffset() is None or booked_arrival.utcoffset() is None:
            raise ValueError("timezone_required")
        departure = booked_departure.astimezone(ZoneInfo("Europe/London"))
        origin = origin_code.strip().upper()
        destination = destination_code.strip().upper()
        if any(
            len(code) != 3 or not code.isascii() or not code.isalpha()
            for code in (origin, destination)
        ):
            raise ValueError("resolved_station_codes_required")
        if booked_arrival.astimezone(UTC) <= booked_departure.astimezone(UTC):
            raise ValueError("arrival_after_departure_required")
        expected_service = ServiceReference("railinfo", expected_service_identity)
        parameters = {
            "from": origin, "to": destination,
            "date": departure.date().isoformat(), "time": departure.strftime("%H%M"),
        }
        result = await self._broker.async_request(
            ProviderRequest(
                provider="railinfo", operation="journey_details",
                parameters=parameters, quota_controlled=False,
            ),
            lambda: self._async_journey_details_json(parameters), urgent=urgent,
        )
        if not result.healthy:
            return None
        return normalize_railinfo_prediction(
            result.payload, origin_code=origin, destination_code=destination,
            expected_service=expected_service,
            booked_departure=booked_departure, booked_arrival=booked_arrival,
            observed_at=result.observed_at, event=event,
        )

    async def _async_journey_details_json(
        self, parameters: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        payload = await self._async_json("/journeys", parameters)
        if (
            not isinstance(payload, Mapping)
            or not isinstance(payload.get("journeys"), list)
        ):
            raise TypeError("Railinfo journey details must contain a journey list")
        return payload

    async def _async_places_json(
        self, parameters: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        payload = await self._async_json("/stations", parameters)
        if not isinstance(payload, list):
            raise TypeError("Railinfo station response must be a list")
        return {
            "results": [
                {"code": item.get("crs"), "name": item.get("description")}
                for item in payload
                if isinstance(item, Mapping)
            ]
        }

    async def _async_journey_json(
        self,
        station_code: str,
        destination_code: str,
        parameters: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Map route-aware journey results into the shared rail matcher shape."""
        payload = await self._async_json("/journeys", parameters)
        if not isinstance(payload, Mapping):
            raise TypeError("Railinfo journey response must be an object")
        journeys = payload.get("journeys")
        if not isinstance(journeys, list):
            raise TypeError("Railinfo journeys must be a list")
        records: list[Mapping[str, Any]] = []
        for journey in journeys:
            if not isinstance(journey, Mapping) or journey.get("changes") != 0:
                continue
            legs = journey.get("legs")
            if not isinstance(legs, list) or len(legs) != 1:
                continue
            leg = legs[0]
            if not isinstance(leg, Mapping):
                continue
            if (
                str(leg.get("from_crs", "")).upper() != station_code
                or str(leg.get("to_crs", "")).upper() != destination_code
            ):
                continue
            records.append(leg)
        return {
            "station_code": station_code,
            "date": payload.get("date"),
            "departures": {
                "all": [
                    {
                        "mode": "train",
                        "aimed_departure_time": _clock(record.get("dep")),
                        "expected_departure_time": "",
                        "destination_name": record.get("to_name"),
                        "operator_name": record.get("atoc_code"),
                        "train_uid": record.get("headcode"),
                        "status": record.get("status") or "",
                        "platform": record.get("dep_platform") or "",
                    }
                    for record in records
                ]
            },
        }

    async def _async_live_board_json(
        self, station_code: str, parameters: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        payload = await self._async_json(f"/boards/{station_code}", parameters)
        if not isinstance(payload, Mapping):
            raise TypeError("Railinfo live board response must be an object")
        return payload

    async def _async_json(
        self, path: str, parameters: Mapping[str, Any]
    ) -> Any:
        response = await self._session.get(
            f"{BASE_URL}{path}", params=parameters, timeout=REQUEST_TIMEOUT
        )
        if response.status == 429:
            raise ProviderBrokerError(ERROR_QUOTA_EXHAUSTED)
        response.raise_for_status()
        return await response.json(content_type=None)


def _clock(value: Any) -> str:
    """Convert Railinfo's HHMM scheduled time to the shared HH:MM format."""
    text = str(value or "").strip()
    return f"{text[:2]}:{text[2:]}" if len(text) == 4 and text.isdigit() else text
