"""Einrichtung: Bluetooth-Box (automatisch erkannt oder Auswahl) oder das optionale Cloud-Konto der Berlin-Green-App."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak, async_discovered_service_info
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS, CONF_EMAIL, CONF_NAME, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ApiError, ApiKeyError, AuthError, sign_in, valid_key_format
from .hub import CONF_API_KEY, CONF_CANNABIS, CONF_CLOUD

DOMAIN = "greenbox"
PREFIX = "GreenBox"
CLOUD_UNIQUE_ID = "greenbox_cloud"
CLOUD_SCHEMA = vol.Schema({vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str, vol.Required(CONF_API_KEY): str})


class GreenBoxConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None

    # --- Einstieg -------------------------------------------------------------------------------
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        has_cloud = any(e.data.get(CONF_CLOUD) for e in self._async_current_entries())
        return self.async_show_menu(step_id="user", menu_options=["ble"] if has_cloud else ["ble", "cloud"])

    # --- Bluetooth-Box ----------------------------------------------------------------------------
    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._discovery is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovery.name,
                data={CONF_ADDRESS: self._discovery.address, CONF_NAME: self._discovery.name},
            )
        self._set_confirm_only()
        return self.async_show_form(step_id="confirm", description_placeholders={"name": self._discovery.name})

    async def async_step_ble(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        configured = self._async_current_ids()
        found = {
            info.address: info.name
            for info in async_discovered_service_info(self.hass, connectable=True)
            if info.name and info.name.startswith(PREFIX) and info.address not in configured
        }
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=found[address], data={CONF_ADDRESS: address, CONF_NAME: found[address]})
        if not found:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="ble",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In({a: f"{n} ({a})" for a, n in found.items()})}),
        )

    # --- Cloud-Konto (optional; geschrieben wird nur bei Boxen im Cloud-Modus) -------------------------------------------------------
    async def _login(self, email: str, password: str, api_key: str) -> tuple[dict[str, str] | None, dict[str, str]]:
        if not valid_key_format(api_key):
            return None, {CONF_API_KEY: "invalid_api_key"}
        try:
            return await sign_in(async_get_clientsession(self.hass), email.strip(), password, api_key.strip()), {}
        except ApiKeyError:
            return None, {CONF_API_KEY: "invalid_api_key"}
        except AuthError:
            return None, {"base": "invalid_auth"}
        except ApiError:
            return None, {"base": "cannot_connect"}

    async def async_step_cloud(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            result, errors = await self._login(user_input[CONF_EMAIL], user_input[CONF_PASSWORD], user_input[CONF_API_KEY])
            if result:
                await self.async_set_unique_id(CLOUD_UNIQUE_ID)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Berlin Green Cloud",
                    data={CONF_CLOUD: True, CONF_EMAIL: user_input[CONF_EMAIL].strip(), CONF_API_KEY: user_input[CONF_API_KEY].strip(),
                          "refresh_token": result["refresh_token"]},
                )
        return self.async_show_form(step_id="cloud", data_schema=self.add_suggested_values_to_schema(CLOUD_SCHEMA, user_input or {}), errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            result, errors = await self._login(entry.data[CONF_EMAIL], user_input[CONF_PASSWORD], user_input[CONF_API_KEY])
            if result:
                return self.async_update_reload_and_abort(
                    entry, data_updates={"refresh_token": result["refresh_token"], CONF_API_KEY: user_input[CONF_API_KEY].strip()})
        schema = vol.Schema({vol.Required(CONF_PASSWORD): str, vol.Required(CONF_API_KEY, default=entry.data.get(CONF_API_KEY, "")): str})
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=schema, errors=errors, description_placeholders={"email": entry.data[CONF_EMAIL]},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Cloud-Konto wechseln. (Bluetooth-Boxen haben nichts einzustellen; zum Trennen den Eintrag löschen.)"""
        entry = self._get_reconfigure_entry()
        if not entry.data.get(CONF_CLOUD):
            return self.async_abort(reason="reconfigure_not_supported")
        errors: dict[str, str] = {}
        if user_input is not None:
            result, errors = await self._login(user_input[CONF_EMAIL], user_input[CONF_PASSWORD], user_input[CONF_API_KEY])
            if result:
                return self.async_update_reload_and_abort(
                    entry, data={CONF_CLOUD: True, CONF_EMAIL: user_input[CONF_EMAIL].strip(), CONF_API_KEY: user_input[CONF_API_KEY].strip(),
                                 "refresh_token": result["refresh_token"]})
        return self.async_show_form(step_id="reconfigure", errors=errors, data_schema=self.add_suggested_values_to_schema(
            CLOUD_SCHEMA, {CONF_EMAIL: entry.data.get(CONF_EMAIL, ""), CONF_API_KEY: entry.data.get(CONF_API_KEY, "")}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return GreenBoxOptions()


class GreenBoxOptions(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self.config_entry.data.get(CONF_CLOUD):
            return self.async_abort(reason="no_options")
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id="init", data_schema=vol.Schema(
            {vol.Optional(CONF_CANNABIS, default=self.config_entry.options.get(CONF_CANNABIS, False)): bool}))
