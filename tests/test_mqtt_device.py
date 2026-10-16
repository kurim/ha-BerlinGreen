"""GreenBoxMqttDevice: Zustand aus dem state-Topic, Befehle als set-Topics.   python tests/test_mqtt_device.py"""
import asyncio
import importlib
import json
import types

import _stubs

_stubs.install()
_stubs.package()
md = importlib.import_module("greenbox.mqtt_device")
proto = importlib.import_module("greenbox.protocol")
fails = 0


def check(cond, msg):
    global fails
    print(("  ok    " if cond else "  FEHLT ") + msg)
    fails += not cond


class Msg:
    def __init__(self, payload):
        self.payload = payload


def make_hass():
    return types.SimpleNamespace(mqtt_subscriptions={}, mqtt_published=[])


STATE = {
    "stripe1": 100, "stripe2": 50, "stripe3": 0, "override": "auto",
    "start": "18:00", "start_weekend": "19:30", "duration": 12, "duration_weekend": 14,
    "water": 50, "low_water": False, "blink_on_low_water": True, "fw_byte": 3,
}


async def main():
    hass = make_hass()
    dev = md.GreenBoxMqttDevice(hass, "greenbox/8c4b14c8", "GreenBox MQTT")
    await dev.async_start()
    check(set(hass.mqtt_subscriptions) == {"greenbox/8c4b14c8/state", "greenbox/8c4b14c8/availability"}, "abonniert state + availability")
    check(dev.connected is False, "vor der ersten Nachricht nicht verbunden")

    calls = []
    dev.register_callback(lambda: calls.append(1))
    for cb in hass.mqtt_subscriptions["greenbox/8c4b14c8/state"]:
        cb(Msg(json.dumps(STATE)))
    check(dev.connected and calls, "state-Nachricht macht verbunden und benachrichtigt")
    st = dev.state
    check(st.strips == {1: 100, 2: 50, 3: 0} and st.override == 3 and st.switch_workdays == 1800 and st.switch_weekend == 1930
          and st.duration_workdays == 12 and st.duration_weekend == 14 and st.water == 50 and st.blink_on_low_water is True
          and st.firmware == 3, "state-JSON korrekt in BoxState übernommen")
    check(dev.schedule_view("workdays") is not None, "Schaltzeit lesbar (fw_byte bekannt)")

    for cb in hass.mqtt_subscriptions["greenbox/8c4b14c8/availability"]:
        cb(Msg("offline"))
    check(dev.connected is False, "availability=offline wird übernommen")
    for cb in hass.mqtt_subscriptions["greenbox/8c4b14c8/availability"]:
        cb(Msg("online"))
    check(dev.connected is True, "availability=online wird übernommen")

    await dev.async_write(proto.frame_strip(1, 42))
    check(hass.mqtt_published[-1] == ("greenbox/8c4b14c8/set/stripe1", "42", False), "async_write (BLE-Frame) -> MQTT-set-Topic")
    await dev.async_write(proto.frame_override(proto.OVERRIDE_ON))
    check(hass.mqtt_published[-1] == ("greenbox/8c4b14c8/set/override", "on", False), "Override-Frame -> set/override")

    await dev.async_set_blink(False)
    check(hass.mqtt_published[-1] == ("greenbox/8c4b14c8/set/blink", "0", False) and dev.state.blink_on_low_water is False, "Blinken aus (optimistisch)")

    await dev.async_set_light(50, 2)
    published = hass.mqtt_published[-3:]
    check([p[:2] for p in published] == [("greenbox/8c4b14c8/set/stripe1", "50"), ("greenbox/8c4b14c8/set/stripe2", "50"), ("greenbox/8c4b14c8/set/stripe3", "50")],
          "Lichtprofil -> drei Streifen-Topics")

    await dev.async_set_schedule("workdays", hour=7, minute=30)
    pubs = {p[0]: p[1] for p in hass.mqtt_published[-2:]}
    check(pubs == {"greenbox/8c4b14c8/set/start": "730", "greenbox/8c4b14c8/set/duration": "12"}, "Startzeit ändern schreibt start + duration (bisherige Dauer bleibt)")
    check(dev.schedule_view("workdays") == (7, 30, 12), "Schaltzeit danach sofort korrekt (optimistisch, nicht erst nach dem nächsten state)")

    await dev.async_stop()
    check(not hass.mqtt_subscriptions["greenbox/8c4b14c8/state"] and not hass.mqtt_subscriptions["greenbox/8c4b14c8/availability"], "async_stop meldet ab")

    dev2 = md.GreenBoxMqttDevice(make_hass(), "greenbox/x", "x")
    try:
        await dev2.async_write(proto.frame_strip(1, 1))
        ok = False
    except Exception:
        ok = True
    check(ok, "ohne Verbindung wird kein Befehl gesendet (HomeAssistantError)")

    dev3 = md.GreenBoxMqttDevice(make_hass(), "greenbox/y", "y")
    learned = []
    dev3.on_ble_address = learned.append
    dev3._on_state(Msg(json.dumps({**STATE, "ble": "aa:bb:cc:dd:ee:03", "fw": "5.0.3"})))
    check(dev3.ble_address == "AA:BB:CC:DD:EE:03" and learned == ["AA:BB:CC:DD:EE:03"], "gemeldete BLE-Adresse wird (groß) übernommen und gemeldet")
    dev3._on_state(Msg(json.dumps({**STATE, "ble": "aa:bb:cc:dd:ee:03", "fw": "5.0.3"})))
    check(len(learned) == 1, "gleiche Adresse löst nichts erneut aus")
    check(dev3.state.firmware_name == "5.0.3", "Firmware-Anzeige zeigt die echte Version statt des Kompatibilitätswerts")
    check(dev3.schedule_view("workdays") is not None, "Kompatibilitätsbyte (fw_byte) steuert weiter die Zeitlogik")

    print("\n" + ("%d FEHLER" % fails if fails else "alle Tests ok"))
    exit(1 if fails else 0)


asyncio.run(main())
