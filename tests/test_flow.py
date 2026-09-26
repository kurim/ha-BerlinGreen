"""Einrichtungsablauf: Menü, Bluetooth-Box, Cloud-Konto, Neuanmeldung, Optionen.   python tests/test_flow.py"""
import asyncio
import importlib
import sys
import types

import _stubs

_stubs.install()


class Abort(Exception):
    pass


class BaseFlow:
    hass, entries, uid, reauth = object(), [], None, None

    def __init_subclass__(cls, **kw): pass
    def __new__(cls, *a, **k):
        o = super().__new__(cls)
        o.context, o.entries = {}, []
        return o
    def _async_current_entries(self): return self.entries
    def _async_current_ids(self): return {e.unique_id for e in self.entries}
    async def async_set_unique_id(self, u): self.uid = u
    def _abort_if_unique_id_configured(self):
        if self.uid in {e.unique_id for e in self.entries}:
            raise Abort("already_configured")
    def async_show_menu(self, step_id, menu_options): return {"type": "menu", "step": step_id, "options": menu_options}
    def async_show_form(self, step_id, data_schema=None, errors=None, description_placeholders=None): return {"type": "form", "step": step_id, "errors": errors or {}, "schema": data_schema}
    def async_create_entry(self, title, data=None): return {"type": "create", "title": title, "data": data}
    def async_abort(self, reason): return {"type": "abort", "reason": reason}
    def _set_confirm_only(self): pass
    def add_suggested_values_to_schema(self, schema, values): return schema
    def async_update_reload_and_abort(self, entry, data=None, data_updates=None): return {"type": "update", "data": data, "updates": data_updates}
    def _get_reauth_entry(self): return self.reauth
    def _get_reconfigure_entry(self): return self.reauth


class OptionsBase:
    def async_show_form(self, step_id, data_schema=None): return {"type": "form", "step": step_id, "schema": data_schema}
    def async_create_entry(self, data): return {"type": "create", "data": data}
    def async_abort(self, reason): return {"type": "abort", "reason": reason}


class Info:
    def __init__(self, a, n): self.address, self.name = a, n


FOUND = [Info(_stubs.MAC1, "GreenBoxOne"), Info("11:22:33:44:55:66", "Phone"), Info(_stubs.MAC2, "GreenBoxTwo")]
sys.modules["homeassistant.config_entries"].ConfigFlow = BaseFlow
sys.modules["homeassistant.config_entries"].OptionsFlow = OptionsBase
sys.modules["homeassistant.components.bluetooth"].async_discovered_service_info = lambda h, connectable=True: FOUND
_stubs.package()
cf = importlib.import_module("greenbox.config_flow")
api = importlib.import_module("greenbox.api")
fails = 0


def check(cond, msg):
    global fails
    print(("  ok    " if cond else "  FEHLT ") + msg)
    fails += not cond


class E:
    def __init__(self, uid, data, options=None): self.unique_id, self.data, self.options = uid, data, options or {}


