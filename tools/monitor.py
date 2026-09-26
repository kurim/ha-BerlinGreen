"""Abonniert Notifications der Box (ff05, wenn möglich auch ff06) und dekodiert die Frames.
Nutzung: py monitor.py [adresse]   -- Strg+C beendet. Nur lesend."""
import asyncio
import sys
import time
from bleak import BleakClient
from gb_common import FF, find_box, parse_frame, describe

buf = bytearray()


def on_ff05(_, data: bytearray):
    # Notifications können Frames teilen/bündeln -> Puffer, an 0xEF trennen
    buf.extend(data)
    while True:
        try:
            end = buf.index(0xEF)
        except ValueError:
            return
        frame, rest = bytes(buf[: end + 1]), buf[end + 1:]
        buf.clear()
        buf.extend(rest)
        t, d, ok = parse_frame(frame)
        stamp = time.strftime("%H:%M:%S")
        if t is None:
            print(f"{stamp} ff05 kein gültiges Framing: {frame.hex()}")
        else:
            print(f"{stamp} ff05 {'OK ' if ok else 'CHK'} {describe(t, d)}   [{frame.hex()}]")


def on_other(name):
    def cb(_, data: bytearray):
        print(f"{time.strftime('%H:%M:%S')} {name} {bytes(data)!r}  (hex {bytes(data).hex()})")
    return cb


async def main():
    dev = await find_box(address=sys.argv[1] if len(sys.argv) > 1 else None)
    if not dev:
        print("Keine GreenBox gefunden.")
        return
    print(f"Verbinde mit {dev.address} ({dev.name}) ...")
    async with BleakClient(dev, timeout=20) as c:
        await c.start_notify(FF[5], on_ff05)
        print("Abonniert ff05.")
        ch6 = c.services.get_characteristic(FF[6])
        if ch6 and "notify" in ch6.properties:
            try:
                await c.start_notify(FF[6], on_other("ff06"))
                print("Abonniert ff06.")
            except Exception as e:  # noqa: BLE001 - alte Firmware: CCCD nicht schreibbar
                print(f"ff06 nicht abonnierbar ({e}), weiter ohne.")
        print("Warte auf Daten (Strg+C beendet) ...")
        while c.is_connected:
            await asyncio.sleep(1)
        print("Verbindung getrennt.")


try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
