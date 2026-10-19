"""Diagnostics download, with the local key and identifiers redacted."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICE_ID, CONF_LOCAL_KEY
from .coordinator import E15ConfigEntry

TO_REDACT = {CONF_LOCAL_KEY, CONF_DEVICE_ID, CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: E15ConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    state = coordinator.data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "connected": coordinator.connection.connected,
        "activity": state.activity,
        "charger_connected": state.charger_connected,
        "mission": repr(state.mission),
        "last_report": state.last_report.isoformat() if state.last_report else None,
        "dps": state.dps,
        "current_session": coordinator.current_session.as_dict()
        if coordinator.current_session
        else None,
        "sessions": [s.as_dict() for s in coordinator.sessions[:5]],
    }
