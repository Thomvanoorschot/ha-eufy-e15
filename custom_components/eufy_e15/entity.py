"""Base entity for the Eufy E15."""

from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ALLOW_CONTROL, DEFAULT_ALLOW_CONTROL, DOMAIN, MANUFACTURER, MODEL
from .coordinator import E15Coordinator
from .transport import MowerConnectionError


class E15Entity(CoordinatorEntity[E15Coordinator]):
    """An entity of the mower device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: E15Coordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=coordinator.config_entry.title,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.available

    @property
    def dps(self) -> dict[str, Any]:
        return self.coordinator.data.dps

    async def async_write(self, dps: dict[str, Any]) -> None:
        """Send a write to the mower, if control is allowed for this entry."""
        if not self.coordinator.config_entry.options.get(CONF_ALLOW_CONTROL, DEFAULT_ALLOW_CONTROL):
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="control_disabled")
        try:
            await self.coordinator.connection.async_write(dps)
        except MowerConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
