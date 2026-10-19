"""Binary sensors of the Eufy E15."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DP_CHILD_LOCK, DP_RAIN_AUTO_RETURN
from .coordinator import E15ConfigEntry, E15Coordinator, MowerState
from .entity import E15Entity


@dataclass(frozen=True, kw_only=True)
class E15BinarySensorDescription(BinarySensorEntityDescription):
    value: Callable[[MowerState], bool | None]


def _bool_dp(dp: str) -> Callable[[MowerState], bool | None]:
    return lambda s: v if isinstance(v := s.dps.get(dp), bool) else None


BINARY_SENSORS: tuple[E15BinarySensorDescription, ...] = (
    E15BinarySensorDescription(
        key="on_station",
        device_class=BinarySensorDeviceClass.PLUG,
        value=lambda s: s.charger_connected,
    ),
    E15BinarySensorDescription(
        key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value=lambda s: s.mission.error if s.mission else None,
    ),
    # Safety settings stay read-only: change them in the Eufy app.
    E15BinarySensorDescription(
        key="rain_auto_return",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=_bool_dp(DP_RAIN_AUTO_RETURN),
    ),
    E15BinarySensorDescription(
        key="child_lock",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=_bool_dp(DP_CHILD_LOCK),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: E15ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(E15BinarySensor(coordinator, d) for d in BINARY_SENSORS)


class E15BinarySensor(E15Entity, BinarySensorEntity):
    entity_description: E15BinarySensorDescription

    def __init__(
        self, coordinator: E15Coordinator, description: E15BinarySensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value(self.coordinator.data)
