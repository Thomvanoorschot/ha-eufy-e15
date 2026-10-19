"""Entities and the writes they send."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.lawn_mower import (
    DOMAIN as LAWN_MOWER_DOMAIN,
)
from homeassistant.components.lawn_mower import (
    SERVICE_DOCK,
    SERVICE_PAUSE,
    SERVICE_START_MOWING,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eufy_e15.const import CONF_ALLOW_CONTROL

MOWER = "lawn_mower.grasmaaier"


def b64(*data: int) -> str:
    return base64.b64encode(bytes(data)).decode()


@pytest.fixture
async def setup(hass: HomeAssistant, config_entry: MockConfigEntry, mock_connection):
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data
    coordinator._handle_dps(
        {"1": False, "2": False, "8": 87, "109": 68, "110": 40, "118": 100, "134": "Wifi"}, True
    )
    coordinator._handle_dps({"108": b64(0x10, 0x01)}, False)
    await hass.async_block_till_done()
    write = AsyncMock()
    with patch.object(coordinator.connection, "async_write", write):
        yield coordinator, write


async def test_states(hass: HomeAssistant, setup) -> None:
    assert hass.states.get(MOWER).state == "docked"
    assert hass.states.get("sensor.grasmaaier_battery").state == "87"
    assert hass.states.get("sensor.grasmaaier_network").state == "wifi"
    assert hass.states.get("number.grasmaaier_mowing_height").state == "40"
    assert hass.states.get("binary_sensor.grasmaaier_on_charging_station").state == "on"


async def test_start_and_dock(hass: HomeAssistant, setup) -> None:
    coordinator, write = setup
    await hass.services.async_call(
        LAWN_MOWER_DOMAIN, SERVICE_START_MOWING, {ATTR_ENTITY_ID: MOWER}, blocking=True
    )
    write.assert_awaited_with({"1": True})
    coordinator._handle_dps({"107": b64(0x08, 0x02, 0x18, 0x01)}, False)
    await hass.async_block_till_done()
    assert hass.states.get(MOWER).state == "mowing"

    await hass.services.async_call(
        LAWN_MOWER_DOMAIN, SERVICE_PAUSE, {ATTR_ENTITY_ID: MOWER}, blocking=True
    )
    write.assert_awaited_with({"2": True})
    coordinator._handle_dps({"107": b64(0x08, 0x02, 0x18, 0x02)}, False)
    await hass.async_block_till_done()

    await hass.services.async_call(
        LAWN_MOWER_DOMAIN, SERVICE_START_MOWING, {ATTR_ENTITY_ID: MOWER}, blocking=True
    )
    write.assert_awaited_with({"2": False})

    await hass.services.async_call(
        LAWN_MOWER_DOMAIN, SERVICE_DOCK, {ATTR_ENTITY_ID: MOWER}, blocking=True
    )
    write.assert_awaited_with({"1": False})


async def test_refused_during_map_save(hass: HomeAssistant, setup) -> None:
    coordinator, write = setup
    coordinator._handle_dps({"118": 40}, False)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            LAWN_MOWER_DOMAIN, SERVICE_START_MOWING, {ATTR_ENTITY_ID: MOWER}, blocking=True
        )
    write.assert_not_awaited()


async def test_pause_only_while_mowing(hass: HomeAssistant, setup) -> None:
    _, write = setup
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            LAWN_MOWER_DOMAIN, SERVICE_PAUSE, {ATTR_ENTITY_ID: MOWER}, blocking=True
        )
    write.assert_not_awaited()


async def test_control_disabled(hass: HomeAssistant, config_entry: MockConfigEntry, setup) -> None:
    _, write = setup
    hass.config_entries.async_update_entry(config_entry, options={CONF_ALLOW_CONTROL: False})
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "number",
            "set_value",
            {ATTR_ENTITY_ID: "number.grasmaaier_mowing_height", "value": 50},
            blocking=True,
        )
    write.assert_not_awaited()


async def test_set_mow_height(hass: HomeAssistant, setup) -> None:
    _, write = setup
    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: "number.grasmaaier_mowing_height", "value": 50},
        blocking=True,
    )
    write.assert_awaited_with({"110": 50})
