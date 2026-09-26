# Changelog

Alle wichtigen Änderungen stehen hier. Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionen nach [SemVer](https://semver.org/lang/de/). / All notable changes are listed here.

## [0.7.0] - 2026-09-26

### Added
- **Pflanzenfotos lokal:** Die Fotos des Katalogs werden in `greenbox_photos/` heruntergeladen, verkleinert und als PNG mit durchsichtigem Hintergrund
  gespeichert (Strichzeichnung als Maske). Die Karte färbt sie bei `show_images: true` in der Phasenfarbe ein und ist so auf hellen und dunklen Themes
  lesbar; ohne lokales Foto bleibt die Originaladresse. / Plant photos are cached locally as small transparent PNGs the card can tint.
- Button **Katalog und Fotos aktualisieren** am Cloud-Konto (wie `greenbox.update_catalog`).

### Changed
- `greenbox.update_catalog` lädt auch die Fotos. Ein fehlgeschlagenes automatisches Laden des Katalogs wird bis zu dreimal wiederholt (bisher einmal).

## [0.6.0] - 2026-09-26

### Changed (Breaking für das Cloud-Konto / breaking for the cloud account)
- Der **API-Schlüssel der Berlin-Green-App wird nicht mehr mitgeliefert**, sondern beim Einrichten des Cloud-Kontos abgefragt. Mit
  `python tools/extract_key.py <APK/XAPK>` liest du ihn aus der App-Datei aus (siehe README). / The app's API key is no longer shipped;
  it is asked for when you add the cloud account. `tools/extract_key.py` reads it from the app file.
- **Update von 0.5.0:** Ein vorhandenes Cloud-Konto bittet einmal um den Schlüssel (Home Assistant zeigt eine Neuanmeldung). Bis dahin
  bleibt die Cloud aus; Bluetooth-Steuerung und lokale Bepflanzung laufen unverändert weiter.
- Ungültiger oder für die App beschränkter Schlüssel wird beim Einrichten am Schlüsselfeld gemeldet, nicht als „Passwort falsch“.

### Added
- `tools/extract_key.py`: liest den Schlüssel aus APK/XAPK (auch verschachtelt) und prüft ihn mit einer Anfrage an Google.
- `tools/cloud.py` und `tools/catalog.py` lesen den Schlüssel aus `GB_API_KEY` oder fragen danach.

### Notes
- Das Repository wurde neu angelegt, damit der Schlüssel auch nicht mehr in der Git-Historie steht. Die frühere Historie und die Releases 0.5.0
  und 0.6.0 des alten Repositories gibt es hier nicht mehr; dieses ist die erste Version im neuen Repository. Wer die Integration schon über
  HACS installiert hat, entfernt das alte benutzerdefinierte Repository und fügt dieses hinzu (gleiche Adresse). /
  The repository was recreated so the key is no longer in the git history either. The earlier history and the 0.5.0 and 0.6.0 releases of the old
  repository are gone; this is the first version in the new repository.

## [0.5.0] - 2026-09-26

Erste öffentliche Version. / First public release. Getestet mit einer Box (Standard, Firmware 2.0.3).

### Added
- **Bluetooth-Steuerung** je Box: Lichtmodus (Automatik/An/Aus), Lichtprofile (Wachstum, Medium, Ambient, Nachtlicht),
  Farbtemperatur (3000–6000 K), Helligkeit, Rohwerte der drei Lichtstreifen (standardmäßig deaktiviert).
- **Zeitplan**: Startzeit und Dauer (12–18 h) für Werktage und Wochenende in Ortszeit. Firmware < 4 speichert UTC; die
  Integration rechnet um und gleicht nach Sommer-/Winterzeit-Wechsel stündlich an. Uhrzeit wird bei jeder Verbindung gesendet.
- Schalter „Bei wenig Wasser blinken“, Button „Uhrzeit synchronisieren“, Sensoren für Wasserstand (Prozent und Status),
  Firmware und Hardware-Revision.
- **Garten**: Bepflanzung mit 8 Pflanz-Slots und Microgreens-Modul (6 Felder) samt Wachstumsphasen (Keimung, Wachstum, Ernte).
  Regeln wie in der App (gemeinsamer Zeitplan je Mix, mit Modul nur Slots 1, 2, 5, 6 für Pflanzen). Sensoren „Garten“
  und je Slot ein Phasen-Sensor.
- Dienste `greenbox.plant_package`, `plant_slot`, `clear_slot`, `remove_package`, `plant_microgreen`, `clear_microgreen`,
  `import_from_cloud`, `update_catalog`.
- **Lovelace-Karte** `custom:greenbox-garden-card` (runde Töpfchen, eckige Microgreens-Felder, Bedienung per Antippen, visueller
  Editor); wird von der Integration selbst bereitgestellt, es muss keine Ressource eingetragen werden.
- **Cloud-Konto (optional, nur lesend)**: zeigt den Stand der App, lädt die Pflanzenbibliothek (`greenbox.update_catalog`).
  Gespeichert wird nur das Anmelde-Token, kein Passwort.
- Ohne Katalog funktioniert die lokale Bepflanzung mit eigenem Zeitplan und frei getippten Namen; alternativ Datei
  `greenbox_catalog.json` im Home-Assistant-Ordner (siehe `tools/`).
- `docs/PROTOCOL.md` (Bluetooth-Protokoll und Cloud-Datenmodell) und `tools/` (Skripte zum Analysieren der eigenen Box).

### Notes
- Der Herstellerkatalog (Namen, Texte, Bilder) ist **nicht** Teil dieses Repositories.
- Nicht enthalten: Schreiben in die Cloud, Pilz-Modul, Boxen mit dem Layout „ThreeSlot“, Firmware-Update, WLAN-Einrichtung.
