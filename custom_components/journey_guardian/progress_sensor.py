"""Event-driven station progress from the configured traveller's GPS source."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .entity import JourneyGuardianEntity
from .progress import StationProgress, StationZone, finite_number, parse_progress_zones


class JourneyProgressSensor(JourneyGuardianEntity, SensorEntity):
    """Expose local proximity evidence without changing journey decisions."""

    _attr_translation_key = "station_progress"
    _attr_icon = "mdi:map-marker-path"

    def __init__(self, coordinator, entry, person_entity: str, zones: str) -> None:
        super().__init__(coordinator, entry, "station_progress")
        self._person = person_entity
        self._zones = parse_progress_zones(zones)
        self._progress = StationProgress()
        self._result = {"status": "waiting"}
        self._store = Store(
            coordinator.hass, 1, f"journey_guardian.progress.{entry.entry_id}"
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        saved = await self._store.async_load()
        if isinstance(saved, dict):
            observed = dt_util.parse_datetime(str(saved.get("observed_at", "")))
            index = saved.get("last_index")
            key = saved.get("key")
            if (
                isinstance(key, str)
                and len(key) == 64
                and isinstance(index, int)
                and not isinstance(index, bool)
                and 0 <= index < len(self._zones)
                and observed is not None
                and observed.tzinfo is not None
                and timedelta(0) <= dt_util.now() - observed <= timedelta(hours=24)
            ):
                self._progress.key = key
                self._progress.last_index = index
                self._progress.observed_at = observed
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._person, *self._zones], self._handle_location_update
            )
        )
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._handle_location_update, timedelta(minutes=1)
            )
        )
        self._update()

    @property
    def native_value(self) -> str:
        return self._result["status"]

    @property
    def extra_state_attributes(self) -> dict:
        return {key: value for key, value in self._result.items() if key != "status"}

    @callback
    def _handle_location_update(self, _event) -> None:
        self._update()
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update()
        self.async_write_ha_state()

    def _saved_data(self) -> dict:
        return {
            "key": self._progress.key,
            "last_index": self._progress.last_index,
            "observed_at": (
                self._progress.observed_at.isoformat()
                if self._progress.observed_at
                else None
            ),
        }

    @callback
    def _update(self) -> None:
        before = self._saved_data()
        zones = []
        for entity_id in self._zones:
            state = self.hass.states.get(entity_id)
            if state is None:
                zones = []
                break
            attrs = state.attributes
            lat, lon, radius = map(
                finite_number,
                (attrs.get("latitude"), attrs.get("longitude"), attrs.get("radius")),
            )
            if (
                lat is None
                or lon is None
                or radius is None
                or not -90 <= lat <= 90
                or not -180 <= lon <= 180
                or not 0 < radius <= 1000
            ):
                zones = []
                break
            zones.append(
                StationZone(
                    entity_id, str(attrs.get("friendly_name", "")), lat, lon, radius
                )
            )
        person_state = self.hass.states.get(self._person)
        source_id = person_state.attributes.get("source") if person_state else None
        source = (
            self.hass.states.get(source_id)
            if isinstance(source_id, str) and source_id.startswith("device_tracker.")
            else None
        )
        attrs = (
            source.attributes
            if source
            and source.state not in {"unknown", "unavailable"}
            and source.attributes.get("source_type") == "gps"
            else {}
        )
        self._result = self._progress.update(
            self.coordinator.data,
            tuple(zones),
            now=dt_util.now(),
            latitude=attrs.get("latitude"),
            longitude=attrs.get("longitude"),
            accuracy=attrs.get("gps_accuracy"),
            location_time=source.last_updated if attrs else None,
        )
        if before != self._saved_data():
            self._store.async_delay_save(self._saved_data, 5)
