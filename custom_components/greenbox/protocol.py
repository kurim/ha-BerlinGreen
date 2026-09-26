"""GreenBox-BLE-Protokoll (ohne Home-Assistant-Abhängigkeiten, daher offline testbar)."""
from __future__ import annotations

from dataclasses import dataclass, field

START = 0xEE
END = 0xEF

# ff05: write-without-response + notify
CHAR_CONTROL = "0000ff05-0000-1000-8000-00805f9b34fb"
# ff06: Text "blink,?,plus" (lesen; schreiben "1"/"0" = Blinken bei wenig Wasser)
CHAR_CONFIG = "0000ff06-0000-1000-8000-00805f9b34fb"

T_STRIP = {1: ord("1"), 2: ord("2"), 3: ord("3")}
T_OVERRIDE = ord("O")
T_TEMPERATURE = ord("T")
T_WATERLEVEL = ord("W")
T_FIRMWARE = ord("f")
T_HARDWARE = ord("r")
T_DURATION_WORKDAYS = ord("D")
T_DURATION_WEEKEND = ord("d")
T_SWITCH_WORKDAYS = ord("S")
T_SWITCH_WEEKEND = ord("s")

OVERRIDE_OFF, OVERRIDE_ON, OVERRIDE_AUTO = 0, 1, 3
OVERRIDE_BY_NAME = {"off": OVERRIDE_OFF, "on": OVERRIDE_ON, "auto": OVERRIDE_AUTO}
OVERRIDE_BY_VALUE = {v: k for k, v in OVERRIDE_BY_NAME.items()}

# aus app-config.json ("registry")
FIRMWARE_NAMES = {0: "3.0.0", 1: "<=2.0.0", 2: "2.0.0/2.0.1", 3: "2.0.3", 4: "4.0.0", 5: "5.x"}

TEMPERATURE_INVALID_FROM = 200  # App wertet nur < 200 aus (255 = kein Sensor)


def checksum(type_byte: int, data: bytes) -> int:
    return (256 - ((START + type_byte + sum(data) + END) % 256)) % 256


def build_frame(type_byte: int, data: bytes) -> bytes:
    return bytes([START, type_byte, *data, checksum(type_byte, data), END])


def frame_override(value: int) -> bytes:
    if value not in OVERRIDE_BY_VALUE:
        raise ValueError(f"ungültiger Override-Wert {value}")
    return build_frame(T_OVERRIDE, bytes([0, value]))


def frame_strip(strip: int, percent: int) -> bytes:
    if strip not in T_STRIP:
        raise ValueError(f"ungültiger Streifen {strip}")
    if not 0 <= percent <= 100:
        raise ValueError("Helligkeit muss 0-100 sein")
    return build_frame(T_STRIP[strip], bytes([0, percent]))


def parse_frame(raw: bytes) -> tuple[int, bytes] | None:
    """Gültigen Frame -> (type, data), sonst None."""
    if len(raw) < 4 or raw[0] != START or raw[-1] != END or sum(raw) % 256 != 0:
        return None
    return raw[1], bytes(raw[2:-2])


