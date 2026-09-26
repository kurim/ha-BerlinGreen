"""Lädt die Pflanzenbibliothek der Berlin-Green-Cloud in eine lokale Datei (NUR LESEN).

  py catalog.py            -> catalog.json (Rohdaten: Mixe, Pflanzen, Microgreens, Pilze)
  py make_catalog.py       -> greenbox_catalog.json (schlank; in den Home-Assistant-Ordner legen)
  py catalog.py --schema   -> schema.json  (Feldnamen der wichtigsten Server-Typen, hilft beim Anpassen der Abfragen)

Benutzt dieselbe Anmeldung wie cloud.py (E-Mail/Passwort oder GB_EMAIL / GB_PASSWORD). Jeder Teil wird einzeln abgefragt:
schlägt einer fehl (z. B. weil ein Feld anders heißt), werden die anderen trotzdem gespeichert.
Hinweis: Namen, Texte und Bilder gehören Berlin Green. Die Datei ist für deine eigene Nutzung gedacht, nicht zum Weitergeben."""
import getpass
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import cloud

I18N = "{ de en }"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components" / "greenbox"))
from catalog_build import QUERIES as PARTS  # noqa: E402  (dieselben Abfragen wie die Integration)

SCHEMA_TYPES = ["mix", "plant", "microgreen", "mushroom", "package", "planted", "planted_microgreen", "planted_mushroom", "box", "plant_mix"]
SCHEMA_QUERY = """query($n: String!) { __type(name: $n) { name fields { name type { name kind ofType { name kind ofType { name kind } } } } } }"""


def type_name(t: dict | None) -> str:
    if not t:
        return "?"
    if t.get("name"):
        return t["name"]
    inner = type_name(t.get("ofType"))
    return f"[{inner}]" if t.get("kind") == "LIST" else f"{inner}!" if t.get("kind") == "NON_NULL" else inner


def get_token() -> str:
    email = os.environ.get("GB_EMAIL") or input("E-Mail: ").strip()
    password = os.environ.get("GB_PASSWORD") or getpass.getpass("Passwort (wird nicht angezeigt): ")
    print("Anmeldung ...")
    return cloud.login(email, password)


def export_catalog(token: str) -> dict:
    out: dict = {"generated": datetime.now(timezone.utc).isoformat(), "errors": {}}
    for name, query in PARTS.items():
        try:
            data = cloud.graphql(token, query)
            (rows,) = data.values()
            out[name] = rows
            print(f"  {name:13} {len(rows):4} Einträge")
        except cloud.CloudError as err:
            out[name] = []
            out["errors"][name] = str(err)[:400]
            print(f"  {name:13} FEHLER: {str(err)[:200]}")
    return out


def export_schema(token: str) -> dict:
    out = {}
    for t in SCHEMA_TYPES:
        try:
            info = cloud.graphql_vars(token, SCHEMA_QUERY, {"n": t})["__type"]
        except cloud.CloudError as err:
            out[t] = f"FEHLER: {str(err)[:200]}"
            print(f"  {t:20} FEHLER")
            continue
        if not info:
            out[t] = None
            print(f"  {t:20} (nicht sichtbar)")
            continue
        out[t] = {f["name"]: type_name(f["type"]) for f in info["fields"]}
        print(f"  {t:20} {len(out[t])} Felder: {', '.join(list(out[t])[:12])}{' ...' if len(out[t]) > 12 else ''}")
    return out


def main() -> None:
    schema = "--schema" in sys.argv[1:]
    try:
        token = get_token()
        print("Schema abfragen ..." if schema else "Bibliothek laden ...")
        result = export_schema(token) if schema else export_catalog(token)
    except cloud.CloudError as err:
        print("Fehler:", err)
        sys.exit(1)
    name = "schema.json" if schema else "catalog.json"
    with open(name, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"\nGespeichert: {name}")
    if not schema and result["errors"]:
        print("Einige Teile sind fehlgeschlagen. Starte 'py catalog.py --schema' und schick mir die Ausgabe, dann passe ich die Felder an.")


if __name__ == "__main__":
    main()
