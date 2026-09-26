"""Lokale Bepflanzung (ohne Home-Assistant-Abhängigkeiten): Speicherformat, Änderungen und Umwandlung in das
Cloud-Format, damit garden.build_box() dieselben Phasenregeln anwendet.

Speicherformat je Box:
  {"name": str,
   "package": None | {"mix_id": int|None, "mix_name": {de,en}, "schedule": [Keimung, Wachstum, Erntefenster],
                       "planted_at": iso, "slots": {"0": {"plant_id": int, "plant": {de,en}, "photo": url,
                                                          "pkg": optional {"mix_id", "mix_name", "schedule", "planted_at"}}}},
   "microgreens": {"0": {"microgreen_id": int, "name": {de,en}, "planted_on": "YYYY-MM-DD", "sprout_days": 2,
                          "growth_days": 8, "photo": url}}}
"pkg" am Slot = eigenes Paket nur für diesen Slot (anderer Mix/Zeitplan/Pflanzdatum); nur lokal möglich, in der App gilt ein Paket je Box.
Slots werden intern ab 0 gezählt (wie in der Cloud), in Diensten ab 1."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .garden import MIXED_PLANT_SLOTS
from .library import GardenError, Library

PLANT_SLOTS = 8
MICROGREEN_SLOTS = 6
DEFAULT_SCHEDULE = [20.0, 20.0, 20.0]  # wie die App bei eigenen Pflanzen


def new_box(name: str) -> dict[str, Any]:
    return {"name": name, "package": None, "microgreens": {}}


def _slot(value: int, count: int, what: str) -> int:
    """Nutzereingabe (ab 1) -> interner Index (ab 0)."""
    if not 1 <= int(value) <= count:
        raise GardenError(f"{what}-Slot muss zwischen 1 und {count} liegen")
    return int(value) - 1


def _pretty(slots: list[int]) -> str:
    return ", ".join(str(s + 1) for s in slots)


def _check_plant_slot(box: dict, slot_index: int) -> None:
    """Mit Microgreen-Modul bleiben nur vier Pflanz-Slots (in der App: 1, 2, 5, 6) - der Rest ist reserviert."""
    if box.get("microgreens") and slot_index not in MIXED_PLANT_SLOTS:
        raise GardenError(f"Slot {slot_index + 1} ist für das Microgreens-Modul reserviert. Mit Microgreens sind nur die "
                          f"Slots {_pretty(MIXED_PLANT_SLOTS)} für Pflanzen verfügbar")


def _entry(plant: dict) -> dict[str, Any]:
    return {"plant_id": plant["id"], "plant": plant.get("name"), "photo": plant.get("photo")}


def _resolve_plant(lib: Library, ref: Any, allowed: list[int] | None, free_text: bool) -> dict[str, Any]:
    """Pflanze aus dem Katalog; bei eigenem Zeitplan darf ein unbekannter Name frei getippt werden (ohne Katalog nötig)."""
    try:
        return _entry(lib.find_plant(ref, among=allowed))
    except GardenError as err:
        text = str(ref).strip()
        if free_text and isinstance(ref, str) and text and not text.isdigit() and "nicht gefunden" in str(err):
            return {"plant_id": None, "plant": {"de": text, "en": text}, "photo": None}
        raise


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _spec(lib: Library, mix: Any, schedule: list[float] | None) -> tuple[Any, dict, list[float], list[int] | None, bool]:
    """Mix (Name/ID) oder eigener Zeitplan -> (Mix-ID, Mix-Name, Zeitplan, erlaubte Pflanzen, freier Name erlaubt)."""
    mix_item = lib.find_mix(mix) if mix is not None else None
    if mix_item:
        return mix_item["id"], mix_item["name"], list(mix_item["schedule"]), (None if mix_item.get("own") else mix_item["plants"]), False
    if len(schedule) != 3 or any(x < 0 for x in schedule):
        raise GardenError("Der Zeitplan braucht drei Werte >= 0 (Keimung, Wachstum, Ernte)")
    return None, {"de": "Eigener Zeitplan", "en": "Custom schedule"}, [float(x) for x in schedule], None, True


def plant_package(box: dict, lib: Library, *, mix: Any = None, schedule: list[float] | None = None,
                  slots: dict[int, Any] | None = None, planted_at: str | None = None) -> None:
    """Neues Mix-Paket (ersetzt ein vorhandenes). Entweder `mix` (Name/ID) oder ein eigener `schedule`."""
    if mix is None and schedule is None:
        raise GardenError("Bitte einen Mix angeben oder einen eigenen Zeitplan (Keimung/Wachstum/Ernte in Tagen)")
    if mix is not None and schedule is not None:
        raise GardenError("Entweder Mix ODER eigener Zeitplan, nicht beides")
    mix_id, mix_name, sched, allowed, free = _spec(lib, mix, schedule)
    chosen: dict[str, Any] = {}
    for slot_no, ref in (slots or {}).items():
        idx = _slot(slot_no, PLANT_SLOTS, "Pflanz")
        _check_plant_slot(box, idx)
        chosen[str(idx)] = _resolve_plant(lib, ref, allowed, free_text=free)
    box["package"] = {"mix_id": mix_id, "mix_name": mix_name, "schedule": sched, "planted_at": planted_at or _now_iso(), "slots": chosen}


def plant_slot(box: dict, lib: Library, slot: int, plant: Any, *, mix: Any = None, schedule: list[float] | None = None,
               planted_at: str | None = None) -> None:
    """Pflanze in einen Slot. Ohne mix/schedule gilt das Paket der Box; mit mix oder eigenem Zeitplan bekommt der Slot ein eigenes
    Paket (andere Keimung/Wachstumsdauer, eigenes Pflanzdatum). Gibt es noch kein Paket, wird es das Paket der Box."""
    if mix is not None and schedule is not None:
        raise GardenError("Entweder Mix ODER eigener Zeitplan, nicht beides")
    if mix is None and schedule is None and planted_at is not None:
        raise GardenError("Ein Pflanzdatum gilt nur zusammen mit einem Mix oder eigenem Zeitplan für den Slot")
    idx = _slot(slot, PLANT_SLOTS, "Pflanz")
    _check_plant_slot(box, idx)
    pkg = box.get("package")
    if mix is not None or schedule is not None:
        mix_id, mix_name, sched, allowed, free = _spec(lib, mix, schedule)
        entry = _resolve_plant(lib, plant, allowed, free_text=free)
        spec = {"mix_id": mix_id, "mix_name": mix_name, "schedule": sched, "planted_at": planted_at or _now_iso()}
        if not pkg:
            box["package"] = {**spec, "slots": {str(idx): entry}}
            return
        entry["pkg"] = spec
        pkg["slots"][str(idx)] = entry
        return
    if not pkg:
        raise GardenError("Es ist noch kein Paket gepflanzt - zuerst 'plant_package' verwenden (oder beim Slot einen Mix bzw. Zeitplan angeben)")
    mix_item = next((m for m in lib.mixes if m["id"] == pkg["mix_id"]), None) if pkg["mix_id"] is not None else None
    allowed = None if (mix_item is None or mix_item.get("own")) else mix_item["plants"]
    pkg["slots"][str(idx)] = _resolve_plant(lib, plant, allowed, free_text=pkg["mix_id"] is None)


def clear_slot(box: dict, slot: int) -> None:
    pkg = box.get("package")
    key = str(_slot(slot, PLANT_SLOTS, "Pflanz"))
    if not pkg or key not in pkg["slots"]:
        raise GardenError(f"Pflanz-Slot {slot} ist bereits leer")
    del pkg["slots"][key]


def remove_package(box: dict) -> None:
    if not box.get("package"):
        raise GardenError("Es ist kein Paket gepflanzt")
    box["package"] = None


def plant_microgreen(box: dict, lib: Library, slot: int, microgreen: Any, planted_on: str | None = None,
                     sprout_days: float | None = None, growth_days: float | None = None) -> None:
    """Microgreen aus dem Katalog. Fehlt er (z. B. ohne Katalog), genügen Name plus Keim- und Erntezeit in Tagen."""
    try:
        mg = lib.find_microgreen(microgreen)
    except GardenError as err:
        if not (isinstance(microgreen, str) and str(microgreen).strip() and not str(microgreen).strip().isdigit()
                and "nicht gefunden" in str(err)):
            raise
        if sprout_days is None or growth_days is None:
            raise GardenError(f"{err}. Katalog laden (greenbox.update_catalog) oder sprout_days und growth_days angeben") from None
        if sprout_days < 0 or growth_days < sprout_days:
            raise GardenError("Erntezeit (growth_days) muss mindestens so lang wie die Keimzeit (sprout_days) sein") from None
        name = str(microgreen).strip()
        mg = {"id": None, "name": {"de": name, "en": name}, "sprout_days": float(sprout_days),
              "growth_days": float(growth_days), "photo": None}
    blocked = sorted(int(k) for k in ((box.get("package") or {}).get("slots") or {}) if int(k) not in MIXED_PLANT_SLOTS)
    if blocked and not box["microgreens"]:  # das Modul würde die Hälfte der Box belegen
        raise GardenError(f"Für das Microgreens-Modul müssen die Pflanz-Slots {_pretty(blocked)} leer sein "
                          f"(mit Modul bleiben nur die Slots {_pretty(MIXED_PLANT_SLOTS)} für Pflanzen)")
    box["microgreens"][str(_slot(slot, MICROGREEN_SLOTS, "Microgreen"))] = {
        "microgreen_id": mg["id"], "name": mg["name"], "planted_on": planted_on or date.today().isoformat(),
        "sprout_days": mg["sprout_days"], "growth_days": mg["growth_days"], "photo": mg.get("photo"),
    }


def clear_microgreen(box: dict, slot: int | None = None) -> None:
    """slot=None: alle Microgreens entfernen."""
    if slot is None:
        box["microgreens"] = {}
        return
    key = str(_slot(slot, MICROGREEN_SLOTS, "Microgreen"))
    if key not in box["microgreens"]:
        raise GardenError(f"Microgreen-Slot {slot} ist bereits leer")
    del box["microgreens"][key]


def to_cloud_shape(key: str, box: dict) -> dict[str, Any]:
    """Lokale Box -> dasselbe Format wie die Cloud-Antwort (für garden.build_box)."""
    pkg = box.get("package")
    packages = []
    if pkg:
        groups: dict[Any, dict[str, Any]] = {}  # Slots mit eigenem Paket werden je Paket zusammengefasst (Cloud-Format kennt mehrere)
        for s, e in sorted(pkg["slots"].items(), key=lambda kv: int(kv[0])):
            spec = e.get("pkg") or pkg
            key = None if spec is pkg else (spec["mix_id"], tuple(spec["schedule"]), spec["planted_at"])
            group = groups.setdefault(key, {
                "id": None, "planted_at": spec["planted_at"], "layout": "EightSlot",
                "mix": {"id": spec["mix_id"], "name": spec["mix_name"], "growth_speed": spec["schedule"]}, "planted": []})
            group["planted"].append({"slot": int(s), "plant": {"id": e["plant_id"], "name": e["plant"], "photo": e.get("photo")}})
        if not groups:  # Paket ohne Pflanzen
            groups[None] = {"id": None, "planted_at": pkg["planted_at"], "layout": "EightSlot",
                            "mix": {"id": pkg["mix_id"], "name": pkg["mix_name"], "growth_speed": pkg["schedule"]}, "planted": []}
        packages = [groups[k] for k in ([None] if None in groups else []) + [k for k in groups if k is not None]]
    mg = [{"slot": int(s), "plantedOnDay": e["planted_on"],
           "microgreen": {"id": e["microgreen_id"], "growthTimeDays": e["growth_days"], "sproutTimeDays": e["sprout_days"],
                          "name": e["name"], "encyclopedia": [{"image": e.get("photo")}]}}
          for s, e in sorted(box.get("microgreens", {}).items(), key=lambda kv: int(kv[0]))]
    return {"id": key, "box_id": key, "name": box["name"], "type": "Standard", "packages": packages,
            "microgreen_configs": [{"planted_microgreens": mg}] if mg else [], "mushroom_config": []}


def from_cloud_shape(raw: dict[str, Any]) -> dict[str, Any]:
    """Cloud-Box -> lokaler Datensatz (Import; danach gilt die lokale Bepflanzung)."""
    from .garden import first_of  # lokal importiert, garden.py hat keine weiteren Abhängigkeiten

    box = new_box(raw.get("name") or raw.get("box_id") or "GreenBox")
    pkgs = raw.get("packages") or []
    if pkgs:
        pkg = pkgs[0]
        mix = pkg.get("mix") or {}
        slots = {}
        for item in pkg.get("planted") or []:
            plant = item.get("plant") or {}
            name = plant.get("name") or ({"de": plant["user_provided_name"]} if plant.get("user_provided_name") else None)
            slots[str(item["slot"])] = {"plant_id": plant.get("id"), "plant": name, "photo": plant.get("photo")}
        box["package"] = {
            "mix_id": mix.get("id"), "mix_name": mix.get("name") or {"de": "Eigene Pflanzen", "en": "Own plants"},
            "schedule": [float(x) for x in (mix.get("growth_speed") or DEFAULT_SCHEDULE)][:3],
            "planted_at": pkg.get("planted_at") or _now_iso(), "slots": slots,
        }
        for extra in pkgs[1:]:  # weitere Pakete der Cloud werden zu Slots mit eigenem Paket
            emix = extra.get("mix") or {}
            spec = {"mix_id": emix.get("id"), "mix_name": emix.get("name") or {"de": "Eigene Pflanzen", "en": "Own plants"},
                    "schedule": [float(x) for x in (emix.get("growth_speed") or DEFAULT_SCHEDULE)][:3],
                    "planted_at": extra.get("planted_at") or _now_iso()}
            for item in extra.get("planted") or []:
                plant = item.get("plant") or {}
                name = plant.get("name") or ({"de": plant["user_provided_name"]} if plant.get("user_provided_name") else None)
                slots.setdefault(str(item["slot"]), {"plant_id": plant.get("id"), "plant": name, "photo": plant.get("photo"), "pkg": spec})
    for cfg in raw.get("microgreen_configs") or []:
        for m in cfg.get("planted_microgreens") or []:
            mg = m.get("microgreen") or {}
            if mg.get("growthTimeDays") is None:
                continue
            box["microgreens"][str(m["slot"])] = {
                "microgreen_id": mg.get("id"), "name": mg.get("name"), "planted_on": m.get("plantedOnDay"),
                "sprout_days": mg.get("sproutTimeDays") or 0, "growth_days": mg["growthTimeDays"],
                "photo": first_of(mg.get("encyclopedia")).get("image"),
            }
    return box
