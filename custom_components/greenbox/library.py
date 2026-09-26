"""Pflanzenbibliothek (catalog.json) mit Suche nach Name oder ID (ohne Home-Assistant-Abhängigkeiten)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class GardenError(ValueError):
    """Fehler mit lesbarer Meldung (wird im Dienstaufruf angezeigt)."""


def _names(item: dict[str, Any]) -> list[str]:
    n = item.get("name") or {}
    return [v.strip().lower() for v in n.values() if isinstance(v, str)]


class Library:
    def __init__(self, data: dict[str, Any], allow_cannabis: bool = False) -> None:
        self.data = data
        self.allow_cannabis = allow_cannabis
        self.mixes: list[dict] = data["mixes"]
        self.plants: dict[str, dict] = data["plants"]
        self.microgreens: list[dict] = data["microgreens"]
        self.mushrooms: list[dict] = data.get("mushrooms", [])

    @classmethod
    def load(cls, path: Path, allow_cannabis: bool = False) -> "Library":
        return cls(json.loads(path.read_text(encoding="utf-8")), allow_cannabis)

    @classmethod
    def empty(cls, allow_cannabis: bool = False) -> "Library":
        """Ohne Katalog: nur eigene Zeitpläne mit frei getippten Namen (siehe local.py)."""
        return cls({"mixes": [], "plants": {}, "microgreens": [], "mushrooms": []}, allow_cannabis)

    @property
    def is_empty(self) -> bool:
        return not self.mixes and not self.plants and not self.microgreens

    @staticmethod
    def valid(data: object) -> bool:
        """Grobe Prüfung einer Katalogdatei, bevor sie verwendet wird."""
        return (isinstance(data, dict) and isinstance(data.get("mixes"), list) and isinstance(data.get("plants"), dict)
                and isinstance(data.get("microgreens"), list))

    # --- Anzeige ------------------------------------------------------------------
    @staticmethod
    def label(item: dict[str, Any] | None, lang: str = "de") -> str | None:
        n = (item or {}).get("name") or {}
        return n.get(lang) or n.get("en") or n.get("de") or next(iter(n.values()), None)

    def visible_mix(self, m: dict) -> bool:
        return self.allow_cannabis or not m.get("cannabis")

    def visible_plant(self, p: dict) -> bool:
        return self.allow_cannabis or not p.get("cannabis")

    # --- Suche ----------------------------------------------------------------------
    def _find(self, ref: Any, items: list[dict], kind: str) -> dict:
        if isinstance(ref, int) or (isinstance(ref, str) and ref.strip().isdigit()):
            for it in items:
                if it["id"] == int(ref):
                    return it
            raise GardenError(f"{kind} mit der ID {ref} gibt es nicht")
        text = str(ref).strip().lower()
        exact = [it for it in items if text in _names(it)]
        hits = exact or [it for it in items if any(text in n for n in _names(it))]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise GardenError(f"{kind} '{ref}' nicht gefunden")
        raise GardenError(f"{kind} '{ref}' ist nicht eindeutig: " + ", ".join(f"{self.label(h)} (ID {h['id']})" for h in hits[:8]))

    def find_mix(self, ref: Any) -> dict:
        mix = self._find(ref, [m for m in self.mixes if self.visible_mix(m) or m.get("own")], "Mix")
        if mix.get("cannabis") and not self.allow_cannabis:
            raise GardenError("Dieser Mix ist ausgeblendet (Option 'Cannabis anzeigen' ist aus)")
        return mix

    def find_plant(self, ref: Any, among: list[int] | None = None) -> dict:
        pool = [p for p in self.plants.values() if self.visible_plant(p)]
        if among is None:
            return self._find(ref, pool, "Pflanze")
        allowed = {int(i) for i in among}
        try:
            return self._find(ref, [p for p in pool if p["id"] in allowed], "Pflanze")
        except GardenError as err:
            try:
                other = self._find(ref, pool, "Pflanze")  # gibt es die Pflanze, nur nicht in diesem Mix?
            except GardenError:
                raise err from None
            options = ", ".join(sorted(self.label(p) or "?" for p in pool if p["id"] in allowed))
            raise GardenError(f"'{self.label(other)}' gehört nicht zu diesem Mix. Möglich: {options}") from None

    def find_microgreen(self, ref: Any) -> dict:
        return self._find(ref, self.microgreens, "Microgreen")

    def plants_of_mix(self, mix: dict) -> list[dict]:
        return [self.plants[str(i)] for i in mix["plants"] if str(i) in self.plants and self.visible_plant(self.plants[str(i)])]

    def custom_mix(self) -> dict | None:
        return next((m for m in self.mixes if m.get("own")), None)

    # --- Für die Card (klein halten) -----------------------------------------------
    def public(self, lang: str = "de", photo=None) -> dict[str, Any]:
        photo = photo or (lambda url: url)

        def plant(p: dict) -> dict:
            return {"id": p["id"], "name": self.label(p, lang), "photo": photo(p.get("photo")), "own": p.get("own", False)}

        return {
            "mixes": [
                {"id": m["id"], "name": self.label(m, lang), "schedule": m["schedule"], "own": m.get("own", False),
                 "plants": [plant(p) for p in self.plants_of_mix(m)]}
                for m in self.mixes if self.visible_mix(m) or m.get("own")
            ],
            "plants": [plant(p) for p in self.plants.values() if self.visible_plant(p)],
            "microgreens": [{"id": m["id"], "name": self.label(m, lang), "photo": photo(m.get("photo")),
                             "sprout_days": m["sprout_days"], "growth_days": m["growth_days"]} for m in self.microgreens],
            "empty": self.is_empty,
        }