async def main():
    f = cf.GreenBoxConfigFlow()
    r = await f.async_step_user()
    check(r["type"] == "menu" and r["options"] == ["ble", "cloud"], "Menü: Bluetooth-Box oder Cloud-Konto")
    f.entries = [E("greenbox_cloud", {"cloud": True})]
    check((await f.async_step_user())["options"] == ["ble"], "mit vorhandenem Cloud-Konto nur noch Bluetooth-Box")
    f.entries = [E(_stubs.MAC1, {"address": _stubs.MAC1})]
    r = await f.async_step_ble()
    check(list(r["schema"].schema.values())[0].container.keys() == {_stubs.MAC2}, "Auswahl: nur neue GreenBoxen (nicht eingerichtete/fremde Geräte ausgeblendet)")
    r = await f.async_step_ble({"address": _stubs.MAC2})
    check(r["type"] == "create" and r["data"] == {"address": _stubs.MAC2, "name": "GreenBoxTwo"}, "Bluetooth-Box anlegen")
    cf.async_discovered_service_info = lambda h, connectable=True: []
    check((await cf.GreenBoxConfigFlow().async_step_ble())["reason"] == "no_devices_found", "keine Box in Reichweite: klare Meldung")

    K = _stubs.FAKE_KEY
    async def _ok(): return {"refresh_token": "RT", "uid": "U"}
    async def _bad(): raise api.AuthError("INVALID_LOGIN_CREDENTIALS")
    async def _key(): raise api.ApiKeyError("API key not valid")
    async def _net(): raise api.ApiError("offline")
    seen = {}
    def good(s, e, p, k):
        seen["key"] = k
        return _ok()
    f = cf.GreenBoxConfigFlow()
    cf.sign_in = good
    check((await f.async_step_cloud())["step"] == "cloud", "Cloud-Formular")
    r = await f.async_step_cloud({"email": " a@b.de ", "password": "pw", "api_key": " " + K + " "})
    check(r["type"] == "create" and r["data"] == {"cloud": True, "email": "a@b.de", "api_key": K, "refresh_token": "RT"} and f.uid == "greenbox_cloud"
          and "password" not in r["data"] and seen["key"] == K, "Cloud-Konto: Token und API-Schlüssel gespeichert (getrimmt), kein Passwort")
    seen.clear()
    r = await cf.GreenBoxConfigFlow().async_step_cloud({"email": "a", "password": "b", "api_key": "kein-schluessel"})
    check(r["errors"] == {"api_key": "invalid_api_key"} and not seen, "falsches Schlüsselformat wird abgelehnt, ohne Anfrage an Google")
    cf.sign_in = lambda s, e, p, k: _key()
    check((await cf.GreenBoxConfigFlow().async_step_cloud({"email": "a", "password": "b", "api_key": K}))["errors"] == {"api_key": "invalid_api_key"}, "Google lehnt den Schlüssel ab -> Fehler am Schlüsselfeld")
    cf.sign_in = lambda s, e, p, k: _bad()
    check((await cf.GreenBoxConfigFlow().async_step_cloud({"email": "a", "password": "b", "api_key": K}))["errors"] == {"base": "invalid_auth"}, "falsches Passwort")
    cf.sign_in = lambda s, e, p, k: _net()
    check((await cf.GreenBoxConfigFlow().async_step_cloud({"email": "a", "password": "b", "api_key": K}))["errors"] == {"base": "cannot_connect"}, "kein Netz")
    cf.sign_in = good
    f = cf.GreenBoxConfigFlow(); f.entries = [E("greenbox_cloud", {"cloud": True})]
    try:
        await f.async_step_cloud({"email": "a@b.de", "password": "pw", "api_key": K})
        ok = False
    except Abort:
        ok = True
    check(ok, "ein zweites Cloud-Konto wird abgelehnt")
    f = cf.GreenBoxConfigFlow(); f.reauth = E("greenbox_cloud", {"cloud": True, "email": "a@b.de", "refresh_token": "OLD"})
    r = await f.async_step_reauth({})
    r2 = await f.async_step_reauth_confirm({"password": "pw", "api_key": K})
    check(r["step"] == "reauth_confirm" and r2["updates"] == {"refresh_token": "RT", "api_key": K}, "Neuanmeldung setzt Token und (fehlenden) API-Schlüssel, z. B. nach dem Update von 0.5.0")
    check(list(r["schema"].schema)[1].default() == "", "ohne gespeicherten Schlüssel ist das Feld leer")
    f.reauth = E("greenbox_cloud", {"cloud": True, "email": "a@b.de", "api_key": K, "refresh_token": "OLD"})
    r = await f.async_step_reauth_confirm()
    check(list(r["schema"].schema)[1].default() == K, "mit gespeichertem Schlüssel ist das Feld vorbelegt")
    cf.sign_in = lambda s, e, p, k: _bad()
    check((await f.async_step_reauth_confirm({"password": "x", "api_key": K}))["errors"] == {"base": "invalid_auth"}, "Neuanmeldung mit falschem Passwort")
    f.reauth = E("x", {"address": "A"})
    check((await f.async_step_reconfigure())["reason"] == "reconfigure_not_supported", "Bluetooth-Eintrag lässt sich nicht als Cloud-Konto neu konfigurieren")
    o = cf.GreenBoxOptions(); o.config_entry = E("x", {"address": "A"}, {"show_cannabis": True})
    r = await o.async_step_init()
    check(r["type"] == "form" and list(r["schema"].schema)[0].default() is True and (await o.async_step_init({"show_cannabis": False}))["data"] == {"show_cannabis": False}, "Optionen einer Box: Cannabis anzeigen")
    o.config_entry = E("c", {"cloud": True})
    check((await o.async_step_init())["reason"] == "no_options", "Cloud-Eintrag hat keine Optionen")
    print("\n" + ("%d FEHLER" % fails if fails else "alle Tests ok"))
    sys.exit(1 if fails else 0)


asyncio.run(main())
