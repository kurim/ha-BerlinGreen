"""Logik ohne Home Assistant: Katalog, Bepflanzung, Wachstumsphasen, Bluetooth-Protokoll.   python tests/test_logic.py"""
import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import _stubs

_stubs.install()
_stubs.package()
build = importlib.import_module("greenbox.catalog_build")
L = importlib.import_module("greenbox.library")
loc = importlib.import_module("greenbox.local")
garden = importlib.import_module("greenbox.garden")
proto = importlib.import_module("greenbox.protocol")
GardenError, Library = L.GardenError, L.Library
NOW = _stubs.NOW
fails = 0


def check(cond, msg):
    global fails
    print(("  ok    " if cond else "  FEHLT ") + msg)
    fails += not cond


def raises(fn, part):
    try:
        fn()
    except GardenError as e:
        return part in str(e)
    return False


print("Katalog aufbereiten")
raw = _stubs.raw_catalog()
cat = build.build(raw)
check(len(cat["mixes"]) == 4 and len(cat["plants"]) == 9 and len(cat["microgreens"]) == 6 and len(cat["mushrooms"]) == 1, "Anzahl Mixe/Pflanzen/Microgreens/Pilze")
check(cat["mixes"][0]["schedule"] == [15.0, 20.0, 15.0] and cat["mixes"][0]["plants"] == [101, 102, 103, 104], "Mix: Zeitplan und Pflanzen")
check(cat["plants"]["201"]["own"] and cat["plants"]["201"]["name"] == {"de": "My Pepper"} and cat["plants"]["201"]["photo"] == "https://example.com/own.svg", "eigene Pflanze: Name aus user_provided_name, Foto aus image")
check(cat["mixes"][2]["own"] and cat["mixes"][2]["name"]["de"] == "Eigene Pflanzen", "eigener Mix ohne Namen bekommt einen Standardnamen")
check(cat["mixes"][3]["cannabis"] and cat["plants"]["301"]["cannabis"], "Cannabis-Kennzeichen")
check(cat["microgreens"][0]["photo"] == "https://example.com/m/1.jpg" and cat["microgreens"][2]["photo"] is None, "Microgreen-Foto aus der Liste 'encyclopedia' (auch leer)")
check(Library.valid(cat) and not Library.valid({}) and not Library.valid(None) and not Library.valid({"mixes": {}}), "Katalog-Prüfung")
check(set(build.QUERIES) == {"mixes", "plants", "microgreens", "mushrooms"} and all(q.count("{") == q.count("}") for q in build.QUERIES.values()), "Abfragen vorhanden und ausgeglichen")

print("Bibliothek")
lib = Library(cat)
check(lib.find_mix("test herbs")["id"] == 1 and lib.find_mix("Testkräuter")["id"] == 1 and lib.find_mix(1)["id"] == 1, "Mix nach Name (de/en, Groß-/Kleinschreibung) oder ID")
check(raises(lambda: lib.find_mix("Test"), "nicht eindeutig") and raises(lambda: lib.find_mix("nix"), "nicht gefunden"), "mehrdeutig / unbekannt")
check(raises(lambda: lib.find_mix("Hidden Mix"), "nicht gefunden") and Library(cat, allow_cannabis=True).find_mix("Hidden Mix")["cannabis"], "Cannabis nur mit Option")
pub = lib.public("en")
check(all(m["name"] != "Hidden Mix" for m in pub["mixes"]) and pub["empty"] is False and len(pub["microgreens"]) == 6, "Karten-Katalog ohne Cannabis")
check(Library.empty().is_empty and Library.empty().public()["empty"] is True, "leerer Katalog")

print("Bepflanzung lokal")
ago = (NOW - timedelta(days=3)).isoformat()
box = loc.new_box("Box")
loc.plant_package(box, lib, mix="Test Herbs", slots={1: "Cilantro", 2: "Thyme", 5: "Cilantro"}, planted_at=ago)
check(sorted(box["package"]["slots"]) == ["0", "1", "4"] and box["package"]["schedule"] == [15.0, 20.0, 15.0], "Paket mit drei Slots")
view = garden.build_box(loc.to_cloud_shape("K", box), NOW)
s0 = view["slots"][0]
check(view["mode"] == "plants" and view["planted_count"] == 3 and len(view["slots"]) == 8 and s0["phase"] == "germination"
      and abs(s0["days_elapsed"] - 3) < 0.1 and abs(s0["days_to_harvest"] - 32) < 0.1, "Ansicht: 8 Slots, Keimung, 32 Tage bis zur Ernte")
