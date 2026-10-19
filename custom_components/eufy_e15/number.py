"""Writable numeric settings: mowing height and speaker volume."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DP_MOW_HEIGHT, DP_VOLUME, MOW_HEIGHT_MAX, MOW_HEIGHT_MIN, MOW_HEIGHT_STEP
from .coordinator import E15ConfigEntry, E15Coordinator
from .entity import E15Entity


@dataclass(frozen=True, kw_only=True)
class E15NumberDescription(NumberEntityDescription):
    dp: str


NUMBERS: tuple[E15NumberDescription, ...] = (
    E15NumberDescription(
        key="mow_height",
        dp=DP_MOW_HEIGHT,
        device_class=NumberDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        native_min_value=MOW_HEIGHT_MIN,
        native_max_value=MOW_HEIGHT_MAX,
        native_step=MOW_HEIGHT_STEP,
        mode=NumberMode.SLIDER,
    ),
    E15NumberDescription(
        key="volume",
        dp=DP_VOLUME,
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: E15ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(E15Number(coordinator, d) for d in NUMBERS)


class E15Number(E15Entity, NumberEntity):
    entity_description: E15NumberDescription

    def __init__(self, coordinator: E15Coordinator, description: E15NumberDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        value = self.dps.get(self.entity_description.dp)
        return value if isinstance(value, int) else None

    async def async_set_native_value(self, value: float) -> None:
        await self.async_write({self.entity_description.dp: int(value)})
