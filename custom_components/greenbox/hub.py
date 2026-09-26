"""Garten-Logik für alle GreenBoxen: lokaler Speicher, Katalog, optionale Cloud (lesen; schreiben nur im Cloud-Modus einer Box), Ansicht je Box, Dienste."""
from __future__ import annotations

import asyncio
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

from . import catalog_build, local, photos
from .api import ApiError, ApiKeyError, AuthError, GreenboxCloud
from .garden import HARVEST, build_box, parse_time
from .library import GardenError, Library

DOMAIN = "greenbox"
CONF_CLOUD = "cloud"  # Eintrag ist das (optionale) Cloud-Konto, keine Bluetooth-Box
CONF_API_KEY = "api_key"  # Firebase-API-Schlüssel der App (vom Nutzer eingetragen, siehe tools/extract_key.py)
CONF_CANNABIS = "show_cannabis"
EVENT_HARVEST_READY = "greenbox_harvest_ready"  # Ereignis, wenn ein Topf erntereif wird (für Benachrichtigungen)
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
        self._catalog_attempts = 0  # automatische Versuche, den Katalog zu laden (Fehler dürfen sich wiederholen, aber nicht endlos)
        self.photo_dir = Path(hass.config.path(photos.PHOTO_DIR))
        self.photo_names: set[str] = set()
        self._photo_task: asyncio.Task | None = None
        self.cloud: GreenboxCloud | None = None
        self.raw_cloud: dict[str, dict] = {}
        self._reauth_started = False
        self._boxes: set[str] = set()
        self._ready: set[tuple[str, str, int]] | None = None  # aktuell erntereife Töpfe (None = noch nicht ausgewertet)
        self.coordinator: DataUpdateCoordinator = DataUpdateCoordinator(
            hass, _LOGGER, config_entry=None, name="greenbox garden", update_method=self._update, update_interval=UPDATE_INTERVAL)

    # --- Einrichtung ----------------------------------------------------------------------------
    async def async_init(self) -> None:
        self.local = await self.store.async_load() or {"boxes": {}}
        self.local.setdefault("boxes", {})
        self.local.setdefault("cloud_sync", [])
        self.lib = await self._load_catalog()
        self.photo_names = await self.hass.async_add_executor_job(photos.existing, self.photo_dir)
        self.configure()
        await self.coordinator.async_refresh()
        self.start_photo_sync()  # Fotos des vorhandenen Katalogs im Hintergrund nachladen

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

    # --- Fotos (lokal zwischengespeichert, siehe photos.py) -----------------------------------------
    def local_photo(self, url: str | None) -> str | None:
        """Lokale Adresse eines Fotos, wenn es schon heruntergeladen ist; sonst die Originaladresse."""
        if url and photos.file_name(url) in self.photo_names:
            return f"{photos.PHOTO_URL}/{photos.file_name(url)}"
        return url

    def start_photo_sync(self) -> None:
        if self.lib.is_empty or (self._photo_task and not self._photo_task.done()):
            return
        self._photo_task = self.hass.async_create_background_task(self.async_sync_photos(), "greenbox photos")

    async def async_sync_photos(self) -> tuple[int, int]:
        urls = photos.collect_urls(self.lib.data)
        result = await photos.sync(async_get_clientsession(self.hass), self.photo_dir, urls, self.hass.async_add_executor_job)
        self.photo_names = await self.hass.async_add_executor_job(photos.existing, self.photo_dir)
        if result[0]:
            self.refresh()
        if result[1]:
            _LOGGER.warning("%d Foto(s) konnten nicht geladen werden (die Karte zeigt dafür die Originaladresse)", result[1])
        return result

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
        self.start_photo_sync()
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
                if self.lib.is_empty and self._catalog_attempts < 3:  # ohne Katalog automatisch (bis zu dreimal) versuchen
                    self._catalog_attempts += 1
                    try:
                        await self.async_update_catalog(refresh=False)
                    except GardenError as err:
                        _LOGGER.warning("Katalog nicht geladen: %s", err)
        views = self.views()
        self._detect_harvest(views)
        return views

    def _detect_harvest(self, views: dict[str, dict[str, Any]]) -> None:
        """Feuert greenbox_harvest_ready für jeden Topf, der seit der letzten Auswertung erntereif geworden ist.
        Beim ersten Mal (Start von Home Assistant) wird nur der Stand gemerkt, damit ein Neustart nicht alle bereits reifen Töpfe meldet."""
        ready: dict[tuple[str, str, int], dict[str, Any]] = {}
        for key, view in views.items():
            for area, slots in (("plants", view.get("slots") or []), ("microgreens", view.get("microgreens") or []),
                                ("mushrooms", view.get("mushrooms") or [])):
                for s in slots:
                    if s.get("phase") == HARVEST:
                        ready[(key, area, s["slot"])] = {"box": key, "box_name": view["name"], "area": area, "slot": s["slot"] + 1,
                                                          "plant": s.get("plant"), "plant_id": s.get("plant_id")}
        previous, self._ready = self._ready, set(ready)
        known, self._boxes = self._boxes, set(views)
        if previous is None:
            return
        for k in sorted(set(ready) - previous):
            if k[0] in known:  # eine Box, die erst jetzt auftaucht (z. B. Cloud war beim Start offline), meldet ihren Bestand nicht
                self.hass.bus.async_fire(EVENT_HARVEST_READY, ready[k])

    # --- Ansicht --------------------------------------------------------------------------------
    def ble_boxes(self) -> dict[str, str]:
        return {e.data[CONF_ADDRESS]: (e.data.get(CONF_NAME) or e.title) for e in self.box_entries() if e.data.get(CONF_ADDRESS)}

    def views(self) -> dict[str, dict[str, Any]]:
        now, ble = dt_util.utcnow(), self.ble_boxes()
        out: dict[str, dict[str, Any]] = {}
        for key in dict.fromkeys([*self.raw_cloud, *ble, *self.local["boxes"]]):
            rec = self.local["boxes"].get(key)
            if self.synced(key):
                shape, source = self.raw_cloud[key], "cloud"
            elif rec:
                shape, source = local.to_cloud_shape(key, rec), "local"
            elif key in self.raw_cloud:
                shape, source = self.raw_cloud[key], "cloud"
            else:
                shape, source = local.to_cloud_shape(key, local.new_box(ble.get(key, key))), "local"
            view = build_box(shape, now, self.language, self.local_photo)
            view.update(source=source, box_key=key, ble=key in ble, cloud_id=(self.raw_cloud.get(key) or {}).get("id"), sync=self.synced(key))
            out[key] = view
        return out

    # --- Cloud-Modus: Änderungen dieser Box gehen an die Cloud (und damit in die App) -----------------
    def synced(self, key: str) -> bool:
        """Cloud-Modus ist für die Box an UND die Cloud kennt sie (sonst gilt vorübergehend der lokale Stand)."""
        return key in self.local.get("cloud_sync", []) and key in self.raw_cloud

    async def async_set_sync(self, key: str, on: bool) -> None:
        if on and (self.cloud is None or key not in self.raw_cloud):
            raise ServiceValidationError("Dafür muss das Cloud-Konto verbunden sein und die Box kennen")
        keys = self.local.setdefault("cloud_sync", [])
        if on and key not in keys:
            keys.append(key)
        elif not on and key in keys:
            keys.remove(key)
        await self.store.async_save(self.local)
        self.refresh()

    async def _cloud_write(self, name: str, key: str, data: dict[str, Any]) -> None:
        """Führt einen Dienst im Cloud-Modus aus: prüfen (wie lokal), an die Cloud schicken, Stand neu laden."""
        raw = self.raw_cloud[key]
        if self.cloud is None:
            raise GardenError("Cloud-Konto nicht verbunden")
        lib, temp = self.lib, local.from_cloud_shape(raw)  # Kopie des Cloud-Stands: dieselben Regeln/Fehlermeldungen wie lokal
        packages = [p for p in raw.get("packages") or [] if p.get("id") is not None]
        configs = [c for c in raw.get("microgreen_configs") or [] if c.get("id")]
        mushroom_configs = [c for c in raw.get("mushroom_config") or [] if c.get("id")]
        ops: list[tuple[str, dict[str, Any]]] = []
        own = "Im Cloud-Modus gibt es wie in der App ein Paket je Box und nur Katalog-Pflanzen"
        if name == "plant_package":
            if data.get("mix") is None:
                raise GardenError(f"{own}: bitte einen Mix angeben (kein eigener Zeitplan)")
            local.plant_package(temp, lib, mix=data["mix"], slots=data.get("plants"), planted_at=self._when(data.get("planted_at")))
            pkg = temp["package"]
            planted = [{"slot": int(s), "plant_id": e["plant_id"]} for s, e in sorted(pkg["slots"].items(), key=lambda kv: int(kv[0]))]
            if not planted or any(p["plant_id"] is None for p in planted):
                raise GardenError(f"{own}: mindestens eine Katalog-Pflanze angeben")
            layout = (packages[0].get("layout") if packages else None) or "EightSlot"
            ops.append(("plant_new", {"boxId": raw["id"], "mixId": pkg["mix_id"], "plantedAt": pkg["planted_at"], "layout": layout, "planted": planted}))
            if packages:  # erst das neue Paket anlegen, dann das alte abschließen: bei einem Fehler geht nichts verloren
                ops.append(("remove_packages", {"ids": [p["id"] for p in packages], "removedAt": local._now_iso()}))
            if mushroom_configs:  # wie in der App ersetzt ein neues Paket den Pilz
                ops.append(("delete_mushroom_config", {"boxId": raw["id"]}))
        elif name == "plant_slot":
            if any(data.get(k) is not None for k in ("mix", "germination_days", "growth_days", "harvest_days", "planted_at")):
                raise GardenError(f"{own}: ein eigenes Paket je Slot gibt es nur im lokalen Modus")
            if not packages:
                raise GardenError("Es ist noch kein Paket gepflanzt - zuerst 'plant_package' verwenden")
            local.plant_slot(temp, lib, data["slot"], data["plant"])
            idx = int(data["slot"]) - 1
            plant_id = temp["package"]["slots"][str(idx)]["plant_id"]
            if plant_id is None:
                raise GardenError(f"{own}: '{data['plant']}' ist keine Katalog-Pflanze")
            holder = next((p for p in packages if any(i.get("slot") == idx for i in p.get("planted") or [])), None)
            ops.append(("update_slot" if holder else "insert_slot", {"packageId": (holder or packages[0])["id"], "slot": idx, "plantId": plant_id}))
        elif name == "clear_slot":
            raise GardenError("Im Cloud-Modus lassen sich Slots nur ersetzen (die App kann sie auch nicht leeren); zum Leeren das Paket entfernen")
        elif name == "remove_package":
            if not packages:
                raise GardenError("Es ist kein Paket gepflanzt")
            ops.append(("remove_packages", {"ids": [p["id"] for p in packages], "removedAt": local._now_iso()}))
        elif name == "plant_microgreen":
            local.plant_microgreen(temp, lib, data["slot"], data["microgreen"], self._day(data.get("planted_on")), data.get("sprout_days"), data.get("growth_days"))
            idx = int(data["slot"]) - 1
            item = temp["microgreens"][str(idx)]
            if item["microgreen_id"] is None:
                raise GardenError(f"{own}: '{data['microgreen']}' ist kein Katalog-Microgreen")
            new = {"microgreen_id": item["microgreen_id"], "plantedOnDay": item["planted_on"], "slot": idx}
            if not configs:
                ops.append(("set_microgreen_config", {"boxId": raw["id"], "planted_microgreens": [new]}))
            else:
                cfg = configs[0]
                if any(m.get("slot") == idx for m in cfg.get("planted_microgreens") or []):
                    ops.append(("delete_microgreen", {"microgreenConfigId": cfg["id"], "slot": idx}))
                ops.append(("add_microgreen", {"microgreenConfigId": cfg["id"], "microgreenId": new["microgreen_id"], "plantedOnDay": new["plantedOnDay"], "slot": idx}))
        elif name == "clear_microgreen":
            local.clear_microgreen(temp, data.get("slot"))
            if data.get("slot") is None:
                ops += [("delete_module", {"id": c["id"]}) for c in configs]
            else:
                idx = int(data["slot"]) - 1
                ops += [("delete_microgreen", {"microgreenConfigId": c["id"], "slot": idx}) for c in configs
                        if any(m.get("slot") == idx for m in c.get("planted_microgreens") or [])]
        elif name == "clear_mushroom":
            if not mushroom_configs:
                raise GardenError("Es ist kein Pilz gepflanzt")
            ops.append(("delete_mushroom_config", {"boxId": raw["id"]}))
        else:
            raise GardenError("Diesen Dienst gibt es im Cloud-Modus nicht")
        try:
            for op, variables in ops:
                await self.cloud.mutate(op, variables)
            fresh = await self.cloud.fetch()  # danach der Stand, wie ihn die Cloud jetzt hat
        except (AuthError, ApiKeyError) as err:
            raise GardenError(f"Anmeldung abgelehnt: {err}") from err
        except ApiError as err:
            raise GardenError(f"Die Cloud hat die Änderung nicht angenommen: {err}") from err
        self.raw_cloud = {b["box_id"]: b for b in fresh.get("box", [])}
        self.refresh()

    def keys_for(self, entry: ConfigEntry) -> list[str]:
        """Welche Gärten legt dieser Eintrag an? Bluetooth-Box: ihren eigenen. Cloud-Konto: nur Boxen, die keine Bluetooth-Box haben."""
        if not entry.data.get(CONF_CLOUD):
            return [entry.data[CONF_ADDRESS]]
        ble = set(self.ble_boxes())
        return [k for k in (self.coordinator.data or {}) if k not in ble]

    def refresh(self) -> None:
        views = self.views()
        self._detect_harvest(views)
        self.coordinator.async_set_updated_data(views)

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
            if self.synced(key):
                if name == "import_from_cloud":
                    raise GardenError("Diese Box ist mit der Cloud synchronisiert: ihr Stand ist schon der Stand der Cloud")
                await self._cloud_write(name, key, data)
                return
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
                    schedule = None
                    if data.get("mix") is None and any(data.get(k) is not None for k in ("germination_days", "growth_days", "harvest_days")):
                        schedule = [data.get("germination_days"), data.get("growth_days"), data.get("harvest_days")]
                        if any(x is None for x in schedule):
                            raise GardenError("Ein eigener Zeitplan braucht germination_days, growth_days und harvest_days")
                    local.plant_slot(rec, lib, data["slot"], data["plant"], mix=data.get("mix"), schedule=schedule,
                                     planted_at=self._when(data.get("planted_at")))
                elif name == "clear_slot":
                    local.clear_slot(rec, data["slot"])
                elif name == "remove_package":
                    local.remove_package(rec)
                elif name == "plant_microgreen":
                    local.plant_microgreen(rec, lib, data["slot"], data["microgreen"], self._day(data.get("planted_on")),
                                           data.get("sprout_days"), data.get("growth_days"))
                elif name == "clear_microgreen":
                    local.clear_microgreen(rec, data.get("slot"))
                elif name == "clear_mushroom":
                    local.clear_mushrooms(rec)
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
