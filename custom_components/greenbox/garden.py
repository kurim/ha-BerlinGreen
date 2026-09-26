"""Berechnung der Slots und Wachstumsphasen aus den Cloud-Daten (ohne Home-Assistant-Abhängigkeiten).

Regeln aus dem App-Code:
- Paket (Mix):  growth_speed = [Keimung, Wachstum, Erntefenster] in Tagen ab planted_at.
  Phase 0 (Keimung) bis d0, Phase 1 (Wachstum) bis d0+d1, danach Ernte; nach d0+d1+d2 ist der Zyklus abgeschlossen.
- Microgreens:  sproutTimeDays = Keimung, growthTimeDays = Tage bis zur ersten Ernte ab plantedOnDay.
- Beide Bereiche laufen unabhängig nebeneinander (Pflanz-Slots des Mix-Pakets und das Microgreen-Modul).
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any

EMPTY = "empty"
GERMINATION = "germination"
GROWTH = "growth"
HARVEST = "harvest"
COMPLETE = "complete"
PHASES = [EMPTY, GERMINATION, GROWTH, HARVEST, COMPLETE]

SLOT_COUNTS = {"EightSlot": 8}
MICROGREEN_SLOTS = 6  # Microgreen-Modul: 6 Felder (3 x 2), in der App bestätigt
# Mit Microgreen-Modul teilt sich die Box: das Modul belegt eine Hälfte, für Pflanzen bleiben 4 Töpfchen (2 x 2).
# In der App heißen sie 1, 2, 5, 6 (hier ab 0 gezählt), der Rest ist "Reserviert für das Microgreens-Modul".
MIXED_PLANT_SLOTS = [0, 1, 4, 5]


def parse_time(value: str | None) -> datetime | None:
    """ISO-Zeitstempel oder Datum ('2025-09-20') -> aware datetime (UTC, wenn nichts angegeben)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.combine(date.fromisoformat(value), datetime.min.time())
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def first_of(value: Any) -> dict[str, Any]:
    """Hasura liefert 1:n-Beziehungen als Liste, 1:1 als Objekt: beides -> erstes Objekt."""
    if isinstance(value, list):
        return value[0] if value and isinstance(value[0], dict) else {}
    return value if isinstance(value, dict) else {}


def name_of(i18n: dict | None, language: str = "de") -> str | None:
    if not i18n:
        return None
    return i18n.get(language) or i18n.get("en") or i18n.get("de")


def package_phase(planted_at: datetime, growth_speed: list[float], now: datetime) -> dict[str, Any]:
    d0, d1, d2 = ([*growth_speed, 0, 0, 0])[:3]
    days = (now - planted_at).total_seconds() / 86400
    if days < d0:
        phase, phase_end = GERMINATION, d0
    elif days < d0 + d1:
        phase, phase_end = GROWTH, d0 + d1
    elif days <= d0 + d1 + d2:
        phase, phase_end = HARVEST, d0 + d1 + d2
    else:
        phase, phase_end = COMPLETE, d0 + d1 + d2
    return {
        "phase": phase,
        "days_elapsed": round(days, 1),
        "days_to_phase_end": round(max(phase_end - days, 0), 1),
        "days_to_harvest": round(max(d0 + d1 - days, 0), 1),
        "germination_days": d0,
        "growth_days": d1,
        "harvest_window_days": d2,
    }


def microgreen_phase(planted_on: datetime, sprout_days: float, growth_days: float, now: datetime) -> dict[str, Any]:
    days = (now - planted_on).total_seconds() / 86400
    if days < sprout_days:
        phase, phase_end = GERMINATION, sprout_days
    elif days < growth_days:
        phase, phase_end = GROWTH, growth_days
    else:
        phase, phase_end = HARVEST, growth_days
    return {
        "phase": phase,
        "days_elapsed": round(days, 1),
        "days_to_phase_end": round(max(phase_end - days, 0), 1),
        "days_to_harvest": round(max(growth_days - days, 0), 1),
        "germination_days": sprout_days,
        "growth_days": max(growth_days - sprout_days, 0),
        "harvest_window_days": None,
    }


DEFAULT_SLOTS = 8  # Standard-Box ("EightSlot"); gilt auch, wenn gerade kein Paket gepflanzt ist


def slot_count(layout: str | None, used: list[int]) -> int:
    if layout in SLOT_COUNTS:
        return SLOT_COUNTS[layout]
    return max(DEFAULT_SLOTS, max(used) + 1 if used else 0)


