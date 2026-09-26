"""Verbindung zur GreenBox: hält eine BLE-Verbindung, dekodiert ff05-Notifications, schreibt Befehle."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .protocol import (
    CHAR_CONFIG,
    CHAR_CONTROL,
    BoxState,
    FrameParser,
    DURATION_RANGE,
    frame_duration,
    frame_set_time,
    frame_strip,
    frame_switch_time,
    light_from_strips,
    local_from_raw,
    parse_config,
    raw_from_local,
    strips_for,
    uses_utc,
)

_LOGGER = logging.getLogger(__name__)

RECONNECT_MIN = 5
RECONNECT_MAX = 300
# Uhrzeit bei jeder Verbindung senden wie die App (SET_TIME). Am Gerät geprüft: nach dem Senden schaltete das
# Licht zur eingestellten Zeit. Die Box meldet die Uhrzeit nicht zurück, ein Zeitfehler würde sich nur als
# verschobene Schaltzeit zeigen -> dann auf False stellen. Die Button-Entität funktioniert unabhängig davon.
AUTO_SYNC_TIME = True
MAINTAIN_FIRST_DELAY = 5  # s: nach dem Verbinden kurz warten, bis die Box den Zustand geschickt hat
MAINTAIN_INTERVAL = 3600  # s: Schaltzeiten prüfen (Sommer-/Winterzeit-Wechsel)


class GreenBoxDevice:
    def __init__(self, hass: HomeAssistant, address: str, name: str) -> None:
        self.hass = hass
        self.address = address
        self.name = name
        self.state = BoxState()
        self._client: BleakClient | None = None
        self._task: asyncio.Task | None = None
        self._disconnected = asyncio.Event()
        self._write_lock = asyncio.Lock()
        self._callbacks: list[Callable[[], None]] = []
        self._parser = FrameParser()
        self.intent: dict[str, tuple[int, int, int]] = {}  # gewünschte Ortszeit je 'workdays'/'weekend'
        self._store = Store(hass, 1, f"greenbox_{address.replace(':', '').lower()}")
        self._synced = False
        self.temp_idx = 2  # zuletzt bekannte Farbtemperatur (Index in TEMPERATURES), Standard 4500 K

    # --- Zustand -----------------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

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
        data = await self._store.async_load() or {}
        self.intent = {k: tuple(v) for k, v in data.get("intent", {}).items() if k in ("workdays", "weekend")}
        self._task = self.hass.async_create_background_task(self._run(), f"greenbox {self.address}")

    async def async_stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._drop_client()

    async def _drop_client(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.disconnect()
            except (BleakError, TimeoutError):
                pass
        self._notify_listeners()

    async def _run(self) -> None:
        delay = RECONNECT_MIN
        while True:
            try:
                ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
                if ble_device is None:
                    _LOGGER.debug("%s: nicht in Reichweite, warte", self.address)
                else:
                    await self._connect_and_wait(ble_device)
                    delay = RECONNECT_MIN  # Verbindung stand -> Backoff zurücksetzen
            except asyncio.CancelledError:
                raise
            except (BleakError, TimeoutError, OSError) as err:
                _LOGGER.debug("%s: Verbindungsfehler: %s", self.address, err)
            except Exception:  # noqa: BLE001 - Schleife darf nie sterben
                _LOGGER.exception("%s: unerwarteter Fehler", self.address)
            await self._drop_client()
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX)

    async def _connect_and_wait(self, ble_device) -> None:
        self._disconnected.clear()
        self._parser = FrameParser()
        client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            self.name,
            disconnected_callback=lambda _c: self.hass.loop.call_soon_threadsafe(self._disconnected.set),
            max_attempts=6,  # schwaches Signal (~ -85 dBm) -> mehr Versuche
            ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            or ble_device,
        )
        self._client = client
        await client.start_notify(CHAR_CONTROL, self._on_notify)
        await self._read_config()
        _LOGGER.info("%s: verbunden", self.address)
        self._notify_listeners()
        self._synced = False
        timeout = MAINTAIN_FIRST_DELAY
        while True:
            try:
                await asyncio.wait_for(self._disconnected.wait(), timeout)
                break
            except TimeoutError:
                await self._maintain()
                timeout = MAINTAIN_INTERVAL
        _LOGGER.info("%s: Verbindung getrennt", self.address)

    # --- Daten -------------------------------------------------------------------
    async def _read_config(self) -> None:
        """ff06 lesen (Blinken bei wenig Wasser, Boxtyp). Notify ist auf dieser Firmware nicht erlaubt."""
        try:
            raw = bytes(await self._client.read_gatt_char(CHAR_CONFIG))
            self.state.blink_on_low_water, self.state.box_type = parse_config(raw.decode("utf-8", "replace"))
        except (BleakError, TimeoutError) as err:
            _LOGGER.debug("%s: ff06 nicht lesbar: %s", self.address, err)

    def _on_notify(self, _char, data: bytearray) -> None:
        changed = False
        for type_byte, payload in self._parser.feed(bytes(data)):
            changed |= self.state.apply(type_byte, payload)
        if changed:
            light = light_from_strips(self.state.strips)
            if light and light[1] is not None:
                self.temp_idx = light[1]
            self.hass.loop.call_soon_threadsafe(self._notify_listeners)

    async def async_write(self, frame: bytes) -> None:
        if not self.connected:
            raise HomeAssistantError("GreenBox ist nicht verbunden")
        async with self._write_lock:
            try:
                await self._client.write_gatt_char(CHAR_CONTROL, frame, response=False)
            except (BleakError, TimeoutError) as err:
                raise HomeAssistantError(f"Schreiben an GreenBox fehlgeschlagen: {err}") from err

    async def async_set_light(self, intensity: int, temp_idx: int) -> None:
        """Intensität (%) + Farbtemperatur wie die App auf die drei Streifen verteilen."""
        values = strips_for(intensity, temp_idx)
        for strip, value in enumerate(values, start=1):
            await self.async_write(frame_strip(strip, value))
            self.state.strips[strip] = value  # optimistisch; die Box bestätigt per Notify
            await asyncio.sleep(0.1)
        self.temp_idx = temp_idx
        self._notify_listeners()

    async def async_set_blink(self, enabled: bool) -> None:
        """'Bei niedrigem Wasser blinken': ASCII '1'/'0' nach ff06 (mit Response), danach zurücklesen."""
        if not self.connected:
            raise HomeAssistantError("GreenBox ist nicht verbunden")
        async with self._write_lock:
            try:
                await self._client.write_gatt_char(CHAR_CONFIG, b"1" if enabled else b"0", response=True)
            except (BleakError, TimeoutError) as err:
                raise HomeAssistantError(f"Schreiben an GreenBox fehlgeschlagen: {err}") from err
            await self._read_config()
        self._notify_listeners()

    # --- Schaltzeiten --------------------------------------------------------------------
    def _raw(self, kind: str) -> tuple[int | None, int | None]:
        st = self.state
        return (st.switch_workdays, st.duration_workdays) if kind == "workdays" else (st.switch_weekend, st.duration_weekend)

    def schedule_view(self, kind: str) -> tuple[int, int, int] | None:
        """(Stunde, Minute, Dauer h) in Ortszeit: gewünschter Wert, sonst aus den Rohwerten der Box."""
        if kind in self.intent:
            return self.intent[kind]
        raw, hours = self._raw(kind)
        utc = uses_utc(self.state.firmware)
        if raw is None or hours is None or utc is None:
            return None
        if not DURATION_RANGE[0] <= hours <= DURATION_RANGE[1]:
            return None  # z. B. Wochenende 0/0 = nicht separat gesetzt
        hh, mm = local_from_raw(raw, dt_util.now(), utc)
        return hh, mm, hours

    async def async_set_schedule(self, kind: str, hour: int | None = None, minute: int | None = None, hours: int | None = None) -> None:
        utc = uses_utc(self.state.firmware)
        if utc is None:
            raise HomeAssistantError("Firmware der Box noch unbekannt - Schaltzeit wird nicht geschrieben")
        base = self.schedule_view(kind) or self.schedule_view("workdays") or (8, 0, DURATION_RANGE[0])
        new = (base[0] if hour is None else hour, base[1] if minute is None else minute, base[2] if hours is None else hours)
        raw_from_local(new[0], new[1], dt_util.now(), utc)  # prüft die Uhrzeit
        frame_duration(kind == "weekend", new[2])  # prüft die Dauer
        self.intent[kind] = new
        await self._store.async_save({"intent": {k: list(v) for k, v in self.intent.items()}})
        await self._write_schedule(kind)
        self._notify_listeners()

    async def _write_schedule(self, kind: str) -> None:
        hh, mm, hours = self.intent[kind]
        utc = uses_utc(self.state.firmware)
        raw = raw_from_local(hh, mm, dt_util.now(), bool(utc))
        weekend = kind == "weekend"
        await self.async_write(frame_switch_time(weekend, raw))
        await asyncio.sleep(0.3)
        await self.async_write(frame_duration(weekend, hours))
        # optimistisch; die Box bestätigt per Notify
        if weekend:
            self.state.switch_weekend, self.state.duration_weekend = raw, hours
        else:
            self.state.switch_workdays, self.state.duration_workdays = raw, hours

    async def _maintain(self) -> None:
        """Nach dem Verbinden und stündlich: Zeit senden (optional) und Schaltzeiten an die Ortszeit angleichen
        (Firmware < 4 speichert UTC -> nach Sommer-/Winterzeit-Wechsel neu schreiben)."""
        try:
            if AUTO_SYNC_TIME and not self._synced:
                await self.async_sync_time()
            utc = uses_utc(self.state.firmware)
            if utc is None:
                return
            for kind, (hh, mm, hours) in list(self.intent.items()):
                raw, cur_hours = self._raw(kind)
                if raw is None or cur_hours is None:
                    continue  # Zustand noch nicht empfangen
                want = raw_from_local(hh, mm, dt_util.now(), utc)
                if raw != want or cur_hours != hours:
                    _LOGGER.info("%s: Schaltzeit %s angleichen (Box %s/%s h -> %s/%s h)", self.address, kind, raw, cur_hours, want, hours)
                    await self._write_schedule(kind)
        except HomeAssistantError as err:
            _LOGGER.debug("%s: Wartung übersprungen: %s", self.address, err)

    async def async_sync_time(self) -> None:
        """SET_TIME: aktuelle Unix-Zeit (UTC), wie die App bei jeder Verbindung."""
        await self.async_write(frame_set_time(int(dt_util.utcnow().timestamp())))
        self._synced = True