check(raises(lambda: loc.plant_slot(box, lib, 3, "Lettuce"), "gehört nicht zu diesem Mix"), "Pflanze außerhalb des Mixes wird mit Hinweis abgelehnt")
check(raises(lambda: loc.plant_slot(box, lib, 9, "Cilantro"), "zwischen 1 und 8") and raises(lambda: loc.plant_package(box, lib), "Mix angeben"), "ungültiger Slot / fehlender Mix")
check(raises(lambda: loc.plant_package(box, lib, mix=1, schedule=[1, 2, 3]), "nicht beides"), "Mix und Zeitplan schließen sich aus")
loc.plant_slot(box, lib, 4, "Mint")
loc.clear_slot(box, 2)
check(sorted(box["package"]["slots"]) == ["0", "3", "4"] and raises(lambda: loc.clear_slot(box, 2), "bereits leer"), "Slot setzen und leeren")
check(raises(lambda: loc.plant_slot(loc.new_box("n"), lib, 1, "Basil"), "kein Paket"), "ohne Paket kein Slot")

print("Eigenes Paket je Slot (nur lokal)")
b3 = loc.new_box("B3")
loc.plant_package(b3, lib, mix="Test Herbs", slots={1: "Cilantro"}, planted_at=ago)
loc.plant_slot(b3, lib, 2, "Lettuce", mix="Test Salad", planted_at=(NOW - timedelta(days=12)).isoformat())
loc.plant_slot(b3, lib, 3, "Nachtkerze", schedule=[4, 9, 6], planted_at=NOW.isoformat())
check(b3["package"]["slots"]["1"]["pkg"]["mix_id"] == 2 and b3["package"]["slots"]["2"]["pkg"]["mix_id"] is None and "pkg" not in b3["package"]["slots"]["0"],
      "Slot mit anderem Mix oder eigenem Zeitplan bekommt ein eigenes Paket, die anderen bleiben beim Paket der Box")
v3 = garden.build_box(loc.to_cloud_shape("K3", b3), NOW)
s = v3["slots"]
check(len(loc.to_cloud_shape("K3", b3)["packages"]) == 3 and s[0]["package"] == "Testkräuter" and s[1]["package"] == "Testsalat" and s[2]["package"] == "Eigener Zeitplan",
      "drei Pakete, jeder Slot kennt seins")
check(s[0]["phase"] == "germination" and abs(s[0]["days_to_harvest"] - 32) < 0.1 and s[1]["phase"] == "growth" and abs(s[1]["days_to_harvest"] - 24) < 0.1
      and s[2]["phase"] == "germination" and abs(s[2]["days_to_harvest"] - 13) < 0.1, "jeder Slot läuft nach seinem eigenen Zeitplan")
check(v3["mix"] == "Testkräuter" and v3["planted_count"] == 3, "Box zeigt weiter das Hauptpaket")
loc.plant_slot(b3, lib, 2, "Lettuce", mix="Test Salad")  # gleicher Mix, neues Datum
loc.plant_slot(b3, lib, 2, "Cilantro")  # ohne Angabe: zurück zum Paket der Box
check("pkg" not in b3["package"]["slots"]["1"], "ohne Mix/Zeitplan gehört der Slot wieder zum Paket der Box")
check(raises(lambda: loc.plant_slot(b3, lib, 4, "Lettuce", mix="Test Herbs"), "gehört nicht zu diesem Mix"), "Pflanze muss zum gewählten Mix passen")
check(raises(lambda: loc.plant_slot(b3, lib, 4, "Basil", mix=1, schedule=[1, 2, 3]), "nicht beides") and raises(lambda: loc.plant_slot(b3, lib, 4, "Basil", planted_at=ago), "nur zusammen"), "Mix und Zeitplan schließen sich aus; Datum braucht Mix oder Zeitplan")
b4 = loc.new_box("B4")
loc.plant_slot(b4, lib, 1, "Basil", mix="Test Herbs")
check(b4["package"]["mix_id"] == 1 and "pkg" not in b4["package"]["slots"]["0"], "ohne Paket wird der Slot mit Mix zum Paket der Box")
back = loc.from_cloud_shape(loc.to_cloud_shape("K3", b3))
check(back["package"]["slots"]["2"]["pkg"]["schedule"] == [4.0, 9.0, 6.0], "Umwandlung hin und zurück behält das Slot-Paket")
loc.remove_package(b3)
check(loc.to_cloud_shape("K3", b3)["packages"] == [], "Paket entfernen entfernt auch die Slot-Pakete")

