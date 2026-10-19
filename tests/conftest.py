"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eufy_e15.const import CONF_DEVICE_ID, CONF_LOCAL_KEY, DOMAIN

DEVICE_ID = "bf0000000000000000test"
LOCAL_KEY = "0123456789abcdef"
HOST = "192.0.2.10"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load integrations from custom_components."""


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Grasmaaier",
        unique_id=DEVICE_ID,
        data={"host": HOST, CONF_DEVICE_ID: DEVICE_ID, CONF_LOCAL_KEY: LOCAL_KEY},
    )


@pytest.fixture
def mock_connection() -> Generator[None]:
    """Replace the session thread: nothing touches the network in tests."""
    with (
        patch("custom_components.eufy_e15.transport.MowerConnection.start"),
        patch("custom_components.eufy_e15.transport.MowerConnection.stop"),
    ):
        yield
