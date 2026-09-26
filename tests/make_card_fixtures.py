"""Erzeugt die Vorlagen (Sensor-Zustände, Katalog) für tests/card/card.test.js aus den ausgedachten Testdaten.   python tests/make_card_fixtures.py"""
import importlib
import json
from pathlib import Path

import _stubs

_stubs.install()
_stubs.package()
L = importlib.import_module("greenbox.library")
loc = importlib.import_module("greenbox.local")
garden = importlib.import_module("greenbox.garden")
OUT = Path(__file__).resolve().parent / "card" / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)
ATTRS = ("name", "box_key", "source", "type", "layout", "mix", "mix_id", "schedule", "has_package", "harvest_ready", "microgreens_planted",
         "microgreens_ready", "mushrooms", "mushrooms_planted", "mushrooms_ready", "slots", "microgreens", "microgreen_modules", "mode", "plant_slot_ids")
lib = L.Library(_stubs.slim_catalog())


def state(box=None, raw=None):
    v = garden.build_box(raw or loc.to_cloud_shape(_stubs.MAC1, box), _stubs.NOW)
    v.update(source="local", box_key=_stubs.MAC1)
    return {"state": str(v["planted_count"]), "attributes": {k: v.get(k) for k in ATTRS}}


def write(name, data):
    (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


write("catalog", lib.public("en"))
write("catalog_empty", L.Library.empty().public("en"))
write("st_empty", state(loc.new_box("Box")))
b = loc.new_box("Box")
loc.plant_package(b, lib, mix="Test Herbs", slots={1: "Basil", 2: "Cilantro"}, planted_at="2026-09-25")
loc.plant_microgreen(b, lib, 1, "Arugula", "2026-09-20")
loc.plant_microgreen(b, lib, 2, "Cress", "2026-09-20")
write("st_pkg", state(b))
c = loc.new_box("Box")
loc.plant_package(c, lib, schedule=[5, 10, 7], slots={1: "Eigene Tomate"}, planted_at="2026-09-25")
write("st_custom", state(c))


def mg(i, n):
    return {"slot": i, "plantedOnDay": "2026-09-20", "microgreen": {"id": i + 1, "growthTimeDays": 8, "sproutTimeDays": 2, "name": {"de": n}, "encyclopedia": [{"image": None}]}}


write("st_double", state(raw={"id": "x", "box_id": _stubs.MAC1, "name": "Double", "type": "Standard", "packages": [], "mushroom_config": [],
                              "microgreen_configs": [{"planted_microgreens": [mg(0, "Cress")]}, {"planted_microgreens": [mg(0, "Arugula")]}]}))
write("st_mush", state(raw={"id": "x", "box_id": _stubs.MAC1, "name": "Pilzbox", "type": "Standard", "microgreen_configs": [],
                            "packages": [{"planted_at": "2026-09-25T09:00:00+00:00", "layout": "EightSlot", "mix": {"id": 1, "name": {"de": "Testkräuter"}, "growth_speed": [15, 20, 15]},
                                          "planted": [{"slot": 0, "plant": {"id": 101, "name": {"de": "Basilikum"}, "photo": None}}]}],
                            "mushroom_config": [{"id": "mc1", "planted_mushrooms": [{"id": "p", "plantedOnDay": "2026-09-20", "mushroom": {
                                "id": 4, "pinningTimeDays": 5, "growthTimeDays": 7, "harvestTimeDays": 5, "name": {"de": "Austernpilz"}}}]}]}))
write("st_mush_only", state(raw={"id": "x", "box_id": _stubs.MAC1, "name": "Pilzbox", "type": "Standard", "microgreen_configs": [], "packages": [],
                                 "mushroom_config": [{"id": "mc1", "planted_mushrooms": [{"id": "p", "plantedOnDay": "2026-09-20", "mushroom": {
                                     "id": 4, "pinningTimeDays": 5, "growthTimeDays": 7, "harvestTimeDays": 5, "name": {"de": "Austernpilz"}}}]}]}))
print("Vorlagen geschrieben:", sorted(p.name for p in OUT.glob("*.json")))
