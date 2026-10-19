"""Sensors of the Eufy E15."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    DP_BASE_STATION_USED,
    DP_BATTERY,
    DP_BLADE_USED,
    DP_NET_MEDIA_TYPE,
    DP_SAVE_MAP_PROCESS,
    DP_SIGNAL,
)
from .coordinator import E15ConfigEntry, E15Coordinator, MowerState
from .entity import E15Entity
from .protocol import MISSIONS, OTHER, SUB_MISSIONS

HISTORY_ATTRIBUTE_LIMIT = 20


def _dp(dp: str) -> Callable[[MowerState], Any]:
    return lambda state: state.dps.get(dp)


@dataclass(frozen=True, kw_only=True)
class E15SensorDescription(SensorEntityDescription):
    value: Callable[[MowerState], Any]


SENSORS: tuple[E15SensorDescription, ...] = (
    E15SensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value=_dp(DP_BATTERY),
    ),
    E15SensorDescription(
        key="mission",
        device_class=SensorDeviceClass.ENUM,
        options=sorted({*MISSIONS.values(), OTHER}),
        value=lambda s: s.mission.mission_name if s.mission else None,
    ),
    E15SensorDescription(
        key="phase",
        device_class=SensorDeviceClass.ENUM,
        options=sorted({*SUB_MISSIONS.values(), OTHER}),
        value=lambda s: s.mission.sub_mission_name if s.mission else None,
    ),
    E15SensorDescription(
        key="wifi_signal",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=_dp(DP_SIGNAL),
    ),
    E15SensorDescription(
        key="network",
        device_class=SensorDeviceClass.ENUM,
        options=["none", "wifi", "cellular"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda s: v.lower() if isinstance(v := s.dps.get(DP_NET_MEDIA_TYPE), str) else None,
    ),
    E15SensorDescription(
        key="map_save_progress",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value=_dp(DP_SAVE_MAP_PROCESS),
    ),
    E15SensorDescription(
        key="blade_used_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=_dp(DP_BLADE_USED),
    ),
    E15SensorDescription(
        key="base_station_used_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=_dp(DP_BASE_STATION_USED),
    ),
    E15SensorDescription(
        key="last_report",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda s: s.last_report,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: E15ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            *(E15Sensor(coordinator, description) for description in SENSORS),
            E15LastSessionSensor(coordinator),
        ]
    )


class E15Sensor(E15Entity, SensorEntity):
    entity_description: E15SensorDescription

    def __init__(self, coordinator: E15Coordinator, description: E15SensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator.data)


class E15LastSessionSensor(E15Entity, SensorEntity):
    """End time of the last finished mowing session; the history is in its attributes."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _unrecorded_attributes = frozenset({"history", "running"})

    def __init__(self, coordinator: E15Coordinator) -> None:
        super().__init__(coordinator, "last_session")

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> datetime | None:
        if not self.coordinator.sessions or not self.coordinator.sessions[0].ended:
            return None
        return dt_util.parse_datetime(self.coordinator.sessions[0].ended)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        sessions = self.coordinator.sessions
        last = sessions[0].as_dict() if sessions else {}
        current = self.coordinator.current_session
        return {
            **{k: v for k, v in last.items() if k != "mowing_seconds"},
            "mowing_minutes": round(last["mowing_seconds"] / 60) if last else None,
            "running": current.as_dict() if current else None,
            "history": [s.as_dict() for s in sessions[:HISTORY_ATTRIBUTE_LIMIT]],
        }
