"""Liest deine Boxen, Slots und Pflanzen aus der Berlin-Green-Cloud (NUR LESEN, nur Python-Standardbibliothek).

  py cloud.py

Fragt E-Mail und Passwort ab (oder Umgebungsvariablen GB_EMAIL / GB_PASSWORD), meldet sich wie die App über
Firebase Auth an und ruft dieselbe GraphQL-Abfrage wie die App ab (QueryBoxes + Details). Ausgabe: Übersicht
im Terminal und die Rohdaten in cloud_dump.json (enthält KEINE Zugangsdaten/Tokens, aber deine Box-/Pflanzendaten).
Das Passwort geht nur an Google (Firebase). Es wird nirgends gespeichert oder ausgegeben."""
import base64
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# Den Firebase-API-Schlüssel der App liefert das Repository nicht mit. Er wird aus GB_API_KEY oder per Eingabe gelesen;
# `python tools/extract_key.py <APK/XAPK>` liest ihn aus der App-Datei aus.
SIGN_IN = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={key}"
REFRESH = "https://securetoken.googleapis.com/v1/token?key={key}"
_KEY = os.environ.get("GB_API_KEY", "").strip()


def api_key() -> str:
    global _KEY
    if not _KEY:
        _KEY = input("API-Schlüssel der App (python tools/extract_key.py <APK/XAPK>): ").strip()
    if not _KEY.startswith("AIza") or len(_KEY) != 39:
        raise SystemExit("Der API-Schlüssel muss mit AIza beginnen und 39 Zeichen lang sein.")
    return _KEY

GRAPHQL = "https://backend.berlingreen.tech/v1alpha1/graphql"
CLAIMS = "https://hasura.io/jwt/claims"

QUERY = """
query GreenboxOverview {
  box {
    id box_id name type light_intensity light_temperature light_set_at
    packages(where: {removed_at: {_is_null: true}, planted_at: {_is_null: false}}) {
      id planted_at layout
      mix { id name { de en } growth_speed }
      planted { slot plant { id name { de en } user_provided_name } }
    }
    microgreen_configs {
      id
      planted_microgreens {
        id slot plantedOnDay
        microgreen { id growthTimeDays sproutTimeDays name { de en } }
      }
    }
    mushroom_config {
      id
      planted_mushrooms {
        id plantedOnDay
        mushroom { id pinningTimeDays growthTimeDays harvestTimeDays name { de en } }
      }
    }
  }
}
"""


class CloudError(Exception):
    pass


