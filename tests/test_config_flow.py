"""Config, reconfigure and options flows."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eufy_e15.const import CONF_ALLOW_CONTROL, DOMAIN
from custom_components.eufy_e15.transport import MowerConnectionError

from .conftest import DEVICE_ID, HOST, LOCAL_KEY

USER_INPUT = {"host": HOST, "device_id": DEVICE_ID, "local_key": LOCAL_KEY}
PROBE = "custom_components.eufy_e15.config_flow.probe"


@pytest.fixture(autouse=True)
def no_setup():
    with patch("custom_components.eufy_e15.async_setup_entry", return_value=True):
        yield


async def test_user_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    with patch(PROBE, return_value={"8": 100}):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == DEVICE_ID


@pytest.mark.parametrize(
    ("probe", "user_input", "error"),
    [
        ({"side_effect": MowerConnectionError("timeout")}, USER_INPUT, "cannot_connect"),
        ({"side_effect": RuntimeError}, USER_INPUT, "unknown"),
        ({"return_value": {"1": True}}, USER_INPUT, "not_an_e15"),
        ({"return_value": {"8": 1}}, {**USER_INPUT, "local_key": "short"}, "invalid_local_key"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant, probe: dict, user_input: dict, error: str
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PROBE, **probe):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input)
    assert result["errors"] == {"base": error}


async def test_already_configured(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    with patch(PROBE, return_value={"8": 100}):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.0.2.20", "local_key": "fedcba9876543210"}
        )
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data["host"] == "192.0.2.20"
    assert config_entry.data["device_id"] == DEVICE_ID


async def test_options(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ALLOW_CONTROL: False}
    )
    assert config_entry.options == {CONF_ALLOW_CONTROL: False}
