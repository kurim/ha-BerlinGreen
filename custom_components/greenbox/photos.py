"""Pflanzenbilder lokal zwischenspeichern: klein, als PNG mit durchsichtigem Hintergrund (einfärbbar).

Die Fotos gehören Berlin Green und liegen deshalb NICHT im Repository; jede Installation lädt sie selbst in ihren
Home-Assistant-Ordner (greenbox_photos/). Ohne Pillow oder ohne Netz zeigt die Karte weiter die Originaladresse."""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)

PHOTO_DIR = "greenbox_photos"  # im Home-Assistant-Ordner
PHOTO_URL = "/greenbox_photos"  # so ausgeliefert
SIZE = 192  # längste Kante in Pixel (die Karte zeigt sie deutlich kleiner)
MAX_DOWNLOAD = 12 * 1024 * 1024
WHITE_LEVEL = 24  # so viel Abweichung vom reinen Weiß gilt noch als Hintergrund (JPEG-Rauschen)
PARALLEL = 4


def file_name(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16] + ".png"


def wanted(url: object) -> bool:
    return isinstance(url, str) and url.startswith("https://")


def collect_urls(catalog: dict[str, Any]) -> set[str]:
    """Alle Foto-Adressen eines Katalogs (Pflanzen, Microgreens, Pilze)."""
    found = [p.get("photo") for p in catalog.get("plants", {}).values()]
    found += [m.get("photo") for m in catalog.get("microgreens", [])]
    found += [m.get("photo") for m in catalog.get("mushrooms", [])]
    return {u for u in found if wanted(u)}


def to_png(data: bytes, size: int = SIZE) -> bytes:
    """Strichzeichnung (dunkel auf weiß) -> kleines PNG: schwarze Linien, Transparenz = Strichstärke, Weiß wird durchsichtig.

    So kann die Karte das Bild als Maske nutzen und in jeder Farbe (Phase, Theme) einfärben."""
    from PIL import Image, ImageFilter, ImageOps  # Bestandteil von Home Assistant

    img = Image.open(io.BytesIO(data))
    img.draft("RGB", (size * 2, size * 2))  # JPEG gleich verkleinert dekodieren (Originale sind ~4000 px)
    if img.mode in ("RGBA", "LA", "P"):  # vorhandene Transparenz auf Weiß legen
        img = img.convert("RGBA")
        flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
        flat.alpha_composite(img)
        img = flat
    gray = img.convert("L")
    gray.thumbnail((size, size), Image.LANCZOS)
    gray = gray.filter(ImageFilter.MinFilter(3))  # dünne Linien etwas kräftiger, damit sie klein noch lesbar sind
    alpha = ImageOps.invert(gray).point(lambda v: 0 if v < WHITE_LEVEL else v)  # Rauschen im Weiß abschneiden
    out = Image.new("RGBA", gray.size, (0, 0, 0, 0))
    out.putalpha(alpha)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def existing(folder: Path) -> set[str]:
    try:
        return {p.name for p in folder.glob("*.png")}
    except OSError:
        return set()


async def _fetch(session: Any, url: str) -> bytes | None:
    async with session.get(url, timeout=30) as resp:
        if resp.status != 200:
            return None
        data = await resp.content.read(MAX_DOWNLOAD + 1)
        return data if len(data) <= MAX_DOWNLOAD else None


async def sync(session: Any, folder: Path, urls: Iterable[str], run_blocking: Callable[..., Any],
               on_progress: Callable[[], None] | None = None) -> tuple[int, int]:
    """Lädt fehlende Fotos. Liefert (neu geladen, fehlgeschlagen). Einzelne Fehler stoppen nichts."""
    await run_blocking(lambda: folder.mkdir(parents=True, exist_ok=True))
    have = await run_blocking(existing, folder)
    todo = [u for u in dict.fromkeys(urls) if wanted(u) and file_name(u) not in have]
    gate, done, failed = asyncio.Semaphore(PARALLEL), 0, 0

    async def one(url: str) -> None:
        nonlocal done, failed
        async with gate:
            try:
                raw = await _fetch(session, url)
                if raw is None:
                    raise ValueError("Antwort unbrauchbar")
                png = await run_blocking(to_png, raw)
                await run_blocking((folder / file_name(url)).write_bytes, png)
                done += 1
            except Exception as err:  # noqa: BLE001 - ein defektes Foto darf die anderen nicht aufhalten
                failed += 1
                _LOGGER.debug("Foto %s nicht geladen: %s", url, err)

    await asyncio.gather(*(one(u) for u in todo))
    if done and on_progress:
        on_progress()
    return done, failed
