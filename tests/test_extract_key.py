"""tools/extract_key.py mit selbst gebauten APK/XAPK-Dateien.   python tests/test_extract_key.py"""
import importlib.util
import io
import sys
import tempfile
import zipfile
from pathlib import Path

import _stubs

spec = importlib.util.spec_from_file_location("extract_key", _stubs.ROOT / "tools" / "extract_key.py")
ek = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ek)
K1, K2 = _stubs.FAKE_KEY, "AIza" + "y" * 35
tmp = Path(tempfile.mkdtemp())
fails = 0


def check(cond, msg):
    global fails
    print(("  ok    " if cond else "  FEHLT ") + msg)
    fails += not cond


def apk(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, d in files.items():
            z.writestr(n, d)
    return buf.getvalue()


# 1) APK, Schlüssel als UTF-8 im String-Pool
p1 = tmp / "a.apk"
p1.write_bytes(apk({"resources.arsc": b"\x00\x01 vorher " + K1.encode() + b" nachher", "AndroidManifest.xml": b"x"}))
f = ek.candidates(str(p1))
check({k for v in f.values() for k in v} == {K1}, "APK: Schlüssel als UTF-8 gefunden")
# 2) XAPK (ZIP mit APKs), Schlüssel als UTF-16LE, wie es im Android-Ressourcen-Pool vorkommt
p2 = tmp / "b.xapk"
p2.write_bytes(apk({"manifest.json": b"{}", "com.example.apk": apk({"resources.arsc": b"\x00" + K2.encode("utf-16-le") + b"\x00"}), "config.de.apk": apk({"resources.arsc": b"leer"})}))
f = ek.candidates(str(p2))
check({k for v in f.values() for k in v} == {K2} and any("com.example.apk" in w for w in f), "XAPK: verschachtelte APK durchsucht, UTF-16 gefunden")
# 3) Kandidaten in classes.dex
p3 = tmp / "c.apk"
p3.write_bytes(apk({"classes.dex": K1.encode(), "resources.arsc": b""}))
check({k for v in ek.candidates(str(p3)).values() for k in v} == {K1}, "auch in classes.dex")
# 4) kein Treffer, kein ZIP, zu kurzer Schlüssel
p4 = tmp / "d.apk"
p4.write_bytes(apk({"resources.arsc": b"AIzaZuKurz und nichts anderes"}))
check(ek.candidates(str(p4)) == {}, "zu kurzer AIza-Text zählt nicht")
p5 = tmp / "e.apk"
p5.write_bytes(b"kein zip")
sys.argv = ["extract_key.py", str(p5), "--no-check"]
check(ek.main() == 2, "keine ZIP-Datei: Fehlermeldung statt Absturz")
sys.argv = ["extract_key.py", str(p4), "--no-check"]
check(ek.main() == 1, "kein Schlüssel: Rückgabewert 1")
sys.argv = ["extract_key.py", str(p1), "--no-check"]
check(ek.main() == 0, "Treffer: Rückgabewert 0 (ohne Anfrage an Google)")
# 5) Mehrere Kandidaten werden alle gemeldet
p6 = tmp / "f.apk"
p6.write_bytes(apk({"resources.arsc": K1.encode() + b" " + K2.encode()}))
check({k for v in ek.candidates(str(p6)).values() for k in v} == {K1, K2}, "mehrere Kandidaten werden alle gefunden")
# 6) Prüfung bei Google wird nicht ausgeführt, wenn --no-check gesetzt ist (kein Netz im Test)
called = []
ek.probe = lambda k: called.append(k) or "ok"
sys.argv = ["extract_key.py", str(p1), "--no-check"]
ek.main()
check(called == [], "--no-check fragt Google nicht")
sys.argv = ["extract_key.py", str(p1)]
ek.main()
check(called == [K1], "ohne --no-check wird jeder Kandidat einmal geprüft")
print("\n" + ("%d FEHLER" % fails if fails else "alle Tests ok"))
sys.exit(1 if fails else 0)
