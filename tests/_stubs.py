"""Ersatz für Home Assistant, damit sich die Integration ohne Home Assistant testen lässt (nur für Tests)."""
from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "custom_components" / "greenbox"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
MAC1, MAC2, CLOUD_ONLY = "AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02", "11111111-2222-3333-4444-555555555555"
NOW = datetime(2026, 9, 27, 9, tzinfo=timezone.utc)
FAKE_KEY = "AIza" + "x" * 35  # Format des Schlüssels, aber ausgedacht (im Quelltext steht bewusst kein Schlüssel)


def mod(name: str, **kw):
    m = types.ModuleType(name)
    m.__dict__.update(kw)
    sys.modules[name] = m
    return m


class ServiceValidationError(Exception):
    pass


class Store:
    """Speicher je Schlüssel, wie .storage/<key>."""

    data: dict[str, object] = {}

    def __init__(self, hass, version, key):
        self.key = key

    async def async_load(self):
        v = Store.data.get(self.key)
        return json.loads(json.dumps(v)) if v else None

    async def async_save(self, d):
        Store.data[self.key] = json.loads(json.dumps(d))


class Coordinator:
    def __init__(self, hass, log, config_entry=None, name=None, update_method=None, update_interval=None):
        self.data, self._m, self.listeners = None, update_method, []

    async def async_refresh(self):
        self.data = await self._m()

    def async_set_updated_data(self, d):
        self.data = d

    def async_add_listener(self, cb):
        self.listeners.append(cb)
        return lambda: None


class State:
    LOADED, NOT_LOADED = "loaded", "not_loaded"


def install(catalog_dir: Path | None = None) -> None:
    """Legt die Ersatzmodule an (mehrfacher Aufruf ist unkritisch)."""
    mod("homeassistant")
    mod("homeassistant.components")
    ws = mod("homeassistant.components.websocket_api", websocket_command=lambda schema: (lambda f: f), ActiveConnection=object,
             async_register_command=lambda h, f: h.ws.append(f))
    sys.modules["homeassistant.components"].websocket_api = ws
    mod("homeassistant.components.frontend", add_extra_js_url=lambda h, url: h.js.append(url))
    mod("homeassistant.components.http", StaticPathConfig=lambda url, path, cache_headers=True: (url, path))
    bt = mod("homeassistant.components.bluetooth", BluetoothServiceInfoBleak=object, async_discovered_service_info=lambda h, connectable=True: [])
    sys.modules["homeassistant.components"].bluetooth = bt
    mod("homeassistant.config_entries", ConfigEntry=object, ConfigEntryState=State, ConfigFlow=object, ConfigFlowResult=dict, OptionsFlow=object)
    mod("homeassistant.const", CONF_ADDRESS="address", CONF_NAME="name", CONF_EMAIL="email", CONF_PASSWORD="password",
        Platform=types.SimpleNamespace(BINARY_SENSOR="binary_sensor", BUTTON="button", NUMBER="number", SELECT="select", SENSOR="sensor", SWITCH="switch", TIME="time"))
    mod("homeassistant.core", HomeAssistant=object, ServiceCall=object, callback=lambda f: f)
    mod("homeassistant.exceptions", ServiceValidationError=ServiceValidationError)
    mod("homeassistant.helpers")
    cv = mod("homeassistant.helpers.config_validation", string=str)
    sys.modules["homeassistant.helpers"].config_validation = cv
    mod("homeassistant.helpers.aiohttp_client", async_get_clientsession=lambda h: None)
    mod("homeassistant.helpers.storage", Store=Store)
    mod("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=Coordinator)
    mod("homeassistant.loader", async_get_integration=_get_integration)
    mod("homeassistant.util")
    dtu = mod("homeassistant.util.dt", utcnow=lambda: NOW)
    sys.modules["homeassistant.util"].dt = dtu
    mod("aiohttp", ClientSession=object, ClientError=Exception, ClientTimeout=lambda **k: None)


async def _get_integration(hass, domain):
    return types.SimpleNamespace(version="9.9.9")


def package(name: str = "greenbox", *, with_init: bool = False, fake_device=None):
    """Lädt die Integration als Paket. Ohne with_init nur die Untermodule (Logik), mit with_init auch __init__.py."""
    for k in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
        del sys.modules[k]
    if with_init:
        spec = importlib.util.spec_from_file_location(name, PKG / "__init__.py", submodule_search_locations=[str(PKG)])
        pkg = importlib.util.module_from_spec(spec)
        sys.modules[name] = pkg
        if fake_device is not None:
            mod(f"{name}.device", GreenBoxDevice=fake_device)
        spec.loader.exec_module(pkg)
        return pkg
    pkg = types.ModuleType(name)
    pkg.__path__ = [str(PKG)]
    sys.modules[name] = pkg
    return pkg


def slim_catalog() -> dict:
    """Katalog aus den ausgedachten Rohdaten (prüft dabei auch catalog_build.build)."""
    build = importlib.import_module("greenbox.catalog_build").build
    return build(json.loads((FIXTURES / "raw_catalog.json").read_text(encoding="utf-8")))


def raw_catalog() -> dict:
    return json.loads((FIXTURES / "raw_catalog.json").read_text(encoding="utf-8"))
