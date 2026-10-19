"""Config flow: the mower's IP address, device id and local key. No account."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .const import (
    CONF_ALLOW_CONTROL,
    CONF_DEVICE_ID,
    CONF_LOCAL_KEY,
    DEFAULT_ALLOW_CONTROL,
    DOMAIN,
    DP_BATTERY,
)
from .transport import MowerConnectionError, probe

_LOGGER = logging.getLogger(__name__)

DEFAULT_TITLE = "Grasmaaier"
_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _schema(defaults: dict[str, Any], *, with_device_id: bool = True) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, vol.UNDEFINED)): str,
    }
    if with_device_id:
        device_id = defaults.get(CONF_DEVICE_ID, vol.UNDEFINED)
        fields[vol.Required(CONF_DEVICE_ID, default=device_id)] = str
    fields[vol.Required(CONF_LOCAL_KEY)] = _PASSWORD
    return vol.Schema(fields)


class E15ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _async_validate(self, data: dict[str, Any]) -> str | None:
        """Return an error key, or None when the mower answered with its battery level."""
        if len(data[CONF_LOCAL_KEY]) != 16:
            return "invalid_local_key"
        try:
            dps = await self.hass.async_add_executor_job(
                probe, data[CONF_HOST], data[CONF_DEVICE_ID], data[CONF_LOCAL_KEY]
            )
        except MowerConnectionError as err:
            _LOGGER.debug("Probe failed: %s", err)
            return "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error while probing the mower")
            return "unknown"
        if DP_BATTERY not in dps:
            return "not_an_e15"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {k: v.strip() for k, v in user_input.items()}
            await self.async_set_unique_id(data[CONF_DEVICE_ID])
            self._abort_if_unique_id_configured()
            if (error := await self._async_validate(data)) is None:
                return self.async_create_entry(title=DEFAULT_TITLE, data=data)
            errors["base"] = error
        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **{k: v.strip() for k, v in user_input.items()}}
            if (error := await self._async_validate(data)) is None:
                return self.async_update_reload_and_abort(entry, data=data)
            errors["base"] = error
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(user_input or dict(entry.data), with_device_id=False),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> E15OptionsFlow:
        return E15OptionsFlow()


class E15OptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_ALLOW_CONTROL, DEFAULT_ALLOW_CONTROL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required(CONF_ALLOW_CONTROL, default=current): bool}),
        )
