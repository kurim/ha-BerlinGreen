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
- Mushrooms (planted in the app) are shown with their phase on the card and the garden sensor; they can be removed, and a new package replaces them like in the app
- A Lovelace card with a visual editor; tap a slot to plant, change or empty it. The integration serves the card itself, no resource to add

**Cloud account (optional)**
- Shows what the app shows, loads the plant library for you (`greenbox.update_catalog`), lists boxes that are not connected via Bluetooth
- **Cloud mode (per box, off by default):** the switch **Sync with cloud** makes the box's planting identical to the app. Planting changes made in Home Assistant are sent to the cloud and show up in the app, and the box shows the cloud state (refreshed every 15 minutes and after each change)
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

**Photos:** the plant drawings are downloaded to `greenbox_photos/` in your Home Assistant folder (also in the background after a restart), converted to
small PNGs with a transparent background and used as a mask, so the card can tint them in the phase colour on any theme (`show_images: true`). The
button **Update catalog and photos** on the cloud account (or `greenbox.update_catalog`) reloads everything. Photos are never part of this repository;
if one cannot be downloaded the card keeps using the original address. Catalog loading is retried automatically (up to three times) after a failed start.

## Lovelace card
```yaml
type: custom:greenbox-garden-card
entity: sensor.<box>_garden        # or use the visual editor
```
Options: `style` (`app` or `tiles`), `show_images`, `microgreens` (`auto` or `false`), `editable`, and for tiles `columns` and `microgreen_slots`.

Layout like the app: without the microgreens module 4 × 2 round pots; with it, 6 square fields on the left and 4 pots on the right (slots 1, 2, 5, 6).
If the card does not show up after an update, clear the browser cache (Ctrl+F5).

## Notifications (push to the Home Assistant app)
- **Harvest ready:** when a pot or microgreens field becomes ready, the integration fires the event `greenbox_harvest_ready` with `box`, `box_name`, `area`
  (`plants`/`microgreens`), `slot` (from 1), `plant` and `plant_id`. Pots that are already ready when Home Assistant starts are not reported again.
  Blueprint: [![Open your Home Assistant instance and show the blueprint import dialog](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fkurim%2Fha-BerlinGreen%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fgreenbox%2Fharvest_ready.yaml)
- **Water critical:** the "Water status" sensor of each box turns `low` or `empty`. Blueprint: [![Open your Home Assistant instance and show the blueprint import dialog](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fkurim%2Fha-BerlinGreen%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fgreenbox%2Fwater_low.yaml)

Both blueprints ask for your phone (Home Assistant app) and let you edit title and text. Any other automation works too, e.g. trigger on the event and call
`notify.mobile_app_<phone>`.

## Cloud mode
Switch **Sync with cloud** (on the box's device, or on the cloud-only box) makes a box follow the app: planting services (`plant_package`, `plant_slot`, `remove_package`,
`plant_microgreen`, `clear_microgreen`) are sent to your Berlin Green account, then the state is reloaded from there. Your local planting of that box stays untouched and
returns when you switch the mode off.

What the app cannot represent is refused in this mode: one package per box (no per-slot package), catalog plants and mixes only (no custom schedule or typed names), slots
can be replaced but not emptied (remove the package instead). Removing a package only closes it; microgreens stay.

The write operations are the ones the app itself uses, but they were derived from the app's code. Confirmed with one account (planting in Home Assistant shows up in the app); **not verified against every account**. If the cloud refuses a change
you get the error message and nothing local is lost. Start with one box and check the app.

## Services
Slots count from 1. `box` is optional when you have a single box (name or address otherwise).

| Service | What it does |
|---|---|
| `greenbox.plant_package` | Plant a mix (or a custom schedule with typed names) and its plants per slot |
| `greenbox.plant_slot` / `clear_slot` | Put a plant into a slot / empty it. `plant_slot` with `mix` or `germination_days`/`growth_days`/`harvest_days` (and `planted_at`) gives that slot its **own package** (other germination/growth times); local only |
| `greenbox.remove_package` | Remove the whole package |
| `greenbox.plant_microgreen` / `clear_microgreen` | Microgreen module (slots 1–6); names not in the catalog need `sprout_days` and `growth_days` |
| `greenbox.clear_mushroom` | Remove the mushroom kit from a box (in cloud mode also in the app) |
| `greenbox.import_from_cloud` | Copy the app's planting for a box into Home Assistant (also the button **Import garden from cloud** on the box; replaces its local planting) |
| `greenbox.update_catalog` | Reload the plant library and its photos from the cloud account |

Rules like in the app: a mix has one shared schedule and only allows its own plants; while the microgreens module is used, only slots 1, 2, 5 and 6 are free for plants.

## Limitations
- Tested with one Standard box, firmware 2.0.3 (start times are stored in UTC there). Firmware 4.x additionally has timezone/OTA characteristics that are not used or tested yet. Plus boxes are untested.
- Not supported: writing to the cloud, the mushroom module, the "ThreeSlot" layout, firmware updates, Wi-Fi setup.
- The box does not report its clock; the integration sends the time on every connection.
- Home Assistant and the phone app cannot use the box at the same time.

## Privacy and security
- Bluetooth control and the garden work fully locally. Local data lives in `.storage/greenbox_garden_local` and `.storage/greenbox_catalog`.
- With the cloud account the integration talks to Google (Firebase sign-in) and `backend.berlingreen.tech` (the app's GraphQL server) every 15 minutes. It only reads, unless you switch a box to cloud mode; then your planting changes are written to your own account with the same operations the app uses.
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
