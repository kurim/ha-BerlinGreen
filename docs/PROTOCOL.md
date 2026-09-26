> **Unofficial notes** on the Bluetooth protocol and the cloud data model of the Berlin Green GreenBox, derived by reading the
> vendor's Android app and by testing against one box (firmware 2.0.3). Not affiliated with Berlin Green. Written in German;
> translations are welcome. Sections marked "am Gerät verifiziert" were confirmed on a real box, everything else is derived from the
> app code and may be wrong.
>
> **Quick reference (English):** service `0xFF` with characteristics `0xFF01`–`0xFF09`; control and status on `0xFF05`
> (write without response + notify), frames `[0xEE, TYPE, DATA…, CHECKSUM, 0xEF]` with a checksum that makes the sum of all bytes
> 0 mod 256; `0xFF06` holds `blink,?,plus` as ASCII; schedule start times are stored in UTC on firmware < 4.

# Berlin Green / GreenBox – BLE-Protokoll (aus App 4.0.0-alpha.2 abgeleitet)

Quelle: statische Analyse des Hermes-Bundles (React Native, react-native-ble-plx), Lesewerte inzwischen an
einer echten Box (Firmware 2.0.3) verifiziert (siehe Abschnitt "Am Gerät verifiziert"). Schreibbefehle sind
getestet für Override (0/1/3) und STRIP1 (50/100). Stellen mit "?" sind unsicher.

## Verbindungsaufbau
1. Scan ohne Service-UUID-Filter (`startDeviceScan(null, {scanMode: LowLatency})`).
2. Treffer: `device.name` oder `device.localName` beginnt mit `GreenBox`.
3. `connect` -> MTU 247 anfordern (mit Retries; der Timezone-String auf 0xFF09 braucht lange Writes)
   -> `discoverAllServicesAndCharacteristics`.
4. Danach automatisch: `syncTime`, `startConfigMonitor` (Notifications auf 0xFF05), `getBoxType`.
5. Firmware >= 4.x ("V4") nutzt zusätzlich 0xFF06 (Notify), 0xFF07 (OTA-Status), 0xFF08 (Device-Info).
   Die App prüft `_supportsNewCharacteristic` bzw. `isV4Box` (Firmware-Version).

## GATT
Service `000000ff-0000-1000-8000-00805f9b34fb`, Characteristics `0000ff01..ff09-0000-1000-8000-00805f9b34fb`.
Alle Werte werden von ble-plx als Base64 übertragen.

| Char | Richtung | Zweck |
|------|----------|-------|
| ff01 | write/read | Wi-Fi-Scan: ASCII `gimme` schreiben, dann lesen. Antwort enthält `["SSID",rssi]`-Einträge |
| ff02 | write | Wi-Fi-Zugang: ASCII `SSID,Passwort` (Komma-getrennt; Passwortlänge begrenzt, App meldet "max {{max}} Zeichen") |
| ff03 | read | Wi-Fi-Status: JSON-Array (bis zur letzten `]`) -> connected / ssid / rssi |
| ff05 | write (ohne Response) + notify | Steuerung und Statusmeldungen, Framing siehe unten |
| ff06 | read/write/notify | (neue Firmware) Box-Typ `Standard`/`Plus` und "Blink bei wenig Wasser". Lesen: Text, Komma-getrennt. Schreiben: ASCII `1`/`0` |
| ff07 | read | OTA-Status: ASCII `progress,error` |
| ff08 | read | Device-Info: ASCII `semver,serial,sku` |
| ff09 | write | Zeitzone als POSIX-TZ-String (ASCII), z. B. `CET-1CEST,M3.5.0,M10.5.0/3` |
| ff04 | ? | in der App definiert, im Code nicht verwendet gefunden |

## Licht (aus dem App-Code, `setLight`; Streifen: 1 = warm, 2 = neutral, 3 = kalt)
Die App rechnet Intensität I (0-100 %) und Farbtemperatur in die drei Streifenwerte um:
`streifen_i = floor(gewicht_i * (I/100) * 300 / summe(gewichte))`, Werte 0-100.
| Temperatur | aktive Streifen | max. Intensität |
|---|---|---|
| 3000 K | 1 | 33 % |
| 3700 K | 1+2 | 66 % |
| 4500 K | 1+2+3 | 100 % |
| 5300 K | 2+3 | 66 % |
| 6000 K | 3 | 33 % |
Profile der App: Wachstum 100 %/4500 K -> 100/100/100; Medium 50 %/4500 K -> 50/50/50;
Ambient 33 %/3000 K -> 99/0/0 (am Gerät bestätigt); Nachtlicht und Fungi 5 %/6000 K -> 0/0/15.

