"""Railinfo acquisition behind the shared cache and request broker."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .provider_broker import (
    ERROR_QUOTA_EXHAUSTED,
    ProviderBrokerError,
    ProviderRequest,
    ProviderRequestBroker,
    ProviderResult,
)

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