print("Eigener Zeitplan und freie Namen")
b2 = loc.new_box("B2")
loc.plant_package(b2, lib, schedule=[5, 10, 7], slots={1: "Tomate Sorte X", 2: "Basil"})
check(b2["package"]["mix_id"] is None and b2["package"]["slots"]["0"]["plant"] == {"de": "Tomate Sorte X", "en": "Tomate Sorte X"}
      and b2["package"]["slots"]["0"]["plant_id"] is None and b2["package"]["slots"]["1"]["plant_id"] == 101, "unbekannter Name frei, bekannter aus dem Katalog")
loc.plant_slot(b2, lib, 3, "Noch ein Name")
v2 = garden.build_box(loc.to_cloud_shape("K2", b2), NOW)
check(v2["slots"][2]["plant"] == "Noch ein Name" and v2["schedule"] == [5.0, 10.0, 7.0], "freie Namen erscheinen in der Ansicht")
check(raises(lambda: loc.plant_package(loc.new_box("x"), lib, mix=1, slots={1: "Unbekannt"}), "nicht gefunden"), "bei einem Mix ist kein freier Name erlaubt")
check(raises(lambda: loc.plant_package(loc.new_box("x"), lib, schedule=[1, 2], slots={}), "drei Werte"), "Zeitplan braucht drei Werte")
b3 = loc.new_box("B3")
empty = Library.empty()
loc.plant_package(b3, empty, schedule=[10, 10, 10], slots={1: "Erdbeere"})
check(b3["package"]["slots"]["0"]["plant"]["de"] == "Erdbeere", "ohne Katalog funktioniert der eigene Zeitplan")
check(raises(lambda: loc.plant_package(loc.new_box("x"), empty, mix="Test Herbs"), "nicht gefunden"), "ohne Katalog gibt es keinen Mix")
own = lib.custom_mix()
b4 = loc.new_box("B4")
loc.plant_package(b4, lib, mix=own["id"], slots={1: "My Pepper"})
loc.plant_slot(b4, lib, 2, "Basil")
check(b4["package"]["schedule"] == [20.0, 20.0, 20.0], "eigener Mix: jede Katalogpflanze erlaubt")

