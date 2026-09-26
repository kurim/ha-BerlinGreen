"""Kern der Integration: Einträge, gemeinsamer Garten, Dienste, Katalog, Karte, Cloud-Fehler.   python tests/test_hub.py"""
import asyncio
import importlib
import json
import sys
import tempfile
from pathlib import Path

import _stubs
from _stubs import FAKE_KEY, MAC1, MAC2, CLOUD_ONLY, State, Store, ServiceValidationError

_stubs.install()


class FakeDevice:
    started: list = []

    def __init__(self, hass, address, name):
        self.address, self.name = address, name
        self.state = type("S", (), {"firmware_name": "1.0"})()

    async def async_start(self):
        FakeDevice.started.append(self.address)

    async def async_stop(self):
        FakeDevice.started.remove(self.address)


gb = _stubs.package(with_init=True, fake_device=FakeDevice)
hub = importlib.import_module("greenbox.hub")
api = importlib.import_module("greenbox.api")
CONFIG_DIR = Path(tempfile.mkdtemp())


class Cfg:
    language = "de"

    @staticmethod
    def path(name):
        return str(CONFIG_DIR / name)


class Entry:
    n = 0

    def __init__(self, data, title="t", options=None):
        Entry.n += 1
        self.entry_id, self.data, self.title, self.options = f"e{Entry.n}", data, title, options or {}
        self.state, self.reauth = State.LOADED, 0

    def async_on_unload(self, fn): pass
    def add_update_listener(self, fn): return lambda: None
    def async_start_reauth(self, hass): self.reauth += 1


class ConfigEntries:
    def __init__(self): self.entries, self.forwarded, self.updated = [], [], []
    def async_entries(self, domain): return list(self.entries)
    async def async_forward_entry_setups(self, e, p): self.forwarded.append((e.entry_id, list(p)))
    async def async_unload_platforms(self, e, p): return True
    def async_update_entry(self, e, data=None): self.updated.append(data); e.data = data
    def async_schedule_reload(self, i): pass


class Services:
    def __init__(self): self.h, self.reg = {}, 0
    def async_register(self, d, n, h, schema=None): self.h[(d, n)] = h; self.reg += 1
    def async_remove(self, d, n): self.h.pop((d, n), None)


class Http:
    def __init__(self): self.paths = []
    async def async_register_static_paths(self, cfgs): self.paths += cfgs


class Hass:
    def __init__(self):
        self.data, self.config, self.config_entries, self.services = {}, Cfg(), ConfigEntries(), Services()
        self.ws, self.js, self.http = [], [], Http()

    async def async_add_executor_job(self, f, *a): return f(*a)
    def async_create_background_task(self, coro, name): return asyncio.ensure_future(coro)


def types_ns(**kw):
    import types
    return types.SimpleNamespace(**kw)


class Call:
    def __init__(self, data): self.data = data


def box(key, name):
    return {"id": "u" + key, "box_id": key, "name": name, "type": "Standard", "packages": [], "microgreen_configs": [], "mushroom_config": []}


class FakeCloud:
    instances = []
    def __init__(self, session, token, key):
        self.refresh_token, self.api_key, self.mode, self.catalog_calls = token, key, "ok", 0
        FakeCloud.instances.append(self)
    async def fetch(self):
        if self.mode == "auth": raise api.AuthError("TOKEN_EXPIRED")
        if self.mode == "key": raise api.ApiKeyError("API key not valid")
        if self.mode == "net": raise api.ApiError("offline")
        self.refresh_token = "ROTATED"
        return {"box": [box(MAC1, "Cloud name"), box(CLOUD_ONLY, "Andere Box")]}
    async def fetch_catalog(self):
        self.catalog_calls += 1
        if self.mode == "auth": raise api.AuthError("TOKEN_EXPIRED")
        if self.mode == "key": raise api.ApiKeyError("API key not valid")
        if self.mode == "net": raise api.ApiError("offline")
        return _stubs.raw_catalog()


