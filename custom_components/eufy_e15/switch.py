"""Writable on/off settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DP_SMART_FORBID_ZONE, DP_SPARSE_LAWN
from .coordinator import E15ConfigEntry, E15Coordinator
from .entity import E15Entity


@dataclass(frozen=True, kw_only=True)
class E15SwitchDescription(SwitchEntityDescription):
    dp: str


SWITCHES: tuple[E15SwitchDescription, ...] = (
    E15SwitchDescription(
        key="smart_no_go_zones", dp=DP_SMART_FORBID_ZONE, entity_category=EntityCategory.CONFIG
    ),
    E15SwitchDescription(
        key="sparse_lawn_optimization", dp=DP_SPARSE_LAWN, entity_category=EntityCategory.CONFIG
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: E15ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(E15Switch(coordinator, d) for d in SWITCHES)


class E15Switch(E15Entity, SwitchEntity):
    entity_description: E15SwitchDescription

    def __init__(self, coordinator: E15Coordinator, description: E15SwitchDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        value = self.dps.get(self.entity_description.dp)
        return value if isinstance(value, bool) else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.async_write({self.entity_description.dp: True})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_write({self.entity_description.dp: False})