print("Microgreens und reservierte Slots")
b5 = loc.new_box("B5")
loc.plant_microgreen(b5, lib, 1, "Arugula", "2026-09-20")
loc.plant_microgreen(b5, lib, 6, "kresse")
check(sorted(b5["microgreens"]) == ["0", "5"], "Microgreens aus dem Katalog (Name, Groß-/Kleinschreibung egal)")
check(raises(lambda: loc.plant_microgreen(b5, lib, 7, "Arugula"), "zwischen 1 und 6"), "nur 6 Felder")
check(raises(lambda: loc.plant_microgreen(b5, lib, 2, "Erdbeere"), "sprout_days und growth_days"), "unbekanntes Microgreen braucht Zeiten")
loc.plant_microgreen(b5, lib, 2, "Erdbeere", None, 3, 10)
check(b5["microgreens"]["1"]["growth_days"] == 10.0 and b5["microgreens"]["1"]["microgreen_id"] is None, "freies Microgreen mit eigenen Zeiten")
check(raises(lambda: loc.plant_microgreen(b5, lib, 3, "Erdbeere", None, 5, 2), "mindestens so lang"), "Erntezeit >= Keimzeit")
mv = garden.build_box(loc.to_cloud_shape("K5", b5), NOW)
check(mv["mode"] == "mixed" and mv["plant_slot_ids"] == [0, 1, 4, 5] and mv["microgreens"][0]["phase"] == "growth" and mv["microgreens_planted"] == 3, "gemischter Modus: 4 Pflanz-Töpfe, Microgreens wachsen")
b6 = loc.new_box("B6")
loc.plant_package(b6, lib, mix=1, slots={1: "Basil", 3: "Thyme"})
check(raises(lambda: loc.plant_microgreen(b6, lib, 1, "Cress"), "müssen die Pflanz-Slots 3 leer sein"), "Pflanze auf reserviertem Slot blockiert das Modul")
loc.clear_slot(b6, 3)
loc.plant_microgreen(b6, lib, 1, "Cress")
check(raises(lambda: loc.plant_slot(b6, lib, 3, "Thyme"), "reserviert") and raises(lambda: loc.plant_package(b6, lib, mix=1, slots={8: "Basil"}), "reserviert"), "mit Modul sind nur die Slots 1, 2, 5, 6 für Pflanzen frei")
loc.clear_microgreen(b6)
loc.plant_slot(b6, lib, 3, "Thyme")
check(garden.build_box(loc.to_cloud_shape("K6", b6), NOW)["mode"] == "plants", "ohne Modul wieder alle 8 Slots")

print("Phasen")
t0 = garden.parse_time("2026-01-01T00:00:00+00:00")
P = lambda days: garden.package_phase(t0, [5, 16, 20], t0 + timedelta(days=days))["phase"]
check([P(0), P(4.9), P(5), P(20.9), P(21), P(41), P(41.1)] == ["germination", "germination", "growth", "growth", "harvest", "harvest", "complete"], "Paket: Keimung -> Wachstum -> Ernte -> abgeschlossen (Grenzen)")
M = lambda days: garden.microgreen_phase(t0, 2, 8, t0 + timedelta(days=days))
check([M(1)["phase"], M(2)["phase"], M(7.9)["phase"], M(8)["phase"], M(30)["phase"]] == ["germination", "growth", "growth", "harvest", "harvest"] and M(4)["days_to_harvest"] == 4, "Microgreens: Keimung -> Wachstum -> Ernte")
check(garden.parse_time("2026-09-20").tzinfo is not None and garden.parse_time("kaputt") is None and garden.parse_time(None) is None, "Zeitangaben")

print("Cloud-Daten")
def mg(i, name):
    return {"slot": i, "plantedOnDay": "2026-09-20", "microgreen": {"id": i + 1, "growthTimeDays": 8, "sproutTimeDays": 2, "name": {"de": name}, "encyclopedia": [{"image": None}]}}
raw_box = {"id": "u", "box_id": _stubs.MAC1, "name": "Box", "type": "Standard", "mushroom_config": [],
           "packages": [{"planted_at": "2026-09-26T11:00:00+00:00", "layout": "EightSlot", "mix": {"id": 3, "name": None, "growth_speed": [15, 20, 15]},
                         "planted": [{"slot": 0, "plant": {"id": 201, "name": None, "user_provided_name": "My Pepper", "photo": None}}]}],
           "microgreen_configs": [{"planted_microgreens": [mg(0, "Rucola")]}]}
cv = garden.build_box(raw_box, NOW)
check(cv["mode"] == "mixed" and cv["slots"][0]["plant"] == "My Pepper" and cv["microgreens"][0]["plant"] == "Rucola", "Paket und Microgreens gleichzeitig (encyclopedia als Liste)")
dbl = dict(raw_box, packages=[], microgreen_configs=[{"planted_microgreens": [mg(0, "Kresse")]}, {"planted_microgreens": [mg(0, "Rucola")]}])
dv = garden.build_box(dbl, NOW)
check(dv["mode"] == "double" and dv["microgreen_modules"][0][0]["plant"] == "Kresse" and dv["microgreen_modules"][1][0]["plant"] == "Rucola", "zwei Module bleiben getrennt")
rec = loc.from_cloud_shape(raw_box)
rv = garden.build_box(loc.to_cloud_shape(_stubs.MAC1, rec), NOW)
strip = lambda v: [(s["slot"], s["plant"], s["phase"], s.get("days_elapsed")) for s in v["slots"] + v["microgreens"]]
check(strip(cv) == strip(rv) and json.dumps(rec), "Import Cloud -> lokal ergibt dieselbe Ansicht")
check(len(garden.build_box({"id": "x", "box_id": "B", "name": "n", "packages": [], "microgreen_configs": [], "mushroom_config": []}, NOW)["slots"]) == 8, "leere Box hat 8 Slots")