def post_json(url: str, payload: dict, headers: dict | None = None, form: bool = False) -> dict:
    if form:
        from urllib.parse import urlencode
        data, ctype = urlencode(payload).encode(), "application/x-www-form-urlencoded"
    else:
        data, ctype = json.dumps(payload).encode(), "application/json"
    req = urllib.request.Request(url, data=data, headers={"Content-Type": ctype, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", "replace")
        try:
            msg = json.loads(body).get("error", body)
            msg = msg.get("message", msg) if isinstance(msg, dict) else msg
        except ValueError:
            msg = body[:300]
        raise CloudError(f"HTTP {err.code}: {msg}") from None
    except urllib.error.URLError as err:
        raise CloudError(f"Netzwerkfehler: {err.reason}") from None


def jwt_payload(token: str) -> dict:
    part = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


def login(email: str, password: str) -> str:
    """Firebase-Anmeldung -> ID-Token mit Hasura-Claim (wie die App: ggf. kurz warten und Token erneuern)."""
    try:
        res = post_json(SIGN_IN.format(key=api_key()), {"email": email, "password": password, "returnSecureToken": True})
    except CloudError as err:
        text = str(err)
        if "API_KEY_ANDROID_APP_BLOCKED" in text or "blocked" in text.lower():
            raise CloudError(
                "Der API-Schlüssel ist auf die Android-App beschränkt; Anmeldung von außerhalb wird abgelehnt.\n"
                "Das umgehe ich bewusst nicht (kein Vortäuschen der App). Ohne Hersteller-Freigabe geht dieser Weg nicht."
            ) from None
        if "INVALID_LOGIN_CREDENTIALS" in text or "INVALID_PASSWORD" in text or "EMAIL_NOT_FOUND" in text:
            raise CloudError("E-Mail oder Passwort falsch. (Anmeldung über Google/Apple funktioniert so nicht.)") from None
        raise
    token, refresh = res["idToken"], res["refreshToken"]
    for attempt in range(4):
        if CLAIMS in jwt_payload(token):
            return token
        print(f"  Hasura-Claim noch nicht im Token, warte und erneuere ({attempt + 1}/4) ...")
        time.sleep(3)
        token = post_json(REFRESH.format(key=api_key()), {"grant_type": "refresh_token", "refresh_token": refresh}, form=True)["id_token"]
    raise CloudError("Das Token enthält keinen Hasura-Claim - der Server würde Abfragen ablehnen.")


def graphql(token: str, query: str) -> dict:
    res = post_json(GRAPHQL, {"query": query}, headers={"Authorization": f"Bearer {token}"})
    if res.get("errors"):
        raise CloudError("GraphQL-Fehler: " + json.dumps(res["errors"], ensure_ascii=False)[:600])
    return res["data"]


def graphql_vars(token: str, query: str, variables: dict) -> dict:
    res = post_json(GRAPHQL, {"query": query, "variables": variables}, headers={"Authorization": f"Bearer {token}"})
    if res.get("errors"):
        raise CloudError("GraphQL-Fehler: " + json.dumps(res["errors"], ensure_ascii=False)[:600])
    return res["data"]


def name_of(i18n: dict | None) -> str:
    return "?" if not i18n else (i18n.get("de") or i18n.get("en") or "?")


def days_since(iso: str | None) -> str:
    if not iso:
        return "?"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            dt = datetime.strptime(iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return "?"
    return f"{(datetime.now(timezone.utc) - dt).total_seconds() / 86400:.1f} Tage"


def summarize(data: dict) -> None:
    boxes = data.get("box", [])
    print(f"\n{len(boxes)} Box(en) im Konto:")
    for b in boxes:
        print(f"\n== {b['name']}  (Typ {b['type']}, BLE-Kennung {b['box_id']})")
        if b.get("light_intensity") is not None:
            print(f"   Licht laut Cloud: Intensität {b['light_intensity']}, Temperatur {b['light_temperature']}, gesetzt {b['light_set_at']}")
        for pkg in b.get("packages", []):
            print(f"   Paket: {name_of((pkg.get('mix') or {}).get('name'))}, gepflanzt {pkg['planted_at']} ({days_since(pkg['planted_at'])}), "
                  f"Layout {pkg.get('layout')}, Wachstumsgeschwindigkeit {(pkg.get('mix') or {}).get('growth_speed')}")
            for s in sorted(pkg.get("planted", []), key=lambda x: x["slot"]):
                plant = s.get("plant") or {}
                print(f"     Slot {s['slot']}: {plant.get('user_provided_name') or name_of(plant.get('name'))}")
        for cfg in b.get("microgreen_configs", []):
            for m in sorted(cfg.get("planted_microgreens", []), key=lambda x: x["slot"]):
                mg = m.get("microgreen") or {}
                print(f"   Microgreen Slot {m['slot']}: {name_of(mg.get('name'))}, gepflanzt {m['plantedOnDay']} ({days_since(m['plantedOnDay'])}), "
                      f"Keimung {mg.get('sproutTimeDays')} Tage, Wachstum {mg.get('growthTimeDays')} Tage")
        mc = b.get("mushroom_config") or []
        for cfg in mc if isinstance(mc, list) else [mc]:  # die Cloud liefert eine Liste (früher als Objekt angenommen)
            for m in cfg.get("planted_mushrooms", []):
                mu = m.get("mushroom") or {}
                print(f"   Pilz: {name_of(mu.get('name'))}, gepflanzt {m['plantedOnDay']} ({days_since(m['plantedOnDay'])}), "
                      f"Pinning {mu.get('pinningTimeDays')} / Wachstum {mu.get('growthTimeDays')} / Ernte {mu.get('harvestTimeDays')} Tage")


def main() -> None:
    email = os.environ.get("GB_EMAIL") or input("E-Mail: ").strip()
    password = os.environ.get("GB_PASSWORD") or getpass.getpass("Passwort (wird nicht angezeigt): ")
    try:
        print("Anmeldung ...")
        token = login(email, password)
        claims = jwt_payload(token).get(CLAIMS, {})
        print(f"  ok. Rolle: {claims.get('x-hasura-default-role')}, erlaubte Rollen: {claims.get('x-hasura-allowed-roles')}")
        data = graphql(token, QUERY)
    except CloudError as err:
        print("Fehler:", err)
        sys.exit(1)
    summarize(data)
    with open("cloud_dump.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\nRohdaten: cloud_dump.json")


if __name__ == "__main__":
    main()
