"""Findet den Firebase-API-Schlüssel der Berlin-Green-App in einer APK oder XAPK.

  python tools/extract_key.py pfad/zur/GreenBoxApp.xapk

Die Integration enthält den Schlüssel aus Rücksicht auf den Hersteller nicht; beim Einrichten des Cloud-Kontos wird er abgefragt.
So kommst du an die Datei: die App aus dem Play Store auf dem Handy sichern (z. B. `adb shell pm path com.berlingreen.android`,
dann `adb pull <pfad>`) oder eine APK/XAPK von einem Anbieter deiner Wahl laden. Das Skript liest die Datei nur, es installiert nichts.

Vorgehen: APK/XAPK sind ZIP-Dateien; der Schlüssel steht als Text in `resources.arsc` (Wert von `google_api_key`).
Gefundene Kandidaten werden mit einer einzigen Anfrage an Google geprüft (dummy-Konto, keine Anmeldung); mit --no-check entfällt das."""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import urllib.error
import urllib.request
import zipfile

KEY = re.compile(rb"AIza[0-9A-Za-z_\-]{35}")
KEY_UTF16 = re.compile(rb"(?:A\x00I\x00z\x00a\x00)(?:[0-9A-Za-z_\-]\x00){35}")
PROBE = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={key}"


def scan(data: bytes) -> set[str]:
    found = {m.group().decode() for m in KEY.finditer(data)}
    found |= {m.group().decode("utf-16-le") for m in KEY_UTF16.finditer(data)}
    return found


def candidates(path: str) -> dict[str, set[str]]:
    """Schlüssel je Fundort. Ein XAPK/APKS enthält APKs im ZIP; jede wird durchsucht."""
    out: dict[str, set[str]] = {}

    def walk(zf: zipfile.ZipFile, label: str) -> None:
        for name in zf.namelist():
            low = name.lower()
            if low.endswith(".apk"):
                with zf.open(name) as fh:
                    walk(zipfile.ZipFile(io.BytesIO(fh.read())), f"{label}/{name}")
            elif low == "resources.arsc" or (low.startswith("classes") and low.endswith(".dex")):
                keys = scan(zf.read(name))
                if keys:
                    out.setdefault(f"{label}:{name}", set()).update(keys)

    with zipfile.ZipFile(path) as zf:
        walk(zf, path.rsplit("/", 1)[-1])
    return out


def probe(key: str) -> str:
    """Firebase-Anmeldung mit einem Dummy-Konto: verrät, ob der Schlüssel zum Anmelden taugt."""
    body = json.dumps({"email": "nobody@example.invalid", "password": "x", "returnSecureToken": True}).encode()
    req = urllib.request.Request(PROBE.format(key=key), data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=20)
        return "ok"
    except urllib.error.HTTPError as err:
        text = err.read().decode("utf-8", "replace")
        if "EMAIL_NOT_FOUND" in text or "INVALID_LOGIN_CREDENTIALS" in text or "INVALID_PASSWORD" in text:
            return "ok"
        if "API key not valid" in text or "API_KEY_INVALID" in text:
            return "ungültig"
        if "blocked" in text.lower():
            return "auf die App beschränkt (nicht nutzbar)"
        return f"unklar (HTTP {err.code})"
    except OSError as err:
        return f"nicht geprüft ({err})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("datei", help="APK oder XAPK der Berlin-Green-App")
    ap.add_argument("--no-check", action="store_true", help="Kandidaten nicht bei Google prüfen")
    args = ap.parse_args()
    try:
        found = candidates(args.datei)
    except (OSError, zipfile.BadZipFile) as err:
        print(f"Datei nicht lesbar: {err}")
        return 2
    keys = sorted({k for v in found.values() for k in v})
    if not keys:
        print("Kein Schlüssel gefunden. Ist das die APK/XAPK der Berlin-Green-App (com.berlingreen.android)?")
        return 1
    usable = []
    for k in keys:
        status = "nicht geprüft" if args.no_check else probe(k)
        where = ", ".join(sorted(w for w, v in found.items() if k in v))
        print(f"{k}  [{status}]  ({where})")
        if status == "ok":
            usable.append(k)
    if len(keys) == 1 or len(usable) == 1:
        print("\nDiesen Schlüssel in Home Assistant eintragen:", (usable or keys)[0])
    elif not usable:
        print("\nKein Kandidat war nutzbar.")
        return 1
    else:
        print("\nMehrere Kandidaten sind nutzbar; nimm den, der in resources.arsc steht (google_api_key).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
