# Changelog

Alle wichtigen Änderungen stehen hier. Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionen nach [SemVer](https://semver.org/lang/de/). / All notable changes are listed here.

## [0.10.0] - 2026-09-26

### Added
- **Cloud-Modus je Box** (Schalter „Mit Cloud synchronisieren“, standardmäßig aus): Pflanz-Dienste gehen an die Cloud, die App zeigt dasselbe, die Box zeigt den Stand der Cloud.
  Es gelten die Regeln der App (ein Paket je Box, nur Katalog-Pflanzen, Slots nur ersetzen). Die Operationen stammen aus dem Code der App und sind nicht bei jedem Konto
  geprüft. Lokaler Stand bleibt beim Ein- und Ausschalten erhalten. / Optional per-box cloud mode: planting changes are written to the Berlin Green account.

## [0.9.0] - 2026-09-26

### Added
- **Eigenes Paket je Slot (nur lokal):** Im Slot-Dialog der Karte gibt es die Auswahl „Paket für diesen Slot“: Paket der Box, ein anderer Mix oder ein eigener
  Zeitplan (mit Pflanzdatum). So können Pflanzen mit anderer Keimung/Wachstumsdauer in derselben Box stehen. Dienst `greenbox.plant_slot` bekommt dafür
  `mix`, `germination_days`, `growth_days`, `harvest_days` und `planted_at`. Bei Cloud-Ständen ist die Auswahl aus (Hinweis: erst übernehmen);
  weitere Pakete der Cloud werden beim Übernehmen zu Slot-Paketen. / A slot can get its own package (local only; disabled for cloud state).
- **Benachrichtigungen:** Ereignis `greenbox_harvest_ready` und zwei Blueprints (`blueprints/automation/greenbox/`): Erntereif und Wasser kritisch, jeweils
  als Push an die Home-Assistant-App. / Event and blueprints for harvest-ready and water-critical push notifications.

## [0.8.0] - 2026-09-26

### Added
- Button **Garten aus der Cloud übernehmen** an jeder Bluetooth-Box (wie `greenbox.import_from_cloud`, aber optional per Knopfdruck). Er ersetzt die
  lokale Bepflanzung dieser Box durch den Stand aus der App und ist nur wählbar, wenn das Cloud-Konto die Box kennt. / Optional button on each
  Bluetooth box that copies the app's planting into Home Assistant.

## [0.7.1] - 2026-09-26

### Fixed
- **Die Karte wird automatisch eingebunden:** Die Integration trägt `greenbox-garden-card.js` selbst bei den Dashboard-Ressourcen ein
  (`/greenbox_static/greenbox-garden-card.js?v=<Version>`, wie HACS es für Karten tut) und aktualisiert die Adresse bei neuer Version. Bei Dashboards im
  YAML-Modus wird sie stattdessen auf jeder Seite geladen. / The card is added to the dashboard resources automatically.
- **Fotos wurden abgeschnitten geladen** und daher fast alle verworfen (die Antwort wurde nur zum Teil gelesen). Sie werden jetzt vollständig geladen;
  der erste Fehler steht im Log als Warnung.

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
