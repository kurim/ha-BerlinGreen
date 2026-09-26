# Berlin Green GreenBox für Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Validate](https://github.com/kurim/ha-BerlinGreen/actions/workflows/validate.yml/badge.svg)](https://github.com/kurim/ha-BerlinGreen/actions/workflows/validate.yml)
[![Tests](https://github.com/kurim/ha-BerlinGreen/actions/workflows/tests.yml/badge.svg)](https://github.com/kurim/ha-BerlinGreen/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/kurim/ha-BerlinGreen/blob/main/LICENSE)

Steuere deine [Berlin Green](https://berlingreen.com) GreenBox per Bluetooth aus Home Assistant und behalte im Blick, was darin wächst.
Dazu gibt es eine Lovelace-Karte, die aussieht wie die App. English version: [README.md](https://github.com/kurim/ha-BerlinGreen/blob/main/README.md).

> **Inoffiziell.** Dieses Projekt steht in keiner Verbindung zu Berlin Green und wird dort weder empfohlen noch unterstützt. „Berlin Green“
> und „GreenBox“ sind deren Namen. Es entstand durch Analyse der Android-App und Tests an einer einzigen Box, also rechne mit Ecken und
> Kanten (siehe [Einschränkungen](#einschränkungen)). Die optionalen Cloud-Funktionen nutzen dieselben Schnittstellen wie die App und können
> jederzeit aufhören zu funktionieren. Nutzung auf eigenes Risiko.

## Funktionen

**Steuerung (Bluetooth, je Box)**
- Lichtmodus (Automatik/An/Aus), Lichtprofile (Wachstum, Medium, Ambient, Nachtlicht), Farbtemperatur, Helligkeit
- Zeitplan: Startzeit und Dauer (12–18 h) für Werktage und Wochenende in Ortszeit; die Uhr der Box wird bei jeder Verbindung gestellt
- Wasserstand (Prozent und Status), Schalter „Bei wenig Wasser blinken“, Firmware und Hardware-Revision

**Garten (lokal, Cloud optional)**
- Pflanzen mit Wachstumsphasen (Keimung → Wachstum → Ernte) je Slot: 8 runde Töpfchen oder 4 Töpfchen plus Microgreens-Modul mit 6 Feldern, genau wie in der App
- Alles wird in Home Assistant gespeichert; es wird nichts an Berlin Green gesendet
- Ein Sensor je Box und ein Phasen-Sensor je Slot, z. B. für Automationen wie „Ernte ist bereit“
- Lovelace-Karte mit visuellem Editor; Slot antippen zum Bepflanzen, Ändern oder Leeren. Die Integration liefert die Karte selbst aus, es muss keine Ressource eingetragen werden

**Cloud-Konto (optional, nur lesend)**
- Zeigt, was die App zeigt, lädt die Pflanzenbibliothek für dich (`greenbox.update_catalog`) und listet Boxen ohne Bluetooth-Verbindung
- Gespeichert wird nur das Anmelde-Token, nie dein Passwort. Anmeldung über Google/Apple wird nicht unterstützt

## Voraussetzungen
- Home Assistant 2025.1 oder neuer mit Bluetooth-Adapter (oder ESP32-Bluetooth-Proxy), der die Box erreicht
- Eine GreenBox. Entwickelt und getestet mit einer Standard-Box mit Firmware 2.0.3

## Installation

### HACS (benutzerdefiniertes Repository)
1. HACS → ⋮ → **Benutzerdefinierte Repositories** → `https://github.com/kurim/ha-BerlinGreen` als **Integration** hinzufügen.
2. **Berlin Green GreenBox (unofficial)** installieren und Home Assistant neu starten.

### Manuell
`custom_components/greenbox` nach `<config>/custom_components/greenbox` kopieren und Home Assistant neu starten.

## Einrichtung
Einstellungen → Geräte & Dienste → **Integration hinzufügen** → *Berlin Green GreenBox*:
- **Bluetooth-Box**: wird automatisch gefunden (Name `GreenBox…`). Ein Eintrag pro Box. **Vorher die Handy-App schließen**: die Box erlaubt vermutlich nur eine Bluetooth-Verbindung.
- **Cloud-Konto (optional)**: dein Login der Berlin-Green-App **plus der API-Schlüssel der App** (siehe unten). Einmal hinzufügen, gilt für alle Boxen. Zum Trennen den Eintrag löschen.

Bei großer Entfernung (etwa −85 dBm) sind Verbindungen langsam oder brechen ab. Adapter oder Proxy näher an die Box stellen.

### Der API-Schlüssel der App (nur für das Cloud-Konto)
Das Cloud-Konto meldet sich wie die App über Google Firebase an und braucht dafür den öffentlichen API-Schlüssel der App. Er wird aus Rücksicht auf den
Hersteller **nicht** mit der Integration geliefert, du trägst ihn einmal beim Hinzufügen des Cloud-Kontos ein. Er steht als Text in der App-Datei und lässt sich leicht auslesen:
```bash
python tools/extract_key.py GreenBoxApp.xapk     # oder eine .apk
```
Die App-Datei bekommst du vom Handy (`adb shell pm path com.berlingreen.android`, dann `adb pull <Pfad>`) oder von einem APK-Anbieter deiner Wahl.
Das Skript liest die Datei nur, findet den Schlüssel (beginnt mit `AIza`, 39 Zeichen) und prüft ihn mit einer einzigen Anfrage an Google. Ohne Cloud-Konto brauchst du davon nichts.

## Der Pflanzenkatalog
Der Katalog (Mixe mit Zeitplänen, Pflanzen, Microgreens) gehört Berlin Green und ist **nicht** Teil dieses Repositories. Er wird geladen, sobald du das
Cloud-Konto verbindest (oder `greenbox.update_catalog` ausführst), und in Home Assistant gespeichert. Ohne Katalog kannst du trotzdem mit
**eigenem Zeitplan** und frei getippten Pflanzennamen pflanzen. Alternativ legst du eine `greenbox_catalog.json` neben die `configuration.yaml`,
siehe [`tools/`](https://github.com/kurim/ha-BerlinGreen/blob/main/tools/README.md).

**Fotos:** Die Pflanzenzeichnungen werden in den Ordner `greenbox_photos/` deines Home-Assistant-Ordners geladen (nach einem Neustart auch im Hintergrund),
in kleine PNGs mit durchsichtigem Hintergrund umgewandelt und als Maske genutzt. So färbt die Karte sie auf jedem Theme in der Phasenfarbe ein
(`show_images: true`). Der Button **Katalog und Fotos aktualisieren** am Cloud-Konto (oder `greenbox.update_catalog`) lädt alles neu. Die Fotos sind nie
Teil dieses Repositories; lässt sich eines nicht laden, nutzt die Karte weiter die Originaladresse. Nach einem fehlgeschlagenen Start wird der
Katalog automatisch bis zu dreimal erneut geladen.

## Lovelace-Karte
```yaml
type: custom:greenbox-garden-card
entity: sensor.<box>_garten        # oder den visuellen Editor benutzen
```
Optionen: `style` (`app` oder `tiles`), `show_images`, `microgreens` (`auto` oder `false`), `editable` und für Kacheln `columns` und `microgreen_slots`.

Aufbau wie in der App: ohne Microgreens-Modul 4 × 2 runde Töpfchen; mit Modul links 6 eckige Felder und rechts 4 Töpfchen (Slots 1, 2, 5, 6).
Erscheint die Karte nach einem Update nicht, den Browser-Cache leeren (Strg+F5).

## Benachrichtigungen (Push an die Home-Assistant-App)
- **Erntereif:** Wird ein Topf oder ein Microgreens-Feld erntereif, löst die Integration das Ereignis `greenbox_harvest_ready` aus, mit `box`, `box_name`, `area`
  (`plants`/`microgreens`), `slot` (ab 1), `plant` und `plant_id`. Töpfe, die beim Start von Home Assistant schon reif sind, werden nicht erneut gemeldet.
  Blueprint: [![Open your Home Assistant instance and show the blueprint import dialog](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fkurim%2Fha-BerlinGreen%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fgreenbox%2Fharvest_ready.yaml)
- **Wasser kritisch:** Der Sensor „Wasserstatus“ einer Box springt auf `low` (niedrig) oder `empty` (leer). Blueprint: [![Open your Home Assistant instance and show the blueprint import dialog](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fkurim%2Fha-BerlinGreen%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fgreenbox%2Fwater_low.yaml)

Beide Blueprints fragen nach deinem Handy (Home-Assistant-App); Titel und Text kannst du anpassen. Jede andere Automation geht auch, z. B. mit dem Ereignis als
Auslöser und `notify.mobile_app_<handy>`.

## Dienste
Slots zählen ab 1. `box` ist bei nur einer Box optional (sonst Name oder Adresse).

| Dienst | Was er tut |
|---|---|
| `greenbox.plant_package` | Mix (oder eigenen Zeitplan mit getippten Namen) und die Pflanzen je Slot pflanzen |
| `greenbox.plant_slot` / `clear_slot` | Pflanze in einen Slot setzen / Slot leeren. `plant_slot` mit `mix` oder `germination_days`/`growth_days`/`harvest_days` (und `planted_at`) gibt dem Slot ein **eigenes Paket** (andere Keim- und Wachstumszeiten); nur lokal |
| `greenbox.remove_package` | Ganzes Paket entfernen |
| `greenbox.plant_microgreen` / `clear_microgreen` | Microgreens-Modul (Slots 1–6); Namen ohne Katalogeintrag brauchen `sprout_days` und `growth_days` |
| `greenbox.import_from_cloud` | Bepflanzung der App für eine Box in Home Assistant übernehmen (auch als Button **Garten aus der Cloud übernehmen** an der Box; ersetzt deren lokale Bepflanzung) |
| `greenbox.update_catalog` | Pflanzenbibliothek und Fotos aus dem Cloud-Konto neu laden |

Regeln wie in der App: Ein Mix hat einen gemeinsamen Zeitplan und erlaubt nur seine eigenen Pflanzen; solange das Microgreens-Modul benutzt wird, sind für Pflanzen nur die Slots 1, 2, 5 und 6 frei.

## Einschränkungen
- Getestet mit einer Standard-Box, Firmware 2.0.3 (dort werden Startzeiten in UTC gespeichert). Firmware 4.x hat zusätzliche Eigenschaften für Zeitzone/OTA, die noch nicht genutzt oder getestet sind. Plus-Boxen sind ungetestet.
- Nicht unterstützt: Schreiben in die Cloud, Pilz-Modul, Layout „ThreeSlot“, Firmware-Updates, WLAN-Einrichtung.
- Die Box meldet ihre Uhr nicht zurück; die Integration sendet die Zeit bei jeder Verbindung.
- Home Assistant und die Handy-App können die Box nicht gleichzeitig nutzen.

## Datenschutz und Sicherheit
- Bluetooth-Steuerung und Garten laufen komplett lokal. Lokale Daten liegen in `.storage/greenbox_garden_local` und `.storage/greenbox_catalog`.
- Mit Cloud-Konto spricht die Integration mit Google (Firebase-Anmeldung) und `backend.berlingreen.tech` (dem GraphQL-Server der App), nur lesend, alle 15 Minuten.
- Der Firebase-Schlüssel der App gehört nicht zu diesem Repository; du trägst ihn selbst ein (siehe oben). Er liegt im Konfigurationseintrag von Home Assistant.
- Bitte poste nie Passwörter, Tokens oder Exporte deines Kontos in Issues.

## Dokumentation
- [`docs/PROTOCOL.md`](https://github.com/kurim/ha-BerlinGreen/blob/main/docs/PROTOCOL.md) – Bluetooth-Protokoll und Cloud-Datenmodell (deutsch, mit englischer Kurzübersicht)
- [`tools/`](https://github.com/kurim/ha-BerlinGreen/blob/main/tools/README.md) – Skripte zum Scannen, Auslesen und Steuern der eigenen Box und zum Export der Pflanzenbibliothek

## Entwicklung
```bash
pip install voluptuous pyyaml
python tests/test_metadata.py && python tests/test_logic.py && python tests/test_hub.py && python tests/test_flow.py
python tests/make_card_fixtures.py && cd tests/card && npm ci && npm test
```
Die Tests laufen ohne Home Assistant (kleine Ersatzklassen in `tests/_stubs.py`) und verwenden nur ausgedachte Daten.

## Lizenz
[MIT](https://github.com/kurim/ha-BerlinGreen/blob/main/LICENSE) für den Code in diesem Repository. Namen, Texte und Bilder von Berlin Green sind von dieser Lizenz nicht erfasst.
Das Symbol ist eine eigene Zeichnung.
