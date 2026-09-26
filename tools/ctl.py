"""Steuert die GreenBox über ff05 (SCHREIBT!). Nutzung (Handy-App vorher trennen):
  py ctl.py override on|off|auto
  py ctl.py strip 1|2|3 0-100
Es wird genau ein Frame gesendet; danach werden 3 s lang die Rückmeldungen der Box angezeigt.
Nach Tests wieder:  py ctl.py override auto   und Streifen zurück auf den Ausgangswert (bei dir: 100)."""
import asyncio
import sys
from bleak import BleakClient
from gb_common import FF, build_frame, find_box, parse_frame, describe

OVERRIDE = {"off": 0, "on": 1, "auto": 3}


def usage():
    print(__doc__)
    sys.exit(2)


def make_frame(args):
    if len(args) == 2 and args[0] == "override" and args[1] in OVERRIDE:
        return build_frame(ord("O"), bytes([0, OVERRIDE[args[1]]]))
    if len(args) == 3 and args[0] == "strip" and args[1] in ("1", "2", "3") and args[2].isdigit() and 0 <= int(args[2]) <= 100:
        return build_frame(ord(args[1]), bytes([0, int(args[2])]))
    usage()


def on_notify(_, data: bytearray):
    t, d, ok = parse_frame(bytes(data))
    print("  <-", describe(t, d) if t is not None else bytes(data).hex(), "" if ok else "(Prüfsumme?)")


async def main():
    frame = make_frame(sys.argv[1:])
    dev = await find_box()
    if not dev:
        print("Keine GreenBox gefunden.")
        return
    async with BleakClient(dev, timeout=20) as c:
        await c.start_notify(FF[5], on_notify)
        await asyncio.sleep(1.5)  # Statusflut nach dem Abonnieren abwarten
        print(f"-> sende {frame.hex()}")
        await c.write_gatt_char(FF[5], frame, response=False)
        await asyncio.sleep(3)


asyncio.run(main())