hub.GreenboxCloud = FakeCloud
fails = 0


def check(cond, msg):
    global fails
    print(("  ok    " if cond else "  FEHLT ") + msg)
    fails += not cond


async def expect(coro, part):
    try:
        await coro
    except ServiceValidationError as e:
        return part in str(e)
    return False


async def main():
    Store.data = {}
    h = Hass()
    e1, e2 = Entry({"address": MAC1, "name": "GreenBoxOne"}, "GreenBoxOne"), Entry({"address": MAC2, "name": "GreenBoxTwo"}, "GreenBoxTwo")
    h.config_entries.entries = [e1, e2]
    print("Start")
    await asyncio.gather(gb.async_setup_entry(h, e1), gb.async_setup_entry(h, e2))
    g = h.data["greenbox"]["_garden"]
    check(h.services.reg == 8 and len(h.ws) == 1 and sorted(FakeDevice.started) == sorted([MAC1, MAC2]), "gleichzeitiger Start: ein Garten, 8 Dienste einmal, 1 Websocket-Befehl, 2 Geräte")
    check(len(h.http.paths) == 2 and h.http.paths[0][0] == "/greenbox_static" and h.http.paths[0][1].endswith("frontend") and h.http.paths[1][0] == "/greenbox_photos" and h.http.paths[1][1].endswith("greenbox_photos") and h.js == ["/greenbox_static/greenbox-garden-card.js?v=9.9.9"],
          "Karte wird automatisch bereitgestellt (einmal, mit Version gegen Cache)")
    check((PKG := _stubs.PKG / "frontend" / "greenbox-garden-card.js").is_file(), "Kartendatei liegt in der Integration")
    check(all("time" in p and "sensor" in p for _, p in h.config_entries.forwarded) and set(g.coordinator.data) == {MAC1, MAC2}
          and g.keys_for(e1) == [MAC1] and g.keys_for(e2) == [MAC2], "jede Bluetooth-Box bekommt ihren eigenen Garten")
    check(g.lib.is_empty, "ohne Katalog startet die Bibliothek leer")

    print("Dienste ohne Katalog")
    call = lambda n, d: h.services.h[("greenbox", n)](Call(d))
    check(await expect(call("plant_package", {"schedule": None, "germination_days": 5, "growth_days": 5, "harvest_days": 5, "plants": {1: "X"}}), "Bitte 'box' angeben"), "bei mehreren Boxen ist 'box' nötig")
    await call("plant_package", {"box": "GreenBoxOne", "germination_days": 5, "growth_days": 10, "harvest_days": 7, "plants": {1: "Erdbeere"}, "planted_at": "2026-09-25"})
    v = g.coordinator.data[MAC1]
    check(v["planted_count"] == 1 and v["slots"][0]["plant"] == "Erdbeere" and v["schedule"] == [5.0, 10.0, 7.0] and g.coordinator.data[MAC2]["planted_count"] == 0, "eigener Zeitplan mit freiem Namen, andere Box unberührt")
    check(Store.data["greenbox_garden_local"]["boxes"][MAC1]["package"]["slots"]["0"]["plant_id"] is None, "gespeichert im bisherigen Speicher 'greenbox_garden_local'")
    check(await expect(call("plant_microgreen", {"box": MAC1, "slot": 1, "microgreen": "Kresse"}), "sprout_days und growth_days"), "Microgreen ohne Katalog braucht Zeiten")
    await call("plant_microgreen", {"box": MAC1, "slot": 1, "microgreen": "Kresse", "sprout_days": 2, "growth_days": 8, "planted_on": "2026-09-20"})
    check(g.coordinator.data[MAC1]["microgreens"][0]["plant"] == "Kresse" and g.coordinator.data[MAC1]["mode"] == "mixed", "freies Microgreen wird gepflanzt")
    check(await expect(call("update_catalog", {}), "Cloud-Konto"), "update_catalog ohne Cloud-Konto: klare Meldung")

    print("Katalogdatei im Home-Assistant-Ordner")
    (CONFIG_DIR / "greenbox_catalog.json").write_text(json.dumps(_stubs.slim_catalog()), encoding="utf-8")
    g2 = hub.Garden(h)
    await g2.async_init()
    check(not g2.lib.is_empty and g2.lib.find_mix("Test Herbs")["id"] == 1, "wird gelesen, wenn kein gespeicherter Katalog da ist")
    (CONFIG_DIR / "greenbox_catalog.json").write_text("kaputt", encoding="utf-8")
    g3 = hub.Garden(h)
    await g3.async_init()
    check(g3.lib.is_empty, "kaputte Datei -> leerer Katalog, kein Absturz")
    (CONFIG_DIR / "greenbox_catalog.json").unlink()

    print("Cloud-Konto")
    ce = Entry({"cloud": True, "email": "a@b.de", "api_key": FAKE_KEY, "refresh_token": "T1"}, "Berlin Green Cloud")
    h.config_entries.entries.append(ce)
    await gb.async_setup_entry(h, ce)
    check(h.config_entries.forwarded[-1] == (ce.entry_id, ["button", "sensor"]) and set(g.coordinator.data) == {MAC1, MAC2, CLOUD_ONLY}, "Cloud-Eintrag: Katalog-Button und Sensoren; Boxen des Kontos kommen dazu")
    check(g.keys_for(ce) == [CLOUD_ONLY] and g.keys_for(e1) == [MAC1], "der Cloud-Eintrag legt Gärten nur für Boxen ohne Bluetooth an")
    cloud = g.cloud
    check(cloud.api_key == FAKE_KEY, "der eingetragene API-Schlüssel wird an die Cloud-Verbindung übergeben")
    check(not g.lib.is_empty and cloud.catalog_calls == 1 and Store.data["greenbox_catalog"]["mixes"], "Katalog wird nach dem Verbinden einmal automatisch geladen und gespeichert")
    await g.coordinator.async_refresh()
    check(cloud.catalog_calls == 1, "danach nicht erneut")
    check(g.coordinator.data[MAC1]["source"] == "local" and g.coordinator.data[CLOUD_ONLY]["source"] == "cloud" and g.coordinator.data[CLOUD_ONLY]["ble"] is False, "lokale Bepflanzung hat Vorrang, Cloud-Box ohne Bluetooth zeigt den Cloud-Stand")
    check(h.config_entries.updated and h.config_entries.updated[-1]["refresh_token"] == "ROTATED", "erneuertes Token landet im Cloud-Eintrag")
    print("Garten aus der Cloud übernehmen (Button)")
    import types as _t
    sys.modules["homeassistant.const"].EntityCategory = _t.SimpleNamespace(CONFIG="config", DIAGNOSTIC="diagnostic")
    _stubs.mod("homeassistant.components.button", ButtonEntity=object)
    _stubs.mod("homeassistant.helpers.device_registry", DeviceInfo=dict)
    _stubs.mod("homeassistant.helpers.entity", Entity=object)
    _stubs.mod("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)

    class CoordinatorEntity:
        def __init__(self, coordinator): self.coordinator = coordinator
    sys.modules["homeassistant.helpers.update_coordinator"].CoordinatorEntity = CoordinatorEntity
    button = importlib.import_module("greenbox.button")
    added = []
    await button.async_setup_entry(h, e1, added.extend)
    imp = next(b for b in added if isinstance(b, button.ImportFromCloud))
    check(imp._attr_unique_id == f"{MAC1}_import_from_cloud" and imp._attr_device_info == {"identifiers": {("greenbox", MAC1)}}, "Button gehört zum Gerät der Bluetooth-Box")
    check(imp.available, "verfügbar, weil die Cloud die Box kennt")
    import copy as _c
    snapshot, before = _c.deepcopy(g.local), g.coordinator.data[MAC1]["source"]
    await imp.async_press()
    check(before == "local" and g.local["boxes"][MAC1] and g.coordinator.data[MAC1]["name"] == "Cloud name", "Knopfdruck übernimmt den Stand der Cloud in den lokalen Garten")
    g.local = snapshot  # übrige Tests erwarten die lokale Bepflanzung
    await g.store.async_save(g.local)
    g.refresh()
    await button.async_setup_entry(h, e2, added.extend)
    imp2 = [b for b in added if isinstance(b, button.ImportFromCloud)][1]
    raw = g.raw_cloud.pop(MAC2, None)
    check(not imp2.available and await expect(imp2.async_press(), "nicht in der Cloud"), "Box ohne Cloud-Eintrag: Button nicht verfügbar, Druck meldet es klar")
    await call("plant_package", {"box": "GreenBoxTwo", "mix": "Test Herbs", "plants": {1: "Cilantro"}})
    check(g.coordinator.data[MAC2]["mix"] == "Testkräuter" and g.coordinator.data[MAC2]["planted_count"] == 1, "mit Katalog: Mix und Katalogpflanze")
    check(await expect(call("plant_slot", {"box": "GreenBoxTwo", "slot": 2, "plant": "Lettuce"}), "gehört nicht zu diesem Mix"), "Mix-Regeln gelten weiter")
    cloud.catalog_calls = 0
    await call("update_catalog", {})
    check(cloud.catalog_calls == 1, "Dienst update_catalog lädt den Katalog neu")
    e1.options["show_cannabis"] = True
    g.configure()
    check(g.lib.allow_cannabis and g.lib.find_mix("Hidden Mix")["cannabis"], "Cannabis-Option der Box-Einträge gilt für den Garten (auch nach Katalog-Update)")
    e1.options["show_cannabis"] = False
    g.configure()

    print("Cloud-Fehler")
    catalog_before = json.dumps(Store.data["greenbox_catalog"], sort_keys=True)
    cloud.mode = "auth"
    await g.coordinator.async_refresh(); await g.coordinator.async_refresh()
    check(ce.reauth == 1 and g.coordinator.data[MAC1]["planted_count"] == 1, "Anmeldung abgelehnt: Neuanmeldung einmal angestoßen, lokale Daten unverändert")
    check(await expect(call("update_catalog", {}), "Anmeldung abgelehnt"), "update_catalog meldet die abgelehnte Anmeldung")
    cloud.mode = "net"
    await g.coordinator.async_refresh()
    check(CLOUD_ONLY in g.coordinator.data and g.coordinator.data[MAC1]["planted_count"] == 1, "Cloud offline: letzter Stand bleibt")
    check(await expect(call("update_catalog", {}), "nicht geladen werden"), "update_catalog meldet fehlendes Netz")
    check(json.dumps(Store.data["greenbox_catalog"], sort_keys=True) == catalog_before and not g.lib.is_empty, "gespeicherter Katalog bleibt bei Fehlern erhalten")

    print("API-Schlüssel")
    cloud.mode = "key"
    ce.reauth = 0
    g._reauth_started = False
    await g.coordinator.async_refresh(); await g.coordinator.async_refresh()
    check(ce.reauth == 1 and g.coordinator.data[MAC1]["planted_count"] == 1, "ungültiger/beschränkter Schlüssel: Neueingabe einmal angestoßen, lokale Daten unverändert")
    check(await expect(call("update_catalog", {}), "Anmeldung abgelehnt"), "update_catalog meldet den Schlüsselfehler")
    cloud.mode = "ok"
    old = dict(ce.data)
    g.configure()                       # der Nutzer hat neu eingegeben -> Merker der früheren Neueingabe ist zurückgesetzt
    g._reauth_started = False
    ce.data = {k: v for k, v in old.items() if k != "api_key"}   # Eintrag aus Version 0.5.0 ohne Schlüssel
    ce.reauth = 0
    g.configure()
    g.configure()
    check(g.cloud is None and ce.reauth == 1, "Eintrag ohne Schlüssel (Version 0.5.0): keine Cloud-Anfragen, Neueingabe einmal angestoßen")
    check(g.coordinator.data[MAC1]["planted_count"] == 1, "lokale Bepflanzung läuft ohne Schlüssel unverändert weiter")
    ce.data = old
    g.configure()
    check(g.cloud is not None and g.cloud.api_key == FAKE_KEY, "mit eingetragenem Schlüssel ist die Cloud wieder da")

    print("Karte als Dashboard-Ressource")

    class Resources:
        loaded = False
        def __init__(self, items=()): self.items, self.n = [dict(i) for i in items], 0
        async def async_load(self): self.loaded = True
        def async_items(self): return list(self.items)
        async def async_create_item(self, data): self.n += 1; self.items.append({"id": f"r{self.n}", **data})
        async def async_update_item(self, id_, data): next(i for i in self.items if i["id"] == id_).update(data)

    card_url = "/greenbox_static/greenbox-garden-card.js?v=9.9.9"
    h5 = Hass(); res = Resources(); h5.data["lovelace"] = types_ns(resources=res)
    root = h5.data.setdefault("greenbox", {})
    await gb._register_card(h5, root, g)
    check(res.loaded and res.items == [{"id": "r1", "res_type": "module", "url": card_url}] and h5.js == [], "Speichermodus: Ressource wird angelegt, keine zweite Einbindung")
    root["_frontend"] = False
    await gb._register_card(h5, root, g)
    check(len(res.items) == 1, "erneuter Start legt sie nicht doppelt an")
    h6 = Hass(); res6 = Resources([{"id": "old", "res_type": "module", "url": "/greenbox_static/greenbox-garden-card.js?v=0.1.0"}])
    h6.data["lovelace"] = {"resources": res6}
    await gb._register_card(h6, h6.data.setdefault("greenbox", {}), g)
    check(res6.items == [{"id": "old", "res_type": "module", "url": card_url}], "neue Version aktualisiert die vorhandene Ressource (auch bei dict-Daten)")
    h7 = Hass(); h7.data["lovelace"] = types_ns(resources=types_ns(async_items=lambda: []))  # YAML-Modus: nur lesbar
    await gb._register_card(h7, h7.data.setdefault("greenbox", {}), g)
    check(h7.js == [card_url], "YAML-Modus: Ersatz über die Seite (extra_js_url)")

    print("Entfernen und Neustart")
    h.config_entries.entries.remove(ce)
    await gb.async_unload_entry(h, ce)
    check(set(g.coordinator.data) == {MAC1, MAC2} and g.cloud is None and "_garden" in h.data["greenbox"], "Cloud-Eintrag entfernt: Garten und Dienste bleiben")
    h.config_entries.entries.remove(e2); e2.state = State.NOT_LOADED
    await gb.async_unload_entry(h, e2)
    h.config_entries.entries.remove(e1); e1.state = State.NOT_LOADED
    await gb.async_unload_entry(h, e1)
    check("_garden" not in h.data["greenbox"] and h.services.h == {} and FakeDevice.started == [], "letzter Eintrag entfernt: Dienste weg, Garten freigegeben, Geräte gestoppt")
    e3 = Entry({"address": MAC1, "name": "GreenBoxOne"}, "GreenBoxOne")
    h.config_entries.entries = [e3]
    await gb.async_setup_entry(h, e3)
    g4 = h.data["greenbox"]["_garden"]
    check(g4 is not g and g4.coordinator.data[MAC1]["planted_count"] == 1 and not g4.lib.is_empty and h.services.reg == 16, "Neustart: Bepflanzung und Katalog bleiben erhalten, Dienste neu registriert")
    check(len(h.http.paths) == 2 and len(h.js) == 1, "Karte und Fotoordner werden nicht doppelt registriert")
    print("\n" + ("%d FEHLER" % fails if fails else "alle Tests ok"))
    sys.exit(1 if fails else 0)


asyncio.run(main())
