# Werkzeuge / Tools

Skripte, um die **eigene** GreenBox zu untersuchen. Sie sind unabhängig von Home Assistant und werden auf einem Rechner mit Bluetooth
ausgeführt (unter Windows mit `py`, unter Linux/macOS mit `python3`). Vorher: `pip install -r tools/requirements.txt`.
Die Handy-App muss geschlossen sein, weil die Box vermutlich nur eine Bluetooth-Verbindung erlaubt.

| Skript | Zweck | Schreibt? |
|---|---|---|
| `scan.py` | BLE-Geräte in der Nähe auflisten, GreenBoxen markieren | nein |
| `dump.py` | GATT-Struktur der Box auflisten, `0xFF03`/`0xFF06`/`0xFF07`/`0xFF08` lesen | nein |
| `monitor.py` | Benachrichtigungen der Box (`0xFF05`) live dekodieren | nein |
| `ctl.py` | Lichtmodus und Streifenwerte setzen (`override on\|off\|auto`, `strip 1-3 0-100`) | **ja** |
| `blink.py` | „Bei wenig Wasser blinken“ lesen/setzen (`on`/`off`) | **ja** |
| `sched.py` | Schaltzeiten lesen/setzen, Uhrzeit senden (`show`, `workdays 08:00 12`, `weekend 09:00 12`, `sync`) | **ja** |
| `extract_key.py` | API-Schlüssel der App aus einer APK/XAPK auslesen (für das Cloud-Konto) | nein |
| `cloud.py` | Boxen, Slots und Pflanzen aus deinem Cloud-Konto ausgeben (nur lesen) | nein |
| `catalog.py` | Pflanzenbibliothek aus deinem Cloud-Konto exportieren (`catalog.json`); `--schema` zeigt Feldnamen | nein |
| `make_catalog.py` | `catalog.json` zu `greenbox_catalog.json` verkleinern | nein |

## Pflanzenkatalog von Hand ablegen
Einfacher ist es, das Cloud-Konto in der Integration zu verbinden (dann lädt `greenbox.update_catalog` den Katalog). Von Hand:
```bash
python3 tools/catalog.py          # fragt E-Mail und Passwort ab, schreibt catalog.json
python3 tools/make_catalog.py     # schreibt greenbox_catalog.json
```
Die Datei `greenbox_catalog.json` kommt in den Home-Assistant-Ordner (neben `configuration.yaml`). Sie enthält Namen, Texte und Bild-Adressen
von Berlin Green sowie deine eigenen Pflanzen und darf nicht veröffentlicht werden (steht deshalb in der `.gitignore`).

## API-Schlüssel
`cloud.py` und `catalog.py` brauchen den API-Schlüssel der App: entweder als Umgebungsvariable `GB_API_KEY` oder per Eingabe. `python3 tools/extract_key.py <APK/XAPK>` liest ihn aus der App-Datei.

## Hinweise
- Das Passwort geht nur an Google (Firebase); es wird weder gespeichert noch ausgegeben. `cloud.py` und `catalog.py` schreiben Rohdaten deines Kontos in Dateien,
  die **nicht** ins Repository gehören (`cloud_dump.json`, `catalog.json`).
- Die Skripte mit „ja“ ändern den Zustand deiner Box (Licht, Zeitplan). Notiere dir vorher die aktuellen Werte (`sched.py show`).
