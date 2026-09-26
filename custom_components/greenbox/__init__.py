"""Berlin Green GreenBox: Bluetooth-Steuerung je Box und ein gemeinsamer Garten (lokal; Cloud optional: lesen, und je Box im Cloud-Modus auch schreiben)."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.loader import async_get_integration

from .device import GreenBoxDevice
from .hub import CONF_CLOUD, DOMAIN, Garden
from .photos import PHOTO_URL

_LOGGER = logging.getLogger(__name__)
BOX_PLATFORMS = [Platform.BUTTON, Platform.NUMBER, Platform.SELECT, Platform.SENSOR, Platform.SWITCH, Platform.TIME]
CLOUD_PLATFORMS = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]
GARDEN = "_garden"
LOCK = "_lock"
FRONTEND = "_frontend"
CARD_URL = "/greenbox_static"
CARD_FILE = "greenbox-garden-card.js"

BOX = {vol.Optional("box"): cv.string}
SERVICES: dict[str, vol.Schema] = {
    "plant_package": vol.Schema({
        **BOX,
        vol.Optional("mix"): vol.Any(cv.string, int),
        vol.Optional("germination_days"): vol.Coerce(float), vol.Optional("growth_days"): vol.Coerce(float),
        vol.Optional("harvest_days"): vol.Coerce(float),
        vol.Optional("plants"): {vol.Coerce(int): vol.Any(cv.string, int)},
        vol.Optional("planted_at"): cv.string,
    }),
    "plant_slot": vol.Schema({
        **BOX, vol.Required("slot"): vol.Coerce(int), vol.Required("plant"): vol.Any(cv.string, int),
        vol.Optional("mix"): vol.Any(cv.string, int),
        vol.Optional("germination_days"): vol.Coerce(float), vol.Optional("growth_days"): vol.Coerce(float),
        vol.Optional("harvest_days"): vol.Coerce(float), vol.Optional("planted_at"): cv.string,
    }),
    "clear_slot": vol.Schema({**BOX, vol.Required("slot"): vol.Coerce(int)}),
    "remove_package": vol.Schema({**BOX}),
    "plant_microgreen": vol.Schema({**BOX, vol.Required("slot"): vol.Coerce(int), vol.Required("microgreen"): vol.Any(cv.string, int),
                                    vol.Optional("planted_on"): cv.string,
                                    vol.Optional("sprout_days"): vol.Coerce(float), vol.Optional("growth_days"): vol.Coerce(float)}),
    "clear_microgreen": vol.Schema({**BOX, vol.Optional("slot"): vol.Coerce(int)}),
    "clear_mushroom": vol.Schema({**BOX}),
    "import_from_cloud": vol.Schema({**BOX}),
    "update_catalog": vol.Schema({}),
}


async def _add_lovelace_resource(hass: HomeAssistant, url: str) -> bool:
    """Trägt die Karte bei den Dashboard-Ressourcen ein (wie HACS es für Karten tut; nur im Speichermodus möglich).

    Ohne Aufruf von Hand steht sie dann unter Einstellungen -> Dashboards -> Ressourcen. Bei neuer Version wird die Adresse aktualisiert."""
    data = hass.data.get("lovelace")
    resources = data.get("resources") if isinstance(data, dict) else getattr(data, "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        return False  # YAML-Modus oder Lovelace nicht geladen
    if not getattr(resources, "loaded", True):
        await resources.async_load()
    base = url.split("?")[0]
    for item in resources.async_items():
        if item.get("url", "").split("?")[0] == base:
            if item["url"] != url:
                await resources.async_update_item(item["id"], {"res_type": "module", "url": url})
            return True
    await resources.async_create_item({"res_type": "module", "url": url})
    return True


async def _register_card(hass: HomeAssistant, root: dict, garden: Garden) -> None:
    """Die Karte gehört zur Integration und wird automatisch geladen (keine Ressource von Hand eintragen)."""
    if root.get(FRONTEND):
        return
    root[FRONTEND] = True  # Pfade lassen sich nur einmal registrieren, auch nicht nach einem Neuladen
    try:
        integration = await async_get_integration(hass, DOMAIN)
        await hass.async_add_executor_job(lambda: garden.photo_dir.mkdir(parents=True, exist_ok=True))
        await hass.http.async_register_static_paths([
            StaticPathConfig(CARD_URL, str(Path(__file__).parent / "frontend"), cache_headers=False),
            StaticPathConfig(PHOTO_URL, str(garden.photo_dir), cache_headers=True),  # Dateinamen sind Hashes der Adresse
        ])
        card = f"{CARD_URL}/{CARD_FILE}?v={integration.version}"
        try:
            registered = await _add_lovelace_resource(hass, card)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Dashboard-Ressource konnte nicht angelegt werden")
            registered = False
        if not registered:  # z. B. Dashboards im YAML-Modus: die Karte wird stattdessen auf jeder Seite geladen
            add_extra_js_url(hass, card)
    except Exception:  # noqa: BLE001 - die Steuerung darf nie an der Karte scheitern
        _LOGGER.exception("Karte konnte nicht registriert werden; Ressource /local/... von Hand eintragen")


async def _get_garden(hass: HomeAssistant) -> Garden:
    """Legt den gemeinsamen Garten beim ersten Eintrag an (mehrere Einträge starten gleichzeitig -> Sperre)."""
    root = hass.data.setdefault(DOMAIN, {})
    lock: asyncio.Lock = root.setdefault(LOCK, asyncio.Lock())
    async with lock:
        garden: Garden | None = root.get(GARDEN)
        if garden is None:
            garden = Garden(hass)
            await garden.async_init()
            root[GARDEN] = garden

            def make_handler(name: str):
                async def handler(call: ServiceCall) -> None:
                    g = hass.data.get(DOMAIN, {}).get(GARDEN)
                    if g is None:
                        raise ServiceValidationError("Garten ist nicht eingerichtet")
                    await g.call(name, dict(call.data))
                return handler

            for name, schema in SERVICES.items():
                hass.services.async_register(DOMAIN, name, make_handler(name), schema=schema)
            websocket_api.async_register_command(hass, ws_catalog)
            await _register_card(hass, root, garden)
        return garden


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    garden = await _get_garden(hass)
    if entry.data.get(CONF_CLOUD):
        garden.configure()
        await garden.coordinator.async_refresh()
        platforms = CLOUD_PLATFORMS
    else:
        device = GreenBoxDevice(hass, entry.data[CONF_ADDRESS], entry.data.get(CONF_NAME) or entry.title)
        hass.data[DOMAIN][entry.entry_id] = device
        await device.async_start()
        garden.configure()
        garden.refresh()
        platforms = BOX_PLATFORMS
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    entry.async_on_unload(entry.add_update_listener(lambda h, e: h.config_entries.async_schedule_reload(e.entry_id)))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    platforms = CLOUD_PLATFORMS if entry.data.get(CONF_CLOUD) else BOX_PLATFORMS
    if not await hass.config_entries.async_unload_platforms(entry, platforms):
        return False
    root = hass.data[DOMAIN]
    if device := root.pop(entry.entry_id, None):
        await device.async_stop()
    others = [e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id and e.state is ConfigEntryState.LOADED]
    if others:
        if garden := root.get(GARDEN):
            garden.configure()
            garden.refresh()
    else:  # letzter Eintrag: Dienste entfernen und Garten freigeben
        for name in SERVICES:
            hass.services.async_remove(DOMAIN, name)
        root.pop(GARDEN, None)
    return True


@websocket_api.websocket_command({vol.Required("type"): "greenbox/catalog"})
@callback
def ws_catalog(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Katalog für die Card (Mixe mit ihren Pflanzen, Microgreens). Cannabis nur, wenn in den Optionen erlaubt."""
    garden: Garden | None = hass.data.get(DOMAIN, {}).get(GARDEN)
    if garden is None:
        connection.send_error(msg["id"], "not_loaded", "Garten ist nicht eingerichtet")
        return
    connection.send_result(msg["id"], garden.lib.public(garden.language, garden.local_photo))
