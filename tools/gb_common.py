"""Gemeinsame Helfer für GreenBox-BLE-Analyse (nur lesend). Abgeleitet aus PROTOCOL.md."""
import asyncio
from bleak import BleakScanner

PREFIX = "GreenBox"


def uuid(n: int) -> str:
    return f"0000{n:04x}-0000-1000-8000-00805f9b34fb"


SERVICE = uuid(0xFF)
FF = {i: uuid(0xFF00 + i) for i in range(1, 10)}

START, END = 0xEE, 0xEF
TYPES = {
    ord("1"): "STRIP1", ord("2"): "STRIP2", ord("3"): "STRIP3",
    ord("D"): "ON_DURATION_WORKDAYS", ord("d"): "ON_DURATION_WEEKEND",
    ord("S"): "SWITCH_TIME_WORKDAYS", ord("s"): "SWITCH_TIME_WEEKEND",
    ord("O"): "OVERRIDE", ord("t"): "SET_TIME", ord("C"): "OTA_CHANNEL",
    ord("U"): "OTA_START", ord("T"): "TEMPERATURE", ord("W"): "WATERLEVEL",
    ord("f"): "FIRMWARE_VERSION", ord("r"): "HARDWARE_REVISION",
}
FIRMWARE = {0: "3.0.0", 1: "<=2.0.0", 2: "2.0.0/2.0.1", 3: "2.0.3", 4: "4.0.0", 5: "(5.x reserviert)"}


def checksum(type_byte: int, data: bytes) -> int:
    return (256 - ((START + type_byte + sum(data) + END) % 256)) % 256


def build_frame(type_byte: int, data: bytes) -> bytes:
    return bytes([START, type_byte, *data, checksum(type_byte, data), END])


def parse_frame(raw: bytes):
    """-> (type_byte, data, ok). Summe aller Bytes muss 0 mod 256 sein."""
    if len(raw) < 4 or raw[0] != START or raw[-1] != END:
        return None, raw, False
    return raw[1], bytes(raw[2:-2]), sum(raw) % 256 == 0


def describe(type_byte: int, data: bytes) -> str:
    name = TYPES.get(type_byte, f"?{chr(type_byte) if 32 <= type_byte < 127 else hex(type_byte)}")
    if len(data) == 2:
        v = data[0] * 256 + data[1]  # alle bisher gesehenen Frames: 16-bit big-endian
        if name.startswith("SWITCH_TIME"):
            return f"{name} = {v} -> {v // 100:02d}:{v % 100:02d}"
        if name == "FIRMWARE_VERSION":
            return f"{name} = {v} -> {FIRMWARE.get(v, 'unbekannt')}"
        if name == "OVERRIDE":
            return f"{name} = {v} -> {OVERRIDE_NAMES.get(v, '?')}"
        return f"{name} = {v}"
    return f"{name} = {data.hex()} ({list(data)})"


OVERRIDE_NAMES = {0: "AUS", 1: "AN", 3: "AUTOMATIK"}


async def find_box(timeout: float = 10.0, address: str | None = None):
    """Gerät per Adresse oder per Namenspräfix (name/local_name) finden."""
    if address:
        return await BleakScanner.find_device_by_address(address, timeout=timeout)
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    for dev, adv in found.values():
        names = [dev.name, adv.local_name]
        if any(n and n.startswith(PREFIX) for n in names):
            return dev
    return None
