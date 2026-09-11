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
        """Fetch a bounded live departure board for one origin station."""
        del departure, calling_at  # Matching remains local and calendar-anchored.
        code = station_code.strip().upper()
        parameters = {"station_code": code, "limit": 50}
        return await self._broker.async_request(
            ProviderRequest(
                provider="railinfo",
                operation="departures",
                parameters=parameters,
                quota_controlled=False,
            ),
            lambda: self._async_board_json(code, {"limit": 50}),
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

    async def _async_board_json(
        self, station_code: str, parameters: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        payload = await self._async_json(
            f"/boards/{station_code}/departures", parameters
        )
        if not isinstance(payload, Mapping):
            raise TypeError("Railinfo board response must be an object")
        records = payload.get("departures")
        if not isinstance(records, list):
            raise TypeError("Railinfo departures must be a list")
        return {
            "station_code": payload.get("crs"),
            "date": payload.get("date"),
            "departures": {
                "all": [
                    {
                        "mode": "train",
                        "aimed_departure_time": _clock(record.get("public_dep")),
                        "expected_departure_time": record.get("etd") or "",
                        "destination_name": record.get("destination"),
                        "operator_name": record.get("operator"),
                        "train_uid": (
                            record.get("live_train_id")
                            or record.get("signalling_id")
                        ),
                        "status": record.get("status") or "",
                        "platform": (
                            record.get("live_platform")
                            or record.get("sched_platform")
                            or ""
                        ),
                    }
                    for record in records
                    if isinstance(record, Mapping)
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
