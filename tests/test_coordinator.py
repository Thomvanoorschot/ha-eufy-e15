"""State merging and mowing-session history, driven through the DPS callback."""

from __future__ import annotations

import base64
from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eufy_e15.protocol import Activity


def b64(*data: int) -> str:
    return base64.b64encode(bytes(data)).decode()


MOWING = {"107": b64(0x08, 0x02, 0x18, 0x01)}
PAUSED = {"107": b64(0x08, 0x02, 0x18, 0x02)}
RETURNING = {"107": b64(0x08, 0x01, 0x18, 0x01)}
ON_STATION = {"108": b64(0x08, 0x01, 0x10, 0x01, 0x18, 0x01)}
IDLE = {"107": b64(0x00)}


@pytest.fixture
async def coordinator(hass: HomeAssistant, config_entry: MockConfigEntry, mock_connection):
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data
    coordinator._handle_dps({"1": False, "2": False, "8": 100, "118": 100}, True)
    coordinator._handle_dps(ON_STATION, False)
    return coordinator


async def test_full_session(
    hass: HomeAssistant, coordinator, freezer: FrozenDateTimeFactory
) -> None:
    assert coordinator.data.activity is Activity.DOCKED

    coordinator._handle_dps({**MOWING, "1": True}, False)
    assert coordinator.data.activity is Activity.MOWING
    assert coordinator.data.charger_connected is False
    freezer.tick(timedelta(minutes=30))
    coordinator._handle_dps(PAUSED, False)
    freezer.tick(timedelta(minutes=5))
    coordinator._handle_dps({**MOWING, "8": 60}, False)
    freezer.tick(timedelta(minutes=10))
    coordinator._handle_dps({"107": b64(0x08, 0x02, 0x18, 0x04)}, False)  # complete
    coordinator._handle_dps(RETURNING, False)
    assert coordinator.data.activity is Activity.RETURNING
    freezer.tick(timedelta(minutes=1))
    coordinator._handle_dps({**ON_STATION, "8": 55}, False)

    assert coordinator.data.activity is Activity.DOCKED
    assert coordinator.current_session is None
    session = coordinator.sessions[0]
    assert session.mission == "whole_lawn"
    assert session.result == "completed"
    assert session.pauses == 1
    assert session.mowing_seconds == 40 * 60
    assert (session.battery_start, session.battery_end) == (100, 55)


async def test_stop_on_lawn_is_idle(hass: HomeAssistant, coordinator) -> None:
    coordinator._handle_dps(MOWING, False)
    coordinator._handle_dps(IDLE, False)
    assert coordinator.data.activity is Activity.IDLE
    assert coordinator.sessions[0].result == "stopped"


async def test_sent_home(hass: HomeAssistant, coordinator) -> None:
    coordinator._handle_dps(MOWING, False)
    coordinator.note_requested_dock()
    coordinator._handle_dps(RETURNING, False)
    coordinator._handle_dps(ON_STATION, False)
    assert coordinator.sessions[0].result == "sent_home"


async def test_malformed_report_is_ignored(hass: HomeAssistant, coordinator) -> None:
    coordinator._handle_dps({"107": "!!!"}, False)
    assert coordinator.data.activity is Activity.DOCKED


async def test_history_survives_reload(
    hass: HomeAssistant, coordinator, config_entry: MockConfigEntry
) -> None:
    coordinator._handle_dps(MOWING, False)
    coordinator._handle_dps(RETURNING, False)
    coordinator._handle_dps(ON_STATION, False)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    restored = config_entry.runtime_data
    assert len(restored.sessions) == 1
    assert restored.data.activity is Activity.DOCKED
