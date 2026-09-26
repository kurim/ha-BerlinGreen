"""Pflanzenbibliothek aus der Cloud aufbereiten (ohne Home-Assistant-Abhängigkeiten).

Die Integration liefert selbst keine Herstellerdaten mit: der Katalog wird aus dem eigenen Konto geladen
(`greenbox.update_catalog`) oder als Datei `greenbox_catalog.json` im Home-Assistant-Ordner abgelegt.
"""
from __future__ import annotations

from typing import Any

I18N = "{ de en }"

# Eine Abfrage je Teil: schlägt eine fehl, bleiben die anderen nutzbar.
QUERIES: dict[str, str] = {
    "mixes": f"""query {{ mix(where: {{visible: {{_eq: true}}}}) {{
        id name {I18N} growth_speed containsCannabis is_experimental temperature shop_link
        containedPlants {{ plant {{ id }} }} }} }}""",
    "plants": f"""query {{ plant(where: {{visible: {{_eq: true}}}}) {{
        id name {I18N} isCannabis is_experimental user_provided_name description photo growth_speed
        image {{ photo }}
        encyclopaedia {{ id text {I18N} tip {I18N} }} }} }}""",
    "microgreens": f"""query {{ microgreen(where: {{visible: {{_eq: true}}}}) {{
        id name {I18N} growthTimeDays sproutTimeDays
        encyclopedia {{ id image description {I18N} tips {I18N} }} }} }}""",
    "mushrooms": f"""query {{ mushroom(where: {{visible: {{_eq: true}}}}) {{
        id name {I18N} pinningTimeDays growthTimeDays harvestTimeDays imageURL
        encyclopedia {{ id image description {I18N} tips {I18N} }} }} }}""",
}
REQUIRED = ("mixes", "plants")  # ohne diese beiden ist der Katalog unbrauchbar


def _i18n(d: dict | None) -> dict | None:
    return {k: v for k, v in (d or {}).items() if v} or None


def _first(x: dict) -> dict:
    e = x.get("encyclopedia") if "encyclopedia" in x else x.get("encyclopaedia")
    return (e[0] if isinstance(e, list) and e else e if isinstance(e, dict) else {}) or {}


def build(raw: dict[str, Any]) -> dict[str, Any]:
    """Rohdaten der Abfragen (siehe QUERIES) -> schlanker Katalog für die Bibliothek."""
    plants: dict[str, dict] = {}
    for p in raw.get("plants", []):
        enc = _first(p)
        plants[str(p["id"])] = {
            "id": p["id"],
            "name": _i18n(p.get("name")) or ({"de": p["user_provided_name"]} if p.get("user_provided_name") else None),
            "photo": p.get("photo") or ((p.get("image") or {}).get("photo")),
            "tip": _i18n(enc.get("tip")),
            "cannabis": bool(p.get("isCannabis")),
            "own": bool(p.get("is_experimental")),
        }
    mixes = []
    for m in raw.get("mixes", []):
        speed = m.get("growth_speed") or [20, 20, 20]
        mixes.append({
            "id": m["id"],
            "name": _i18n(m.get("name")) or {"de": "Eigene Pflanzen", "en": "Own plants"},
            "schedule": [float(x) for x in speed][:3],
            "plants": [c["plant"]["id"] for c in m.get("containedPlants", []) if c.get("plant")],
            "cannabis": bool(m.get("containsCannabis")),
            "own": bool(m.get("is_experimental")),
            "shop_link": m.get("shop_link"),
        })
    micro = []
    for m in raw.get("microgreens", []):
        enc = _first(m)
        micro.append({"id": m["id"], "name": _i18n(m.get("name")), "sprout_days": m["sproutTimeDays"],
                      "growth_days": m["growthTimeDays"], "photo": enc.get("image"), "tip": _i18n(enc.get("tips"))})
    mush = []
    for m in raw.get("mushrooms", []):
        enc = _first(m)
        mush.append({"id": m["id"], "name": _i18n(m.get("name")), "pinning_days": m["pinningTimeDays"],
                     "growth_days": m["growthTimeDays"], "harvest_days": m["harvestTimeDays"],
                     "photo": m.get("imageURL") or enc.get("image")})
    return {"generated": raw.get("generated"), "mixes": mixes, "plants": plants, "microgreens": micro, "mushrooms": mush}
