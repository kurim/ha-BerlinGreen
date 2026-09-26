"""Schaltzeiten und Uhrzeit der GreenBox lesen/setzen (SCHREIBT!). Handy-App vorher trennen.

  py sched.py show                    -> aktuelle Werte (Rohwerte + Ortszeit)
  py sched.py workdays 08:00 12       -> Werktage: Start (Ortszeit) + Dauer in Stunden (12-18)
  py sched.py weekend  09:00 12       -> Wochenende
  py sched.py sync                    -> Uhrzeit der Box setzen (SET_TIME, Unix-UTC)

Firmware < 4 (deine Box): die Box speichert die Startzeit in UTC; das Skript rechnet mit der Zeitzone
dieses PCs um (wie die App). Es zeigt vorher die alten Werte, damit du sie wiederherstellen kannst."""
import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from bleak import BleakClient

sys.path.append(str(Path(__file__).resolve().parent.parent / "custom_components" / "greenbox"))
import protocol as p  # noqa: E402
from gb_common import FF, find_box  # noqa: E402


def usage():
    print(__doc__)
    sys.exit(2)


def parse_args(args):
    if args == ["show"] or args == ["sync"]:
        return args[0], None
    if len(args) == 3 and args[0] in ("workdays", "weekend"):
        try:
            hh, mm = (int(x) for x in args[1].split(":"))
            hours = int(args[2])
            p.frame_duration(False, hours)  # prüft den Bereich
            p.raw_from_local(hh, mm, datetime.now().astimezone(), True)  # prüft die Uhrzeit
        except ValueError as e:
            print("Ungültige Eingabe:", e)
            usage()
        return args[0], (hh, mm, hours)
    usage()


def describe(state: p.BoxState, ref: datetime):
    utc = p.uses_utc(state.firmware)
    print(f"Firmware {state.firmware_name}  ->  Startzeit als {'UTC' if utc else 'lokale Zeit' if utc is False else '?? (unbekannt)'}")
    for name, raw, dur in (("Werktage ", state.switch_workdays, state.duration_workdays),
                           ("Wochenende", state.switch_weekend, state.duration_weekend)):
        if raw is None:
            print(f"  {name}: (noch nicht empfangen)")
            continue
        loc = p.local_from_raw(raw, ref, bool(utc))
        print(f"  {name}: Rohwert {raw:04d} = {loc[0]:02d}:{loc[1]:02d} Ortszeit, Dauer {dur} h")
    return utc


async def main():
    action, arg = parse_args(sys.argv[1:])
    dev = await find_box()
    if not dev:
        print("Keine GreenBox gefunden.")
        return
    state, parser = p.BoxState(), p.FrameParser()

    def on_notify(_, data):
        for t, d in parser.feed(bytes(data)):
            state.apply(t, d)

    async with BleakClient(dev, timeout=20) as c:
        await c.start_notify(FF[5], on_notify)
        await asyncio.sleep(3)  # die Box schickt den Gesamtzustand von selbst
        ref = datetime.now().astimezone()
        print(f"PC-Zeitzone: {ref.tzname()} (UTC{ref.strftime('%z')}), jetzt {ref:%Y-%m-%d %H:%M}")
        print("VORHER:")
        utc = describe(state, ref)
        if action == "show":
            return
        if utc is None:
            print("Firmware unbekannt -> die App schreibt in diesem Fall nichts. Abbruch.")
            return
        if action == "sync":
            frame = p.frame_set_time(int(time.time()))
            print(f"-> SET_TIME {frame.hex()}  ({datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC)")
            await c.write_gatt_char(FF[5], frame, response=False)
            await asyncio.sleep(3)
            print("Gesendet. (Die Box meldet die Uhrzeit nicht zurück; prüfe am Verhalten des Lichts.)")
            return
        hh, mm, hours = arg
        weekend = action == "weekend"
        raw = p.raw_from_local(hh, mm, ref, utc)
        frames = [p.frame_switch_time(weekend, raw), p.frame_duration(weekend, hours)]
        print(f"-> {action}: {hh:02d}:{mm:02d} Ortszeit = Rohwert {raw:04d}, Dauer {hours} h")
        for f in frames:
            print("   sende", f.hex())
            await c.write_gatt_char(FF[5], f, response=False)
            await asyncio.sleep(0.3)
        await asyncio.sleep(3)
        print("NACHHER:")
        describe(state, ref)


asyncio.run(main())