print("Bluetooth-Protokoll")
check(proto.frame_override(0).hex() == "ee4f0000d4ef" and proto.frame_override(1).hex() == "ee4f0001d3ef" and proto.frame_override(3).hex() == "ee4f0003d1ef", "Override-Frames")
check(proto.frame_strip(1, 50).hex() == "ee310032c0ef" and proto.frame_switch_time(False, 600).hex() == "ee53025876ef" and proto.frame_duration(False, 12).hex() == "ee44000cd3ef", "Streifen-, Schaltzeit- und Dauer-Frames")
check(proto.parse_frame(bytes.fromhex("ee4f0003d1ef")) == (79, b"\x00\x03") and proto.parse_frame(bytes.fromhex("ee4f0003d2ef")) is None, "Prüfsumme")
st, fp = proto.BoxState(), proto.FrameParser()
blob = b"".join(bytes.fromhex(x) for x in "ee4f0003d1ef ee660003baef ee5302bc12ef ee57006468ef ee3100648eef ee5400ffd0ef ee310032c1ef".split())
for i in range(0, len(blob), 3):
    for t, d in fp.feed(blob[i:i + 3]):
        st.apply(t, d)
check(st.override == 3 and st.firmware == 3 and st.firmware_name == "2.0.3" and st.switch_workdays == 700 and st.water == 100 and st.strips == {1: 100} and st.temperature_c is None,
      "zerstückelte Notifications werden zusammengesetzt, Frame mit falscher Prüfsumme verworfen")
check(proto.strips_for(100, 2) == (100, 100, 100) and proto.strips_for(50, 2) == (50, 50, 50) and proto.strips_for(33, 0) == (99, 0, 0) and proto.strips_for(5, 4) == (0, 0, 15), "Lichtprofile -> Streifen")
check(all(proto.light_from_strips(dict(zip((1, 2, 3), proto.strips_for(i, t)))) == (i, t) for t in range(5) for i in (1, 5, 10, 20, 30, proto.max_intensity(t)) if i <= proto.max_intensity(t)), "Streifen -> Intensität/Farbtemperatur (Rundreise)")
check(proto.preset_for({1: 99, 2: 0, 3: 0}) == "ambient" and proto.preset_for({1: 100, 2: 100, 3: 100}) == "growth", "Profil aus Streifenwerten erkennen")
summer, winter = datetime(2026, 9, 26, 12, tzinfo=ZoneInfo("Europe/Berlin")), datetime(2026, 12, 1, 12, tzinfo=ZoneInfo("Europe/Berlin"))
check(proto.local_from_raw(600, summer, True) == (8, 0) and proto.raw_from_local(8, 0, summer, True) == 600 and proto.raw_from_local(8, 0, winter, True) == 700, "Schaltzeit: UTC-Umrechnung mit Sommer-/Winterzeit")
check(all(proto.local_from_raw(proto.raw_from_local(h, m, r, True), r, True) == (h, m) for r in (summer, winter) for h in range(24) for m in (0, 30, 59)), "Umrechnung ist umkehrbar (auch über Mitternacht)")
check(proto.uses_utc(3) is True and proto.uses_utc(4) is False and proto.uses_utc(None) is None and proto.parse_config("1,0,1") == (True, "plus"), "Firmware-Regel und Konfigurationsfeld")
try:
    proto.frame_duration(False, 11)
    ok = False
except ValueError:
    ok = True
check(ok and proto.water_status(0) == "empty" and proto.water_status(20) == "low" and proto.water_status(50) == "ok", "Grenzen: Dauer 12-18 h, Wasserstatus")
print("\n" + ("%d FEHLER" % fails if fails else "alle Tests ok"))
sys.exit(1 if fails else 0)