def build_box(box: dict[str, Any], now: datetime, language: str = "de", photo: Callable[[str | None], str | None] | None = None) -> dict[str, Any]:
    """Eine Box aus der Cloud -> Übersicht mit allen Slots (leere Slots inklusive). photo: Adresse -> lokale Adresse (falls vorhanden)."""
    photo = photo or (lambda url: url)
    pkg_slots: dict[int, dict[str, Any]] = {}
    mg_slots: dict[int, dict[str, Any]] = {}
    layout = None
    mix_name = None
    mix_id = None
    schedule = None
    for pkg in box.get("packages") or []:
        planted_at = parse_time(pkg.get("planted_at"))
        layout = layout or pkg.get("layout")
        mix = pkg.get("mix") or {}
        mix_name = mix_name or name_of(mix.get("name"), language)
        mix_id = mix.get("id") if mix_id is None else mix_id
        schedule = schedule or mix.get("growth_speed")
        speed = mix.get("growth_speed") or [0, 0, 0]
        if planted_at is None:
            continue
        info = package_phase(planted_at, speed, now)
        for item in pkg.get("planted") or []:
            plant = item.get("plant") or {}
            pkg_slots[item["slot"]] = {
                "slot": item["slot"],
                "source": "package",
                "plant": plant.get("user_provided_name") or name_of(plant.get("name"), language),
                "plant_id": plant.get("id"),
                "image": photo(plant.get("photo")),
                "package": name_of(mix.get("name"), language),
                "planted_at": planted_at.isoformat(),
                **info,
            }
    modules: list[dict[int, dict[str, Any]]] = []
    for cfg in box.get("microgreen_configs") or []:
        module: dict[int, dict[str, Any]] = {}
        for m in cfg.get("planted_microgreens") or []:
            planted_on = parse_time(m.get("plantedOnDay"))
            mg = m.get("microgreen") or {}
            if planted_on is None or mg.get("growthTimeDays") is None:
                continue
            module[m["slot"]] = {
                "slot": m["slot"],
                "source": "microgreen",
                "plant": name_of(mg.get("name"), language),
                "plant_id": mg.get("id"),
                "image": photo(first_of(mg.get("encyclopedia")).get("image")),
                "planted_at": planted_on.isoformat(),
                **microgreen_phase(planted_on, mg.get("sproutTimeDays") or 0, mg["growthTimeDays"], now),
            }
        if module:
            modules.append(module)
    mg_slots = modules[0] if modules else {}
    # Beide Bereiche existieren nebeneinander: die 8 Pflanz-Slots (Mix-Paket) und das Microgreen-Modul mit eigenen Slots.
    plant_count = slot_count(layout, list(pkg_slots))
    full = [pkg_slots.get(i) or {"slot": i, "state_only": True, "phase": EMPTY, "plant": None} for i in range(plant_count)]
    def fill(module: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        n = max(MICROGREEN_SLOTS, max(module) + 1 if module else 0)
        return [module.get(i) or {"slot": i, "state_only": True, "phase": EMPTY, "plant": None} for i in range(n)]

    micro = fill(mg_slots)
    micro_modules = [fill(m) for m in modules] or [micro]
    mushrooms: list[dict[str, Any]] = []
    for cfg in box.get("mushroom_config") or []:  # die Cloud liefert eine Liste von Konfigurationen
        for m in cfg.get("planted_mushrooms") or []:
            mu = m.get("mushroom") or {}
            planted_on = parse_time(m.get("plantedOnDay"))
            entry: dict[str, Any] = {
                "slot": len(mushrooms), "source": "mushroom", "plant": name_of(mu.get("name"), language), "plant_id": mu.get("id"),
                "image": photo(mu.get("imageURL")), "planted_at": planted_on.isoformat() if planted_on else None,
                "pinning_days": mu.get("pinningTimeDays"), "harvest_days": mu.get("harvestTimeDays"),
            }
            if planted_on is not None and mu.get("growthTimeDays") is not None:
                # Pilz: Fruchtansatz (pinning) -> Wachstum -> Erntefenster; gleiche Phasenregeln wie beim Paket
                entry.update(package_phase(planted_on, [mu.get("pinningTimeDays") or 0, mu["growthTimeDays"], mu.get("harvestTimeDays") or 0], now))
            else:
                entry["phase"] = EMPTY
            mushrooms.append(entry)
    planted_count = sum(1 for s in full if s["phase"] != EMPTY)
    micro_count = sum(1 for s in micro if s["phase"] != EMPTY)
    return {
        "id": box["id"],
        "box_id": box["box_id"],
        "name": box["name"],
        "type": box.get("type"),
        "layout": layout,
        "mix": mix_name,
        "mix_id": mix_id,
        "schedule": schedule,
        "has_package": bool(box.get("packages")),
        "slots": full,
        "planted_count": planted_count,
        "harvest_ready": sum(1 for s in full if s["phase"] == HARVEST),
        "microgreens": micro,
        "microgreen_modules": micro_modules,
        "mode": ("double" if len(modules) >= 2 else "mixed" if modules else "mushroom" if mushrooms else "plants"),
        "plant_slot_ids": MIXED_PLANT_SLOTS if modules else list(range(plant_count)),
        "microgreens_planted": micro_count,
        "microgreens_ready": sum(1 for s in micro if s["phase"] == HARVEST),
        "mushrooms": mushrooms,
        "mushrooms_planted": sum(1 for s in mushrooms if s["phase"] != EMPTY),
        "mushrooms_ready": sum(1 for s in mushrooms if s["phase"] == HARVEST),
    }


def build_all(data: dict[str, Any], now: datetime, language: str = "de") -> dict[str, dict[str, Any]]:
    return {b["box_id"]: build_box(b, now, language) for b in data.get("box", [])}
