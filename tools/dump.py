"""Verbindet sich mit der Box, listet GATT auf und liest ff03/ff06/ff07/ff08 (nur lesend).
Nutzung: py dump.py [adresse]     (Handy-App vorher schließen/trennen!)"""
import asyncio
import sys
from bleak import BleakClient
from gb_common import FF, find_box


def show(raw: bytes) -> str:
    try:
        txt = raw.decode("utf-8")
        if txt.isprintable():
            return f"{txt!r}  (hex {raw.hex()})"
    except UnicodeDecodeError:
        pass
    return f"hex {raw.hex()}"


async def main():
    dev = await find_box(address=sys.argv[1] if len(sys.argv) > 1 else None)
    if not dev:
        print("Keine GreenBox gefunden.")
        return
    print(f"Verbinde mit {dev.address} ({dev.name}) ...")
    async with BleakClient(dev, timeout=20) as c:
        print(f"Verbunden. MTU={c.mtu_size}\n")
        for svc in c.services:
            print(f"Service {svc.uuid}")
            for ch in svc.characteristics:
                print(f"  {ch.uuid}  props={','.join(ch.properties)}")
        print()
        for n in (3, 6, 7, 8):
            uid = FF[n]
            ch = c.services.get_characteristic(uid)
            if not ch:
                print(f"ff{n:02x}: nicht vorhanden (ältere Firmware?)")
            elif "read" not in ch.properties:
                print(f"ff{n:02x}: nicht lesbar ({','.join(ch.properties)})")
            else:
                try:
                    print(f"ff{n:02x}: {show(bytes(await c.read_gatt_char(uid)))}")
                except Exception as e:  # noqa: BLE001
                    print(f"ff{n:02x}: Lesefehler {e!r}")


asyncio.run(main())