class FrameParser:
    """Setzt Notifications zusammen (Frames können geteilt oder gebündelt ankommen)."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> list[tuple[int, bytes]]:
        self._buf.extend(chunk)
        frames: list[tuple[int, bytes]] = []
        while True:
            # bis zum ersten Startbyte verwerfen
            while self._buf and self._buf[0] != START:
                del self._buf[0]
            try:
                end = self._buf.index(END, 1)
            except ValueError:
                # Puffer nicht unbegrenzt wachsen lassen
                if len(self._buf) > 64:
                    self._buf.clear()
                return frames
            raw = bytes(self._buf[: end + 1])
            del self._buf[: end + 1]
            parsed = parse_frame(raw)
            if parsed:
                frames.append(parsed)
            # bei ungültigem Frame: 0xEF kann auch als Datenbyte vorkommen -> weiter suchen wäre
            # unsicher; wir verwerfen den Abschnitt und synchronisieren auf das nächste 0xEE.


# --- Licht: Intensität (%) + Farbtemperatur -> drei Streifen (aus dem App-Code, setLight) -----------
TEMPERATURES = [3000, 3700, 4500, 5300, 6000]
# aktive Streifen je Farbtemperatur (warm=Streifen 1, neutral=2, kalt=3)
_WEIGHTS = {0: (1, 0, 0), 1: (1, 1, 0), 2: (1, 1, 1), 3: (0, 1, 1), 4: (0, 0, 1)}
_PATTERN_TO_TEMP = {w: i for i, w in _WEIGHTS.items()}
PRESETS = {  # aus der App: Intensität %, Index in TEMPERATURES (Fungi = Nachtlicht)
    "growth": (100, 2),
    "medium": (50, 2),
    "ambient": (33, 0),
    "nightlight": (5, 4),
}


def max_intensity(temp_idx: int) -> int:
    """Größte Intensität (%), bei der kein Streifen über 100 geht: 33 / 66 / 100 / 66 / 33."""
    return int(100 * sum(_WEIGHTS[temp_idx]) / 3 + 1e-9)


def strips_for(intensity: int, temp_idx: int) -> tuple[int, int, int]:
    """Rechenweg wie in der App: floor(gewicht * I * 300/summe(gewichte)), I = Intensität/100."""
    import math

    w = _WEIGHTS[temp_idx]
    i = min(max(intensity, 0), max_intensity(temp_idx)) / 100
    k = 300 / sum(w)
    return tuple(min(100, math.floor((wi * i) * k)) for wi in w)  # type: ignore[return-value]


def light_from_strips(strips: dict[int, int]) -> tuple[int, int | None] | None:
    """(Intensität %, Farbtemperatur-Index) aus den Streifenwerten.
    (0, None) = alles aus; None = keine Kombination der App (benutzerdefiniert)."""
    if not all(n in strips for n in (1, 2, 3)):
        return None
    vals = (strips[1], strips[2], strips[3])
    if not any(vals):
        return 0, None
    pattern = tuple(1 if v else 0 for v in vals)
    idx = _PATTERN_TO_TEMP.get(pattern)
    active = [v for v in vals if v]
    if idx is None or max(active) - min(active) > 1:
        return None
    return round(sum(vals) / 3), idx


def preset_for(strips: dict[int, int]) -> str | None:
    light = light_from_strips(strips)
    if light is None:
        return None
    for name, (pct, idx) in PRESETS.items():
        if light == (pct, idx):
            return name
    return None


def parse_config(text: str) -> tuple[bool | None, str | None]:
    """ff06 -> (Blinken bei wenig Wasser, Boxtyp). Format aus der App: Feld 0 == '1' -> Blinken,
    Feld 2 == '1' -> Plus."""
    parts = text.strip().split(",")
    blink = parts[0] == "1" if parts else None
    box = ("plus" if parts[2] == "1" else "standard") if len(parts) > 2 else None
    return blink, box


# --- Schaltzeiten -----------------------------------------------------------------------------
DURATION_RANGE = (12, 18)  # Stunden, laut App-UI
LEGACY_BELOW = 4  # Firmware-Wert < 4: Startzeit wird als UTC gespeichert (am Gerät bestätigt), >= 4: lokale Zeit


def uses_utc(firmware: int | None) -> bool | None:
    """True = Box speichert UTC (Firmware < 4), False = lokale Zeit (>= 4), None = unbekannt."""
    if firmware is None:
        return None
    return firmware < LEGACY_BELOW


def raw_from_local(hour: int, minute: int, ref, utc: bool) -> int:
    """Lokale Uhrzeit -> Rohwert HHMM. `ref` ist ein tz-aware datetime (Tag, dessen UTC-Versatz gilt,
    wie in der App: aktuelles Datum)."""
    from datetime import timezone

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("ungültige Uhrzeit")
    t = ref.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if utc:
        t = t.astimezone(timezone.utc)
    return t.hour * 100 + t.minute


def local_from_raw(raw: int, ref, utc: bool) -> tuple[int, int]:
    """Rohwert HHMM -> lokale Uhrzeit (Stunde, Minute)."""
    from datetime import timezone

    hh, mm = divmod(raw, 100)
    if utc:
        t = ref.astimezone(timezone.utc).replace(hour=hh, minute=mm, second=0, microsecond=0).astimezone(ref.tzinfo)
    else:
        t = ref.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return t.hour, t.minute


def frame_switch_time(weekend: bool, raw_hhmm: int) -> bytes:
    if not (0 <= raw_hhmm <= 2359 and raw_hhmm % 100 < 60):
        raise ValueError("ungültiger Rohwert für die Schaltzeit")
    return build_frame(T_SWITCH_WEEKEND if weekend else T_SWITCH_WORKDAYS, bytes([raw_hhmm >> 8, raw_hhmm & 0xFF]))


def frame_duration(weekend: bool, hours: int) -> bytes:
    if not DURATION_RANGE[0] <= hours <= DURATION_RANGE[1]:
        raise ValueError(f"Dauer muss {DURATION_RANGE[0]}-{DURATION_RANGE[1]} h sein")
    return build_frame(T_DURATION_WEEKEND if weekend else T_DURATION_WORKDAYS, bytes([0, hours]))


T_SET_TIME = ord("t")


def frame_set_time(unix_utc: int) -> bytes:
    return build_frame(T_SET_TIME, int(unix_utc).to_bytes(4, "big"))


def _u16(data: bytes) -> int | None:
    return data[0] * 256 + data[1] if len(data) == 2 else None


def water_status(level: int | None) -> str | None:
    """Grenzen aus der App: <=0 kritisch, <=21 niedrig."""
    if level is None:
        return None
    if level <= 0:
        return "empty"
    if level <= 21:
        return "low"
    return "ok"


@dataclass
class BoxState:
    override: int | None = None
    strips: dict[int, int] = field(default_factory=dict)
    water: int | None = None
    firmware: int | None = None
    hardware: int | None = None
    temperature: int | None = None
    switch_workdays: int | None = None
    switch_weekend: int | None = None
    duration_workdays: int | None = None
    duration_weekend: int | None = None
    blink_on_low_water: bool | None = None
    box_type: str | None = None

    def apply(self, type_byte: int, data: bytes) -> bool:
        """Übernimmt einen Frame. True, wenn sich ein Wert geändert hat."""
        value = _u16(data)
        if value is None:
            return False
        for strip, t in T_STRIP.items():
            if type_byte == t:
                return self._set_strip(strip, value)
        mapping = {
            T_OVERRIDE: "override", T_WATERLEVEL: "water", T_FIRMWARE: "firmware",
            T_HARDWARE: "hardware", T_TEMPERATURE: "temperature",
            T_SWITCH_WORKDAYS: "switch_workdays", T_SWITCH_WEEKEND: "switch_weekend",
            T_DURATION_WORKDAYS: "duration_workdays", T_DURATION_WEEKEND: "duration_weekend",
        }
        attr = mapping.get(type_byte)
        if attr is None or getattr(self, attr) == value:
            return False
        setattr(self, attr, value)
        return True

    def _set_strip(self, strip: int, value: int) -> bool:
        if self.strips.get(strip) == value:
            return False
        self.strips[strip] = value
        return True

    @property
    def firmware_name(self) -> str | None:
        return None if self.firmware is None else FIRMWARE_NAMES.get(self.firmware, f"unbekannt ({self.firmware})")

    @property
    def temperature_c(self) -> int | None:
        t = self.temperature
        return t if t is not None and t < TEMPERATURE_INVALID_FROM else None
