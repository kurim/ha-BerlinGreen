"""Fotos: Umwandlung in einfärbbare PNGs, Herunterladen, Zuordnung der lokalen Adresse.   python tests/test_photos.py"""
import asyncio
import importlib
import io
import sys
import tempfile
from pathlib import Path

import _stubs

_stubs.install()
_stubs.package(with_init=False)
photos = importlib.import_module("greenbox.photos")
library = importlib.import_module("greenbox.library")
from PIL import Image, ImageDraw  # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    print(("  ok    " if cond else "  FEHLT ") + msg)
    fails += not cond


def drawing(size=800, mode="RGB", fmt="JPEG") -> bytes:
    """Schwarzer Kreis (Strich) auf weißem Grund, wie die Pflanzenzeichnungen."""
    img = Image.new("RGB", (size, size), (255, 255, 255))
    ImageDraw.Draw(img).ellipse((size // 4, size // 4, size * 3 // 4, size * 3 // 4), outline=(0, 0, 0), width=size // 40)
    buf = io.BytesIO()
    img.convert(mode).save(buf, fmt)
    return buf.getvalue()


print("Umwandlung")
png = Image.open(io.BytesIO(photos.to_png(drawing())))
alpha = png.getchannel("A")
check(png.format == "PNG" and png.mode == "RGBA" and max(png.size) == photos.SIZE, "kleines PNG mit Transparenz")
check(alpha.getpixel((0, 0)) == 0 and alpha.getpixel((png.width // 2, png.height // 2)) == 0, "weißer Hintergrund und Innenfläche sind durchsichtig")
check(alpha.getpixel((png.width // 4, png.height // 2)) > 100 and png.getpixel((png.width // 4, png.height // 2))[:3] == (0, 0, 0), "Linien bleiben schwarz und sichtbar (Maske zum Einfärben)")
check(all(png.getpixel((x, 5))[3] == 0 for x in range(png.width)), "JPEG-Rauschen im Weiß wird abgeschnitten")
check(Image.open(io.BytesIO(photos.to_png(drawing(fmt="PNG")))).getchannel("A").getpixel((0, 0)) == 0, "auch PNG als Quelle")
try:
    photos.to_png(b"kein bild")
    check(False, "Unbrauchbare Daten lösen einen Fehler aus")
except Exception:  # noqa: BLE001
    check(True, "Unbrauchbare Daten lösen einen Fehler aus")

print("Adressen")
u = "https://cdn.example/a.jpg"
check(photos.file_name(u) == photos.file_name(u) and photos.file_name(u).endswith(".png") and photos.file_name(u) != photos.file_name(u + "x"), "Dateiname ist stabil und je Adresse verschieden")
cat = {"plants": {"1": {"photo": u}, "2": {"photo": None}, "3": {"photo": "http://unsicher/x.jpg"}}, "microgreens": [{"photo": u}, {"photo": "https://cdn.example/b.jpg"}], "mushrooms": []}
check(photos.collect_urls(cat) == {u, "https://cdn.example/b.jpg"}, "nur https-Adressen, ohne Doppelte")


class Resp:
    def __init__(self, status, body): self.status, self.content = status, self
    async def iter_chunked(self, n):
        for i in range(0, len(self.body), 1000):  # wie im Netz: in kleinen Häppchen, nicht am Stück
            yield self.body[i:i + 1000]
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


class Session:
    def __init__(self, files): self.files, self.calls = files, []
    def get(self, url, timeout=None):
        self.calls.append(url)
        status, body = self.files.get(url, (404, b""))
        r = Resp(status, body)
        r.body = body
        return r


async def run_blocking(f, *a): return f(*a)


async def main():
    folder = Path(tempfile.mkdtemp()) / "greenbox_photos"
    ok, missing, broken = "https://cdn.example/ok.jpg", "https://cdn.example/missing.jpg", "https://cdn.example/broken.jpg"
    session = Session({ok: (200, drawing()), broken: (200, b"<html>kein Bild</html>")})
    print("Herunterladen")
    fired = []
    done, failed = await photos.sync(session, folder, [ok, missing, broken, ok, "http://x/y.jpg"], run_blocking, lambda: fired.append(1))
    check((done, failed) == (1, 2) and (folder / photos.file_name(ok)).is_file() and fired == [1], "ein Foto geladen, fehlende und defekte übersprungen, ohne Abbruch")
    check(session.calls.count(ok) == 1 and "http://x/y.jpg" not in session.calls, "Doppelte nur einmal, kein http")
    session.calls.clear()
    done, failed = await photos.sync(session, folder, [ok], run_blocking)
    check((done, failed) == (0, 0) and session.calls == [], "vorhandene Fotos werden nicht erneut geladen")
    big = Session({ok + "2": (200, b"x" * (photos.MAX_DOWNLOAD + 5))})
    check(await photos.sync(big, folder, [ok + "2"], run_blocking) == (0, 1), "zu große Dateien werden abgelehnt")

    print("Zuordnung")
    lib = library.Library({"mixes": [{"id": 1, "name": {"de": "Mix"}, "schedule": [1, 1, 1], "plants": [1]}],
                           "plants": {"1": {"id": 1, "name": {"de": "Koriander"}, "photo": ok}}, "microgreens": [
                               {"id": 5, "name": {"de": "Kresse"}, "photo": missing, "sprout_days": 1, "growth_days": 2}]})
    mapped = lib.public("de", lambda url: "/greenbox_photos/" + photos.file_name(url) if url == ok else url)
    check(mapped["plants"][0]["photo"] == "/greenbox_photos/" + photos.file_name(ok) and mapped["microgreens"][0]["photo"] == missing,
          "Katalog nennt die lokale Adresse, sonst die Originaladresse")
    check(lib.public("de")["plants"][0]["photo"] == ok, "ohne Zuordnung unverändert")


asyncio.run(main())
print("\n" + ("%d FEHLER" % fails if fails else "alle Tests ok"))
sys.exit(1 if fails else 0)
