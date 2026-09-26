"""Listet BLE-Geräte in der Nähe; GreenBoxen werden markiert.  Nutzung: py scan.py [sekunden]"""
import asyncio
import sys
from bleak import BleakScanner
from gb_common import PREFIX


async def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 10
    found = await BleakScanner.discover(timeout=secs, return_adv=True)
    rows = sorted(found.values(), key=lambda t: -t[1].rssi)
    for dev, adv in rows:
        names = [n for n in (dev.name, adv.local_name) if n]
        mark = "  <== GreenBox" if any(n.startswith(PREFIX) for n in names) else ""
        print(f"{dev.address}  rssi={adv.rssi:4}  {', '.join(sorted(set(names))) or '-'}{mark}")
        if mark:
            print(f"    service_uuids={adv.service_uuids}  manufacturer={ {k: v.hex() for k, v in adv.manufacturer_data.items()} }")
    print(f"\n{len(rows)} Geräte gefunden.")


asyncio.run(main())
