"""Testet 'Bei niedrigem Wasser blinken' (ff06). SCHREIBT!  Nutzung (Handy-App trennen):
  py blink.py            -> nur ff06 lesen
  py blink.py on|off     -> ASCII '1'/'0' nach ff06 schreiben (mit Response), danach zurücklesen
Format ff06 (aus dem App-Code): "blink,?,plus" -> Feld 0 == '1' = Blinken an, Feld 2 == '1' = Plus-Box."""
import asyncio
import sys
from bleak import BleakClient
from gb_common import FF, find_box


async def read(c):
    raw = bytes(await c.read_gatt_char(FF[6]))
    print(f"ff06 = {raw!r}  -> Felder {raw.decode(errors='replace').split(',')}")


async def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg not in (None, "on", "off"):
        print(__doc__)
        return
    dev = await find_box()
    if not dev:
        print("Keine GreenBox gefunden.")
        return
    async with BleakClient(dev, timeout=20) as c:
        await read(c)
        if arg:
            await c.write_gatt_char(FF[6], b"1" if arg == "on" else b"0", response=True)
            print(f"geschrieben: {'1' if arg == 'on' else '0'}")
            await asyncio.sleep(1)
            await read(c)


asyncio.run(main())
