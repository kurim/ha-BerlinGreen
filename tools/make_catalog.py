"""Verkleinert catalog.json (Rohdaten von catalog.py) zu greenbox_catalog.json.

  py make_catalog.py [catalog.json] [greenbox_catalog.json]

Die Datei `greenbox_catalog.json` gehört in den Home-Assistant-Konfigurationsordner (neben configuration.yaml).
Einfacher: Cloud-Konto in der Integration verbinden, dann lädt `greenbox.update_catalog` den Katalog selbst.
Der Katalog enthält Namen, Texte und Bild-Adressen von Berlin Green sowie deine eigenen Pflanzen: nicht veröffentlichen."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components" / "greenbox"))
from catalog_build import build  # noqa: E402

if __name__ == "__main__":
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "catalog.json")
    dst = Path(sys.argv[2] if len(sys.argv) > 2 else "greenbox_catalog.json")
    out = build(json.loads(src.read_text(encoding="utf-8")))
    dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{dst} ({dst.stat().st_size // 1024} KB): {len(out['mixes'])} Mixe, {len(out['plants'])} Pflanzen, "
          f"{len(out['microgreens'])} Microgreens, {len(out['mushrooms'])} Pilze")