## Schaltzeiten (Startzeit, Dauer und UTC-Speicherung am Gerät verifiziert; SET_TIME gesendet, danach schaltete das Licht zur richtigen Zeit (die Box meldet die Uhrzeit nicht zurück))
- Werktage: `D` (Dauer, Stunden, `[0, h]`) und `S` (Startzeit, HHMM 16-bit BE); Wochenende: `d` und `s`.
  Dauer laut App-UI 12-18 h. Nach dem Schreiben ruft die App `setTimezone` (ff09, POSIX-TZ) - nur bei V4-Firmware.
- Die Startzeit hat je nach Firmware andere Semantik (`byFirmware`, Schwelle Firmware-Wert 4):
  - Firmware < 4 (`legacy`, z. B. 2.0.3; am Gerät bestätigt: Rohwert 0600/0700 = 08:00/09:00 in der App bei UTC+2): die App wandelt die lokale Zeit in **UTC** um (für das jeweils
    aktuelle Datum, deshalb Neuschreiben bei Sommer-/Winterzeitwechsel nötig).
  - Firmware >= 4 (`v4`): lokale Zeit, die Box kennt die Zeitzone (ff09).
  - Firmware unbekannt: die App schreibt nichts ("Cannot set light schedule: box firmware version not known yet").
- `SET_TIME` (`t`, uint32 BE Unix-UTC) sendet die App bei jeder Verbindung. Ein GitHub-Issue (#22) nennt, dass nach
  Stromausfall manuell neu verbunden werden muss, damit der Zeitplan wieder läuft -> Box hat vermutlich keine
  Batterie-Uhr und braucht die Zeit nach jedem Start neu.

## ff06 (Konfiguration, ASCII, kommagetrennt)
`Feld0,Feld1,Feld2`: Feld 0 == `1` -> "Bei niedrigem Wasser blinken" an; Feld 2 == `1` -> Plus-Box, sonst Standard;
Feld 1 unbekannt. Schreiben von ASCII `1`/`0` (mit Response) setzt Blinken; am Gerät verifiziert (`0,0,0` -> `1,0,0` -> `0,0,0`).

## Framing auf ff05
`[0xEE, TYPE, DATA..., CHK, 0xEF]`
- `CHK = 256 - ((0xEE + TYPE + sum(DATA) + 0xEF) mod 256)`, sodass die Summe aller Bytes inkl. Start/Ende
  = 0 mod 256 ergibt. (Randfall: Ergebnis 256 würde in Uint8 zu 0 – App behandelt das nicht extra.)
- TYPE ist ein ASCII-Zeichen.

### Schreib-Typen (App -> Box)
| Name | TYPE | DATA |
|------|------|------|
| STRIP1 / STRIP2 / STRIP3 | `1` `2` `3` (0x31-0x33) | `[0, wert]` – Helligkeit je Lichtstreifen, 0-100 (STRIP1 mit 50 und 100 verifiziert) |
| AUTOMATIC_ON_DURATION_WORKDAYS | `D` (0x44) | `[0, stunden]` |
| AUTOMATIC_ON_DURATION_WEEKEND | `d` (0x64) | `[0, stunden]` |
| AUTOMATIC_ON_SWITCH_TIME_WORKDAYS | `S` (0x53) | 16-bit BE von `hour*100 + minute` (verifiziert: 700 = 07:00) |
| AUTOMATIC_ON_SWITCH_TIME_WEEKEND | `s` (0x73) | wie oben |
| OVERRIDE_TIME_SCHEDULE | `O` (0x4F) | `[0, v]`: an = 1, aus = 0, Automatik = 3 (verifiziert: Schreiben von 0 schaltet das Licht aus, 3 stellt Automatik wieder her; Box bestätigt per Notify) |
| SET_TIME | `t` (0x74) | Unix-Zeit UTC als uint32 big-endian |
| OTA_CHANNEL | `C` (0x43) | 1 Byte, `beta` vs. stabil (Codierung ?) |
| OTA_START | `U` (0x55) | Startet das Update (Payload ?) |

### Am Gerät verifiziert (Box mit Firmware 2.0.3, Windows/bleak)
- Prüfsumme und Framing stimmen; alle Frames haben 2 Datenbytes = 16-bit big-endian.
- OVERRIDE: 0 = aus, 1 = an, 3 = Automatik (gemeldet: 3).
- STRIP1-3: 0-100 (Prozent), gemeldet 100.
- SWITCH_TIME_*: HHMM (700 = 07:00); Wochenende 0 = nicht separat gesetzt.
- ON_DURATION_*: Stunden (12). HARDWARE_REVISION: 1.
- WATERLEVEL: beobachtet 0 (Sensor ausgebaut), 20 (Tank fast leer), 50 (Tank gefüllt; App zeigt "Voll"). App-Logik: <=0 kritisch/leer, <=21 "niedrig", sonst ok. Später mit eingesetztem Sensor und vollem Tank: 100 -> vermutlich Prozentwert 0-100.
- TEMPERATURE: 255 (0x00FF). Die App wertet Temperaturen nur bei < 200 aus, 255 = "kein gültiger Wert".
- FIRMWARE_VERSION: 3 -> 2.0.3 (Wert = zweites Byte / 16-bit).
- Die Box wiederholt den Gesamtzustand fortlaufend (ca. alle 1-2 s); Änderungen nur gegen den letzten Stand auswerten.
- Beim Abonnieren von ff05 schickt die Box den kompletten Zustand von selbst.
- Alte Firmware (2.0.3): nur ff01, ff02, ff03, ff05, ff06 vorhanden; ff04/07/08/09 fehlen.
  ff06 meldet "notify", das Aktivieren ist aber nicht erlaubt (GATT-Fehler 3). ff06 lesen liefert `0,0,0`.
  ff03 lesen liefert `["d"]` (WLAN nicht verbunden; vermutlich `["c","SSID",rssi]` wenn verbunden).

### Melde-Typen (Box -> App, Notify auf ff05)
| Name | TYPE | DATA |
|------|------|------|
| TEMPERATURE | `T` (0x54) | 16-bit BE (255 = vermutlich kein Sensor) |
| WATERLEVEL | `W` (0x57) | 16-bit BE, 0-100 (beobachtet 0/20/50/100) |
| FIRMWARE_VERSION | `f` (0x66) | 16-bit BE, Wert -> `registry` |
| HARDWARE_REVISION | `r` (0x72) | 16-bit BE |
| STRIP1-3, D/d/S/s, O | wie oben | Rückmeldung des aktuellen Werts (16-bit BE bei Zeit/Dauer) |

## Firmware-Update
- Die App lädt keine Firmware herunter. Sie setzt `OTA_CHANNEL` und `OTA_START` per BLE; die Box holt die
  Firmware selbst über das zuvor eingerichtete WLAN. Fortschritt über ff07 lesen (`progress,error`).
- Die Firmware-URL steht nicht in der App. Die Box hat sie eingebrannt.
- Die App ruft `https://app.berlingreen.com/app-config.json` ab (Konstante `OTA_CONFIG_URL`, Funktion
  `fetchOtaConfig`). Inhalt (vom Nutzer bereitgestellt): `registry` bildet das Firmware-Byte (Typ `f` auf ff05)
  auf Versionen ab (1 = <=2.0.0, 2 = 2.0.0/2.0.1, 3 = 2.0.3, 4 = 4.0.0, 0 = 3.0.0, 5 reserviert).
  `channels` nennt pro Kanal (stable/beta) und Boxgröße (small/big) die neueste Version
  (stable 2.0.3, beta 4.0.0). `offers` bietet Byte 3 -> 4.0.0 im Beta-Kanal an, nur für eingeschriebene Nutzer
  (`enrolledOnly`). Die Datei enthält keine Download-URLs; der Download läuft über die Box selbst.
- Update-Erkennung in HA: Firmware-Byte lesen, über `registry` in Klartext umsetzen, mit `channels` vergleichen.

## Hersteller-Repository
`github.com/BerlinGreen/BerlinGreen` enthält nur Logo und README (Firmware/App nicht Open Source, laut README in Arbeit).
Issue #22 (Juli 2026) bittet um dokumentiertes BLE-Protokoll/lokale API für Home Assistant, keine Antwort der Betreiber sichtbar.
Issue #20 betrifft Sicherheit von BLE-Pairing und Datenübertragung.

## Cloud-Datenmodell (Hasura-GraphQL, aus den App-Abfragen; mit eigenem Konto gelesen)
- Anmeldung: Firebase Auth (`identitytoolkit`, Projekt `bg-box`, Schlüssel aus `res/values/strings.xml`), danach
  `Authorization: Bearer <ID-Token>`. Das Token muss den Claim `https://hasura.io/jwt/claims` enthalten (wird kurz nach
  Kontoerstellung serverseitig gesetzt; die App wartet darauf und erneuert das Token).
- `box`: `id`, `box_id` (bei Android-Registrierung die BLE-MAC, bei iOS eine UUID), `name`, `type`, `config`, `light_*`.
- `packages` (Mix-Pakete): `planted_at`, `layout` (`EightSlot`, Slots 0-7), `mix.growth_speed = [Keimung, Wachstum,
  Erntefenster]` in Tagen, `planted[slot -> plant]`. Eigene Pflanzen: `plant.user_provided_name`, `mix.name = null`.
- `microgreen_configs`: `planted_microgreens[slot, plantedOnDay, microgreen{sproutTimeDays, growthTimeDays}]` - eigenes
  Microgreen-Modul (Slots 0-5), läuft unabhängig neben dem Mix-Paket (an echten Daten bestätigt: Paket auf Slots 0/1/4/5
  und 6 Microgreens gleichzeitig). Ein Mix-Paket hat einen gemeinsamen Zeitplan (`growth_speed`) für alle Pflanzen, Beispiel
  in der App: Keimung 15 / Wachstum 20 / Ernte 15 Tage.
  `mushroom_config`: `planted_mushrooms[plantedOnDay, pinning/growth/harvestTimeDays]`.
- Phase (App-Logik `getCurrentPhaseIndex`/`isGrowthCycleComplete`): Tage seit `planted_at`; < d0 Keimung, < d0+d1
  Wachstum, danach Ernte, > d0+d1+d2 abgeschlossen.
- Schreibende Mutationen der App (nicht implementiert): `insert_package`, `update_package` (removed_at),
  `InsertSlot`/`UpdateSlot`, `AddPlantedMicrogreen`, `DeletePlantedMicrogreen`, `SetBoxLight`, `SetBoxConfig`.

## Pflanzenbibliothek (mit `tools/catalog.py` aus der Cloud exportiert)
- 13 Mixe (`id`, `name{de,en}`, `growth_speed=[Keimung,Wachstum,Erntefenster]`, `containedPlants[plant.id]`, `shop_link`,
  `containsCannabis`, `is_experimental`), 83 Pflanzen (`name`, `photo` auf cdn.shopify.com, `encyclopaedia[text, tip]`),
  6 Microgreens (alle Keimung 2 / Ernte 8 Tage), 5 Pilze (`pinningTimeDays`, `growthTimeDays`, `harvestTimeDays`),
  13 Platzhalterbilder für eigene Pflanzen, dazu die eigenen Pflanzen des Kontos (`user_provided_name`, `is_experimental`).
- Der Zeitplan hängt am **Mix**, nicht an der Pflanze (`plant.growth_speed` ist praktisch immer leer). Eigene Pflanzen leben in
  einem `is_experimental`-Mix mit `[20, 20, 20]`. Beispiel: "Asiatische Kräuter" = 15/20/15, "Asiatisches Blattgemüse" = 5/16/20.
- `encyclopedia` (Microgreens/Pilze) ist eine Liste mit einem Eintrag; der Mix "Cannabis Samen" ist `containsCannabis`
  (die App fragt vorher das Alter ab).

## Cloud (nur zur Info, für lokale Steuerung nicht nötig)
- GraphQL (Hasura): `backend.berlingreen.tech/v1alpha1/graphql` (prod), `dev.backend.berlingreen.tech/v1/graphql`
- Firebase Auth (identitytoolkit) + Cloud Functions `https://us-central1-bg-box.cloudfunctions.net/`
- Shopify: `berlingreen.myshopify.com` (Storefront `/api/2022-01/graphql.json`)
- Tree-Nation: `https://tree-nation.com/api/`; Stamped: `https://stamped.io/api/widget/...`
- Statische Seiten: `berlingreen.com/pages/app-password-reset`, `.../app-email-verified`, `.../checkout-complete`
