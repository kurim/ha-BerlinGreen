# Berlin Green GreenBox for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Validate](https://github.com/kurim/ha-BerlinGreen/actions/workflows/validate.yml/badge.svg)](https://github.com/kurim/ha-BerlinGreen/actions/workflows/validate.yml)
[![Tests](https://github.com/kurim/ha-BerlinGreen/actions/workflows/tests.yml/badge.svg)](https://github.com/kurim/ha-BerlinGreen/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/kurim/ha-BerlinGreen/blob/main/LICENSE)

Control your [Berlin Green](https://berlingreen.com) GreenBox from Home Assistant over Bluetooth and keep track of what is
growing in it, including a Lovelace card that looks like the app. Deutsche Version: [README.de.md](https://github.com/kurim/ha-BerlinGreen/blob/main/README.de.md).

> **Unofficial.** This project is not affiliated with, endorsed by or supported by Berlin Green. "Berlin Green" and "GreenBox" are
> their names. It was built by reading the vendor's Android app and testing against a single box, so expect rough edges (see
> [Limitations](#limitations)). The optional cloud features use the same endpoints as the app and may stop working at any time.
> Use at your own risk.

## Features

**Control (Bluetooth, per box)**
- Light mode (automatic / on / off), light profiles (growth, medium, ambient, night light), colour temperature, brightness
- Schedule: start time and duration (12–18 h) for weekdays and weekend, in local time; the box clock is synchronised on every connection
- Water level (percent and status), "blink on low water" switch, firmware and hardware revision

**Garden (local, cloud optional)**
- Plants with growth phases (germination → growth → harvest) per slot: 8 round pots, or 4 pots plus the 6-field microgreens module, exactly like the app
- Everything is stored in Home Assistant; nothing is sent to Berlin Green
- One sensor per box and one phase sensor per slot, for automations such as "harvest is ready"
- A Lovelace card with a visual editor; tap a slot to plant, change or empty it. The integration serves the card itself, no resource to add

**Cloud account (optional, read-only)**
- Shows what the app shows, loads the plant library for you (`greenbox.update_catalog`), lists boxes that are not connected via Bluetooth
- Only the sign-in token is stored, never your password. Google/Apple sign-in is not supported

## Requirements
- Home Assistant 2025.1 or newer with a Bluetooth adapter (or an ESP32 Bluetooth proxy) that can reach the box
- A GreenBox. Developed and tested with one Standard box on firmware 2.0.3

## Installation

### HACS (custom repository)
1. HACS → ⋮ → **Custom repositories** → add `https://github.com/kurim/ha-BerlinGreen`, type **Integration**.
2. Install **Berlin Green GreenBox (unofficial)** and restart Home Assistant.

### Manual
Copy `custom_components/greenbox` to `<config>/custom_components/greenbox` and restart Home Assistant.

## Setup
Settings → Devices & services → **Add integration** → *Berlin Green GreenBox*:
- **Bluetooth box**: found automatically (name `GreenBox…`). One entry per box. **Close the phone app first**: the box most likely accepts only one Bluetooth connection.
- **Cloud account (optional)**: your Berlin Green app login **plus the app's API key** (see below). Add it once; it is shared by all boxes. Remove the entry to disconnect.

If the box is far away (around −85 dBm) connections will be slow or drop. Place the adapter or proxy near the box.

### The app's API key (cloud account only)
The cloud account signs in through Google Firebase like the app does, which needs the app's public API key. It is **not** shipped with this
integration (out of consideration for the vendor), you enter it once when adding the cloud account. It is stored in plain text in the app file, so it is easy to read:
```bash
python tools/extract_key.py GreenBoxApp.xapk     # or an .apk
```
Get the app file from your phone (`adb shell pm path com.berlingreen.android`, then `adb pull <path>`) or from an APK provider of your choice.
The script only reads the file, finds the key (starts with `AIza`, 39 characters) and checks it with a single request to Google. Without the cloud account nothing here is needed.

## The plant catalog
The catalog (mixes with their schedules, plants, microgreens) belongs to Berlin Green and is **not** part of this repository. It is loaded
for you when you connect the cloud account (or run `greenbox.update_catalog`) and stored in Home Assistant. Without it you can still plant with a
**custom schedule** and free-typed plant names. You can also put a `greenbox_catalog.json` next to `configuration.yaml`; see [`tools/`](https://github.com/kurim/ha-BerlinGreen/blob/main/tools/README.md).

## Lovelace card
```yaml
type: custom:greenbox-garden-card
entity: sensor.<box>_garden        # or use the visual editor
```
Options: `style` (`app` or `tiles`), `show_images`, `microgreens` (`auto` or `false`), `editable`, and for tiles `columns` and `microgreen_slots`.

Layout like the app: without the microgreens module 4 × 2 round pots; with it, 6 square fields on the left and 4 pots on the right (slots 1, 2, 5, 6).
If the card does not show up after an update, clear the browser cache (Ctrl+F5).

## Services
Slots count from 1. `box` is optional when you have a single box (name or address otherwise).

| Service | What it does |
|---|---|
| `greenbox.plant_package` | Plant a mix (or a custom schedule with typed names) and its plants per slot |
| `greenbox.plant_slot` / `clear_slot` | Put a plant into a slot / empty it |
| `greenbox.remove_package` | Remove the whole package |
| `greenbox.plant_microgreen` / `clear_microgreen` | Microgreen module (slots 1–6); names not in the catalog need `sprout_days` and `growth_days` |
| `greenbox.import_from_cloud` | Copy the app's planting for a box into Home Assistant |
| `greenbox.update_catalog` | Reload the plant library from the cloud account |

Rules like in the app: a mix has one shared schedule and only allows its own plants; while the microgreens module is used, only slots 1, 2, 5 and 6 are free for plants.

## Limitations
- Tested with one Standard box, firmware 2.0.3 (start times are stored in UTC there). Firmware 4.x additionally has timezone/OTA characteristics that are not used or tested yet. Plus boxes are untested.
- Not supported: writing to the cloud, the mushroom module, the "ThreeSlot" layout, firmware updates, Wi-Fi setup.
- The box does not report its clock; the integration sends the time on every connection.
- Home Assistant and the phone app cannot use the box at the same time.

## Privacy and security
- Bluetooth control and the garden work fully locally. Local data lives in `.storage/greenbox_garden_local` and `.storage/greenbox_catalog`.
- With the cloud account the integration talks to Google (Firebase sign-in) and `backend.berlingreen.tech` (the app's GraphQL server), read-only, every 15 minutes.
- The app's Firebase API key is not part of this repository; you enter it yourself (see above). It is stored in Home Assistant's config entry.
- Please never post passwords, tokens or exports of your account in issues.

## Documentation
- [`docs/PROTOCOL.md`](https://github.com/kurim/ha-BerlinGreen/blob/main/docs/PROTOCOL.md) – Bluetooth protocol and cloud data model (German, with an English quick reference)
- [`tools/`](https://github.com/kurim/ha-BerlinGreen/blob/main/tools/README.md) – scripts to scan, read and control your own box and to export the plant library

## Development
```bash
pip install voluptuous pyyaml
python tests/test_metadata.py && python tests/test_logic.py && python tests/test_hub.py && python tests/test_flow.py
python tests/make_card_fixtures.py && cd tests/card && npm ci && npm test
```
The tests run without Home Assistant (small stand-ins are in `tests/_stubs.py`) and use invented data only.

## License
[MIT](https://github.com/kurim/ha-BerlinGreen/blob/main/LICENSE) for the code in this repository. Berlin Green names, texts and images are not covered by this license.
The icon is an original drawing.
