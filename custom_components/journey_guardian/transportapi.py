"""Manual-only TransportAPI acquisition behind the shared request broker."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .provider_broker import (
    ProviderRequest,
    ProviderRequestBroker,
    ProviderResult,
)

BASE_URL = "https://transportapi.com"
REQUEST_TIMEOUT = ClientTimeout(total=15)


class TransportAPIClient:
    """Acquire TransportAPI JSON without bypassing quota or cache controls."""

    def __init__(
        self,
        session: ClientSession,
        broker: ProviderRequestBroker,
        *,
        app_id: str,
        app_key: str,
    ) -> None:
        """Create a dormant client; construction performs no request."""
        self._session = session
        self._broker = broker
        self._app_id = app_id.strip()
        self._app_key = app_key.strip()

    @property
    def configured(self) -> bool:
        """Return whether both required credentials are present."""
        return bool(self._app_id and self._app_key)

    async def async_places(self, query: str) -> ProviderResult:
        """Resolve a station name using one quota-controlled Places request."""
        parameters = {
            "query": query,
            "type": "train_station",
            "limit": 10,
        }
        return await self._broker.async_request(
            ProviderRequest(
                provider="transportapi",
                operation="places",
                parameters=parameters,
            ),
            lambda: self._async_json("/v3/uk/places.json", parameters),
        )

    async def async_station_board(
        self, station_code: str, departure: datetime
    ) -> ProviderResult:
        """Fetch a bounded live station board around the calendar departure."""
        code = station_code.strip().upper()
        parameters: dict[str, Any] = {
            "datetime": departure.isoformat(),
            "from_offset": "-PT00:45:00",
            "to_offset": "PT00:45:00",
            "limit": 50,
            "live": "true",
            "train_status": "passenger",
            "source_detail": "true",
        }
        return await self._broker.async_request(
            ProviderRequest(
                provider="transportapi",
                operation="station_timetables",
                parameters={"station_code": code, **parameters},
            ),
            lambda: self._async_json(
                f"/v3/uk/train/station_timetables/{code}.json",
                parameters,
            ),
        )

    async def _async_json(
        self, path: str, parameters: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        if not self.configured:
            raise RuntimeError("transportapi_credentials_missing")
        response = await self._session.get(
            f"{BASE_URL}{path}",
            params=parameters,
            headers={
                "X-App-Id": self._app_id,
                "X-App-Key": self._app_key,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = await response.json(content_type=None)
        if not isinstance(payload, Mapping):
            raise TypeError("TransportAPI response must be an object")
        return payload
