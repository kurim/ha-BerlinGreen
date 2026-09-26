"""Garten-Logik für alle GreenBoxen: lokaler Speicher, Katalog, optionale Cloud (nur lesend), Ansicht je Box, Dienste."""
from __future__ import annotations

import copy
import json
from datetime import timedelta
import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import catalog_build, local
from .api import ApiError, ApiKeyError, AuthError, GreenboxCloud
from .garden import build_box, parse_time
from .library import GardenError, Library

DOMAIN = "greenbox"
CONF_CLOUD = "cloud"  # Eintrag ist das (optionale) Cloud-Konto, keine Bluetooth-Box
CONF_API_KEY = "api_key"  # Firebase-API-Schlüssel der App (vom Nutzer eingetragen, siehe tools/extract_key.py)
CONF_CANNABIS = "show_cannabis"
CATALOG_FILE = "greenbox_catalog.json"  # optional im Home-Assistant-Ordner (siehe tools/make_catalog.py)
UPDATE_INTERVAL = timedelta(minutes=15)  # Cloud selten abfragen (inoffizielle API); lokale Änderungen wirken sofort
_LOGGER = logging.getLogger(__name__)


class Garden:
    """Ein Objekt für die ganze Integration; wird beim ersten Eintrag angelegt und vom Rest mitgenutzt."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        # gleicher Speicherort wie in der früheren Einzel-Integration -> vorhandene Bepflanzung bleibt erhalten
        self.store: Store = Store(hass, 1, "greenbox_garden_local")
        self.catalog_store: Store = Store(hass, 1, "greenbox_catalog")
        self.local: dict[str, Any] = {"boxes": {}}
        self.lib: Library = Library.empty()
        self._catalog_tried = False
        self.cloud: GreenboxCloud | None = None
        self.raw_cloud: dict[str, dict] = {}
        self._reauth_started = False
        self.coordinator: DataUpdateCoordinator = DataUpdateCoordinator(
            hass, _LOGGER, config_entry=None, name="greenbox garden", update_method=self._update, update_interval=UPDATE_INTERVAL)

    # --- Einrichtung ----------------------------------------------------------------------------
    async def async_init(self) -> None:
        self.local = await self.store.async_load() or {"boxes": {}}
        self.local.setdefault("boxes", {})
        self.lib = await self._load_catalog()
        self.configure()
        await self.coordinator.async_refresh()

    async def _load_catalog(self) -> Library:
        """Katalog: zuerst der gespeicherte (aus der Cloud geladene), dann die Datei im HA-Ordner, sonst leer."""
        data = await self.catalog_store.async_load()
        if not Library.valid(data):
            data = await self.hass.async_add_executor_job(self._read_catalog_file)
        return Library(data) if Library.valid(data) else Library.empty()

    def _read_catalog_file(self) -> dict | None:
        path = Path(self.hass.config.path(CATALOG_FILE))
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        except (OSError, ValueError) as err:
            _LOGGER.warning("Katalogdatei %s nicht lesbar: %s", path, err)
            return None

    async def async_update_catalog(self, refresh: bool = True) -> int:
        """Katalog aus dem verbundenen Cloud-Konto laden und dauerhaft speichern. Liefert die Zahl der Pflanzen."""
        if self.cloud is None:
            raise GardenError("Dafür wird das Cloud-Konto benötigt (Integration hinzufügen -> Cloud-Konto), "
                              f"oder die Datei {CATALOG_FILE} in den Home-Assistant-Ordner legen")
        try:
            raw = await self.cloud.fetch_catalog()
        except (AuthError, ApiKeyError) as err:
            raise GardenError(f"Anmeldung abgelehnt: {err}") from err
        except ApiError as err:
            raise GardenError(f"Katalog konnte nicht geladen werden: {err}") from err
        data = catalog_build.build(raw)
        if not Library.valid(data) or not data["mixes"] or not data["plants"]:
            raise GardenError("Die Cloud lieferte keinen brauchbaren Katalog")
        await self.catalog_store.async_save(data)
        self.lib = Library(data, self.lib.allow_cannabis)
        if refresh:
            self.refresh()
        return len(data["plants"])

    def entries(self) -> list[ConfigEntry]:
        return list(self.hass.config_entries.async_entries(DOMAIN))

    def cloud_entry(self) -> ConfigEntry | None:
        return next((e for e in self.entries() if e.data.get(CONF_CLOUD)), None)

    def box_entries(self) -> list[ConfigEntry]:
        return [e for e in self.entries() if not e.data.get(CONF_CLOUD)]

    def configure(self) -> None:
        """Liest Cloud-Eintrag und Optionen neu ein (nach Hinzufügen/Entfernen/Ändern eines Eintrags)."""
        entry = self.cloud_entry()
        token = entry.data.get("refresh_token") if entry else None
        key = entry.data.get(CONF_API_KEY) if entry else None
        if not token or not key:
            self.cloud, self.raw_cloud = None, {}
            if entry and token and not key and not self._reauth_started:
                # Eintrag aus Version 0.5.0: der API-Schlüssel wird jetzt abgefragt
                self._reauth_started = True
                _LOGGER.warning("Cloud-Konto: bitte den API-Schlüssel der App eintragen (Reparaturhinweis in Home Assistant)")
                entry.async_start_reauth(self.hass)
        elif self.cloud is None or self.cloud.refresh_token != token or self.cloud.api_key != key:
            self.cloud = GreenboxCloud(async_get_clientsession(self.hass), token, key)
            self._reauth_started = False
        self.lib.allow_cannabis = any(e.options.get(CONF_CANNABIS) for e in self.box_entries())

    @property
    def language(self) -> str:
        return "de" if self.hass.config.language.startswith("de") else "en"

    async def _update(self) -> dict[str, Any]:
        """Cloud nur lesen; Fehler dort dürfen die lokale Bepflanzung nie unbrauchbar machen."""
        entry = self.cloud_entry()
        if self.cloud and entry:
            try:
                raw = await self.cloud.fetch()
                self.raw_cloud = {b["box_id"]: b for b in raw.get("box", [])}
                if self.cloud.refresh_token != entry.data.get("refresh_token"):  # Google kann das Token erneuern
                    self.hass.config_entries.async_update_entry(entry, data={**entry.data, "refresh_token": self.cloud.refresh_token})
            except (AuthError, ApiKeyError) as err:
                _LOGGER.warning("Cloud-Anmeldung abgelehnt: %s", err)
                if not self._reauth_started:
                    self._reauth_started = True
                    entry.async_start_reauth(self.hass)
            except ApiError as err:
                _LOGGER.warning("Cloud nicht erreichbar, verwende letzten Stand: %s", err)
            else:
                if self.lib.is_empty and not self._catalog_tried:  # einmal automatisch versuchen
                    self._catalog_tried = True
                    try:
                        await self.async_update_catalog(refresh=False)
                    except GardenError as err:
                        _LOGGER.warning("Katalog nicht geladen: %s", err)
        return self.views()

    # --- Ansicht --------------------------------------------------------------------------------
    def ble_boxes(self) -> dict[str, str]:
        return {e.data[CONF_ADDRESS]: (e.data.get(CONF_NAME) or e.title) for e in self.box_entries() if e.data.get(CONF_ADDRESS)}

    def views(self) -> dict[str, dict[str, Any]]:
        now, ble = dt_util.utcnow(), self.ble_boxes()
        out: dict[str, dict[str, Any]] = {}
        for key in dict.fromkeys([*self.raw_cloud, *ble, *self.local["boxes"]]):
            rec = self.local["boxes"].get(key)
            if rec:
                shape, source = local.to_cloud_shape(key, rec), "local"
            elif key in self.raw_cloud:
                shape, source = self.raw_cloud[key], "cloud"
            else:
                shape, source = local.to_cloud_shape(key, local.new_box(ble.get(key, key))), "local"
            view = build_box(shape, now, self.language)
            view.update(source=source, box_key=key, ble=key in ble, cloud_id=(self.raw_cloud.get(key) or {}).get("id"))
            out[key] = view
        return out

    def keys_for(self, entry: ConfigEntry) -> list[str]:
        """Welche Gärten legt dieser Eintrag an? Bluetooth-Box: ihren eigenen. Cloud-Konto: nur Boxen, die keine Bluetooth-Box haben."""
        if not entry.data.get(CONF_CLOUD):
            return [entry.data[CONF_ADDRESS]]
        ble = set(self.ble_boxes())
        return [k for k in (self.coordinator.data or {}) if k not in ble]

    def refresh(self) -> None:
        self.coordinator.async_set_updated_data(self.views())

    # --- Dienste --------------------------------------------------------------------------------
    def resolve(self, ref: str | None) -> str:
        views = self.coordinator.data or {}
        if not ref:
            if len(views) == 1:
                return next(iter(views))
            raise GardenError("Bitte 'box' angeben. Verfügbar: " + ", ".join(f"{v['name']} ({k})" for k, v in views.items()))
        text = ref.strip().lower()
        for key, v in views.items():
            if text in (key.lower(), str(v["name"]).lower()):
                return key
        raise GardenError(f"Box '{ref}' nicht gefunden. Verfügbar: " + ", ".join(f"{v['name']} ({k})" for k, v in views.items()))

    def record(self, key: str) -> dict[str, Any]:
        """Lokaler Datensatz; existiert er noch nicht, startet er mit dem Stand der Cloud (falls vorhanden)."""
        rec = self.local["boxes"].get(key)
        if rec is None:
            view = (self.coordinator.data or {}).get(key, {})
            rec = local.from_cloud_shape(self.raw_cloud[key]) if key in self.raw_cloud else local.new_box(view.get("name", key))
            self.local["boxes"][key] = rec
        return rec

    async def call(self, name: str, data: dict[str, Any]) -> None:
        snapshot = copy.deepcopy(self.local)  # bei einem Fehler wird nichts halb gespeichert
        try:
            if name == "update_catalog":
                await self.async_update_catalog()
                return
            key = self.resolve(data.get("box"))
            if name == "import_from_cloud":
                if key not in self.raw_cloud:
                    raise GardenError("Diese Box gibt es nicht in der Cloud (oder es ist kein Cloud-Konto verbunden)")
                self.local["boxes"][key] = local.from_cloud_shape(self.raw_cloud[key])
            else:
                rec, lib = self.record(key), self.lib
                if name == "plant_package":
                    schedule = None
                    if data.get("mix") is None:
                        schedule = [data.get("germination_days"), data.get("growth_days"), data.get("harvest_days")]
                        if any(x is None for x in schedule):
                            raise GardenError("Ohne Mix bitte germination_days, growth_days und harvest_days angeben")
                    local.plant_package(rec, lib, mix=data.get("mix"), schedule=schedule, slots=data.get("plants"),
                                        planted_at=self._when(data.get("planted_at")))
                elif name == "plant_slot":
                    local.plant_slot(rec, lib, data["slot"], data["plant"])
                elif name == "clear_slot":
                    local.clear_slot(rec, data["slot"])
                elif name == "remove_package":
                    local.remove_package(rec)
                elif name == "plant_microgreen":
                    local.plant_microgreen(rec, lib, data["slot"], data["microgreen"], self._day(data.get("planted_on")),
                                           data.get("sprout_days"), data.get("growth_days"))
                elif name == "clear_microgreen":
                    local.clear_microgreen(rec, data.get("slot"))
        except GardenError as err:
            self.local = snapshot
            raise ServiceValidationError(str(err)) from err
        await self.store.async_save(self.local)
        self.refresh()

    @staticmethod
    def _when(value: str | None) -> str | None:
        if not value:
            return None
        parsed = parse_time(value)
        if parsed is None:
            raise GardenError(f"Ungültiges Datum '{value}' (Format JJJJ-MM-TT)")
        return parsed.isoformat()

    @staticmethod
    def _day(value: str | None) -> str | None:
        if not value:
            return None
        parsed = parse_time(value)
        if parsed is None:
            raise GardenError(f"Ungültiges Datum '{value}' (Format JJJJ-MM-TT)")
        return parsed.date().isoformat()
