"""The mower itself: start, pause and send home."""

from __future__ import annotations

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, DP_PAUSE, DP_SAVE_MAP_PROCESS, DP_SWITCH_GO
from .coordinator import E15ConfigEntry, E15Coordinator
from .entity import E15Entity
from .protocol import Activity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: E15ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([E15LawnMower(entry.runtime_data)])


class E15LawnMower(E15Entity, LawnMowerEntity):
    """Only hardware-validated writes: DP 1 true starts, DP 2 pauses and resumes, and
    DP 1 false ends the task and drives the mower home. DP 3 (switch_charge) is
    accepted by the E15 but ignored, so it is never used.
    """

    _attr_name = None
    _attr_supported_features = (
        LawnMowerEntityFeature.START_MOWING
        | LawnMowerEntityFeature.PAUSE
        | LawnMowerEntityFeature.DOCK
    )

    def __init__(self, coordinator: E15Coordinator) -> None:
        super().__init__(coordinator, "mower")

    @property
    def activity(self) -> LawnMowerActivity | None:
        activity = self.coordinator.data.activity
        return LawnMowerActivity(activity.value) if activity else None

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        mission = self.coordinator.data.mission
        if mission is None:
            return None
        return {"mission": mission.mission_name, "phase": mission.sub_mission_name}

    def _refuse_during_map_save(self) -> None:
        # The app offers no control while the map is saved, and the E15 ignores one.
        progress = self.dps.get(DP_SAVE_MAP_PROCESS)
        if isinstance(progress, int) and 0 < progress < 100:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="map_saving")

    async def async_start_mowing(self) -> None:
        self._refuse_during_map_save()
        if self.coordinator.data.activity is Activity.PAUSED:
            await self.async_write({DP_PAUSE: False})
        else:
            await self.async_write({DP_SWITCH_GO: True})

    async def async_pause(self) -> None:
        if self.coordinator.data.activity is not Activity.MOWING:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="not_mowing")
        await self.async_write({DP_PAUSE: True})

    async def async_dock(self) -> None:
        self._refuse_during_map_save()
        self.coordinator.note_requested_dock()
        await self.async_write({DP_SWITCH_GO: False})
