"""Verbindung zur GreenBox über die eigene Firmware-MQTT-Schnittstelle (Alternative zu Bluetooth, siehe device.py).

Nutzt die MQTT-Integration von Home Assistant (Broker-Zugang liegt dort); diese Integration braucht dafür keine
eigenen Broker-Zugangsdaten. Protokoll/Topics siehe BerlinGreen-FW/firmware/README.md ("MQTT"):
  <base>/state          JSON (retained), bei Änderung + alle 60 s
  <base>/availability   online|offline (retained, LWT)
  <base>/set/<key>      Broker -> Box
Bietet dieselbe öffentliche Schnittstelle wie GreenBoxDevice (device.py), damit alle Plattformen (sensor.py,
number.py, select.py, ...) unverändert bleiben; async_write() nimmt dieselben BLE-Frames entgegen und übersetzt
sie über protocol.decode_frame_to_set() in ein MQTT-set-Topic."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .protocol import (
    DURATION_RANGE,
    BoxState,
    OVERRIDE_BY_NAME,
    decode_frame_to_set,
    frame_duration,
    light_from_strips,
    local_from_raw,
    raw_from_local,
    strips_for,
    uses_utc,
)

_LOGGER = logging.getLogger(__name__)

# Die "Ortszeit"-Logik (Zeitzone/Sommerzeit nachziehen) lässt die Firmware selbst erledigen; anders als die
# Original-Box (nur RAM) speichert diese Firmware den Zeitplan im NVS, eine periodische Wartung wie bei der
# Bluetooth-Box (device.py: _maintain) ist hier daher nicht nötig.


def _parse_hhmm(text: str) -> int | None:
    try:
        hh, mm = text.split(":", 1)
        return int(hh) * 100 + int(mm)
    except (ValueError, AttributeError):
        return None


class GreenBoxMqttDevice:
    """Hält den letzten über MQTT gemeldeten Zustand einer Box; `address` ist hier kein Bluetooth-MAC."""

    uses_bluetooth = False  # entity.py: keine "connections" vom Typ bluetooth für dieses Gerät

    def __init__(self, hass: HomeAssistant, base: str, name: str) -> None:
        self.hass = hass
        self.base = base
        self.address = f"mqtt_{base}"
        self.name = name
        self.state = BoxState()
        self.intent: dict[str, tuple[int, int, int]] = {}
        self.temp_idx = 2
        self.ble_address: str | None = None  # vom Gerät gemeldet; Kennung für Garten/Cloud
        self.on_ble_address: Callable[[str], None] | None = None
        self._available = False
        self._callbacks: list[Callable[[], None]] = []
        self._unsub_state: Callable[[], None] | None = None
        self._unsub_avail: Callable[[], None] | None = None

    @property
    def connected(self) -> bool:
        return self._available

    @callback
    def register_callback(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._callbacks.append(cb)

        def _remove() -> None:
            self._callbacks.remove(cb)

        return _remove

    @callback
    def _notify_listeners(self) -> None:
        for cb in list(self._callbacks):
            cb()

    # --- Lebenszyklus --------------------------------------------------------------
    async def async_start(self) -> None:
        self._unsub_state = await mqtt.async_subscribe(self.hass, f"{self.base}/state", self._on_state)
        self._unsub_avail = await mqtt.async_subscribe(self.hass, f"{self.base}/availability", self._on_availability)

    async def async_stop(self) -> None:
        if self._unsub_state:
            self._unsub_state()
        if self._unsub_avail:
            self._unsub_avail()

    # --- Eingehend -----------------------------------------------------------------
    @callback
    def _on_availability(self, msg) -> None:
        self._available = msg.payload == "online"
        self._notify_listeners()

    @callback
    def _on_state(self, msg) -> None:
        try:
            data = json.loads(msg.payload)
        except ValueError:
            _LOGGER.warning("%s: ungültiges state-JSON", self.base)
            return
        st = self.state
        st.override = OVERRIDE_BY_NAME.get(data.get("override"))
        st.strips = {1: data.get("stripe1"), 2: data.get("stripe2"), 3: data.get("stripe3")}
        st.water = data.get("water")
        st.firmware = data.get("fw_byte")
        st.firmware_version = data.get("fw")
        ble = str(data.get("ble") or "").upper()
        if ble and ble != self.ble_address:
            self.ble_address = ble
            if self.on_ble_address:
                self.on_ble_address(ble)
        start = _parse_hhmm(data.get("start", ""))
        if start is not None:
            st.switch_workdays = start
        start_we = _parse_hhmm(data.get("start_weekend", ""))
        if start_we is not None:
            st.switch_weekend = start_we
        st.duration_workdays = data.get("duration")
        st.duration_weekend = data.get("duration_weekend")
        st.blink_on_low_water = data.get("blink_on_low_water")
        light = light_from_strips(st.strips)
        if light and light[1] is not None:
            self.temp_idx = light[1]
        self._available = True  # eine state-Nachricht gilt bereits als "online" (availability kann nachkommen)
        self._notify_listeners()

    # --- Ausgehend -----------------------------------------------------------------
    async def _publish_set(self, key: str, value: str) -> None:
        if not self.connected:
            raise HomeAssistantError("GreenBox ist nicht erreichbar (MQTT)")
        await mqtt.async_publish(self.hass, f"{self.base}/set/{key}", value)

    async def async_write(self, frame: bytes) -> None:
        """Dieselben BLE-Frames wie device.py entgegennehmen (number.py/select.py bauen sie direkt) und als
        MQTT-set-Topic weiterreichen."""
        decoded = decode_frame_to_set(frame)
        if decoded is None:
            _LOGGER.warning("%s: Frame ohne MQTT-Entsprechung verworfen", self.base)
            return
        key, value = decoded
        await self._publish_set(key, value)

    async def async_set_light(self, intensity: int, temp_idx: int) -> None:
        values = strips_for(intensity, temp_idx)
        for strip, value in enumerate(values, start=1):
            await self._publish_set(f"stripe{strip}", str(value))
            self.state.strips[strip] = value  # optimistisch; der nächste state-Retain bestätigt
        self.temp_idx = temp_idx
        self._notify_listeners()

    async def async_set_blink(self, enabled: bool) -> None:
        await self._publish_set("blink", "1" if enabled else "0")
        self.state.blink_on_low_water = enabled  # optimistisch
        self._notify_listeners()

    # --- Schaltzeiten (siehe device.py: dieselbe Semantik, "start*" ist die Zeitbasis der Box) -------------
    def _raw(self, kind: str) -> tuple[int | None, int | None]:
        st = self.state
        return (st.switch_workdays, st.duration_workdays) if kind == "workdays" else (st.switch_weekend, st.duration_weekend)

    def schedule_view(self, kind: str) -> tuple[int, int, int] | None:
        if kind in self.intent:
            return self.intent[kind]
        raw, hours = self._raw(kind)
        utc = uses_utc(self.state.firmware)
        if raw is None or hours is None or utc is None:
            return None
        if not DURATION_RANGE[0] <= hours <= DURATION_RANGE[1]:
            return None
        hh, mm = local_from_raw(raw, dt_util.now(), utc)
        return hh, mm, hours

    async def async_set_schedule(self, kind: str, hour: int | None = None, minute: int | None = None, hours: int | None = None) -> None:
        utc = uses_utc(self.state.firmware)
        if utc is None:
            raise HomeAssistantError("Firmware der Box noch unbekannt - Schaltzeit wird nicht geschrieben")
        base = self.schedule_view(kind) or self.schedule_view("workdays") or (8, 0, DURATION_RANGE[0])
        new = (base[0] if hour is None else hour, base[1] if minute is None else minute, base[2] if hours is None else hours)
        raw = raw_from_local(new[0], new[1], dt_util.now(), utc)  # prüft die Uhrzeit
        frame_duration(kind == "weekend", new[2])  # prüft nur die Dauer (Frame wird nicht benutzt)
        self.intent[kind] = new
        key_prefix = "_weekend" if kind == "weekend" else ""
        await self._publish_set(f"start{key_prefix}", str(raw))
        await self._publish_set(f"duration{key_prefix}", str(new[2]))
        if kind == "weekend":
            self.state.switch_weekend, self.state.duration_weekend = raw, new[2]
        else:
            self.state.switch_workdays, self.state.duration_workdays = raw, new[2]
        self._notify_listeners()

    async def async_sync_time(self) -> None:
        await self._publish_set("time", str(int(dt_util.utcnow().timestamp())))
