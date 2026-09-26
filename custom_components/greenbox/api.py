"""Cloud-Zugriff: Firebase-Anmeldung wie die App, GraphQL-Abfragen wie die App; Schreiben nur im optionalen Cloud-Modus."""
from __future__ import annotations

import base64
import json
import re
from typing import Any

import aiohttp

# Den Firebase-API-Schlüssel der App liefert die Integration bewusst nicht mit: er wird beim Einrichten des Cloud-Kontos
# abgefragt (mit tools/extract_key.py aus der App-Datei auslesbar).
API_KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
SIGN_IN = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={key}"
REFRESH = "https://securetoken.googleapis.com/v1/token?key={key}"
GRAPHQL = "https://backend.berlingreen.tech/v1alpha1/graphql"
CLAIMS = "https://hasura.io/jwt/claims"

QUERY = """
query GreenboxOverview {
  box {
    id box_id name type
    packages(where: {removed_at: {_is_null: true}, planted_at: {_is_null: false}}) {
      id planted_at layout
      mix { id name { de en } growth_speed }
      planted { slot plant { id name { de en } user_provided_name photo } }
    }
    microgreen_configs {
      id
      planted_microgreens {
        id slot plantedOnDay
        microgreen { id growthTimeDays sproutTimeDays name { de en } encyclopedia { image } }
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


# Änderungen, die im Cloud-Modus geschickt werden. Es sind dieselben Operationen, die auch die App für das Bepflanzen benutzt
# (PlantNew, InsertSlot, UpdateSlot, SetMicrogreenConfig, AddPlantedMicrogreen, DeletePlantedMicrogreen, DeleteMicrogreenModule);
# das Entfernen eines Pakets setzt nur removed_at (die App löscht dabei zusätzlich die Microgreens-Module).
MUTATIONS = {
    "plant_new": """
mutation PlantNew($boxId: uuid!, $mixId: Int!, $plantedAt: timestamptz!, $layout: String!, $planted: [planted_insert_input!]!) {
  insert_package(objects: {box_id: $boxId, mix_id: $mixId, planted_at: $plantedAt, layout: $layout, planted: {data: $planted}}) { affected_rows }
}""",
    "remove_packages": """
mutation RemovePackages($ids: [Int!]!, $removedAt: timestamptz!) {
  update_package(where: {id: {_in: $ids}}, _set: {removed_at: $removedAt}) { affected_rows }
}""",
    "insert_slot": """
mutation InsertSlot($packageId: Int!, $slot: Int!, $plantId: Int!) {
  insert_planted(objects: {package_id: $packageId, plant_id: $plantId, slot: $slot}) { affected_rows }
}""",
    "update_slot": """
mutation UpdateSlot($packageId: Int!, $slot: Int!, $plantId: Int!) {
  update_planted(where: {package_id: {_eq: $packageId}, slot: {_eq: $slot}}, _set: {plant_id: $plantId}) { affected_rows }
}""",
    "set_microgreen_config": """
mutation SetMicrogreenConfig($boxId: uuid!, $planted_microgreens: [planted_microgreen_insert_input!]!) {
  insert_microgreen_config(objects: {box_id: $boxId, planted_microgreens: {data: $planted_microgreens}}) { affected_rows }
}""",
    "add_microgreen": """
mutation AddPlantedMicrogreen($microgreenConfigId: uuid!, $microgreenId: Int!, $plantedOnDay: date!, $slot: Int!) {
  insert_planted_microgreen(objects: {microgreen_config_id: $microgreenConfigId, microgreen_id: $microgreenId, plantedOnDay: $plantedOnDay, slot: $slot}) { affected_rows }
}""",
    "delete_microgreen": """
mutation DeletePlantedMicrogreen($microgreenConfigId: uuid!, $slot: Int!) {
  delete_planted_microgreen(where: {_and: [{slot: {_eq: $slot}}, {microgreen_config_id: {_eq: $microgreenConfigId}}]}) { affected_rows }
}""",
    "delete_module": """
mutation DeleteMicrogreenModule($id: uuid!) {
  delete_microgreen_config_by_pk(id: $id) { id }
}""",
}


class AuthError(Exception):
    """Anmeldung/Token abgelehnt (Passwort geändert, Konto gesperrt ...)."""


class ApiKeyError(Exception):
    """Der API-Schlüssel fehlt, ist ungültig oder auf die App beschränkt."""


class ApiError(Exception):
    """Vorübergehender Fehler (Netzwerk, Server)."""


def jwt_payload(token: str) -> dict[str, Any]:
    part = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))


async def _post(session: aiohttp.ClientSession, url: str, *, json_body=None, form=None, headers=None) -> dict[str, Any]:
    try:
        async with session.post(url, json=json_body, data=form, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            body = await resp.text()
            if resp.status >= 400:
                try:
                    err = json.loads(body).get("error", body)
                    msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                except ValueError:
                    msg = body[:200]
                if "API key not valid" in msg or "API_KEY_INVALID" in msg or "blocked" in msg.lower():
                    raise ApiKeyError(msg)
                if resp.status in (400, 401, 403) and any(k in msg for k in ("INVALID", "TOKEN", "EMAIL_NOT_FOUND", "USER_DISABLED", "PASSWORD")):
                    raise AuthError(msg)
                raise ApiError(f"HTTP {resp.status}: {msg}")
            return json.loads(body)
    except (aiohttp.ClientError, TimeoutError) as err:
        raise ApiError(f"Netzwerkfehler: {err}") from err


def valid_key_format(key: str) -> bool:
    return bool(API_KEY_PATTERN.fullmatch(key.strip()))


async def sign_in(session: aiohttp.ClientSession, email: str, password: str, api_key: str) -> dict[str, str]:
    """Passwort-Anmeldung. Liefert refresh_token und uid; das Passwort wird NICHT gespeichert."""
    res = await _post(session, SIGN_IN.format(key=api_key.strip()),
                      json_body={"email": email, "password": password, "returnSecureToken": True})
    return {"refresh_token": res["refreshToken"], "uid": res["localId"]}


class GreenboxCloud:
    def __init__(self, session: aiohttp.ClientSession, refresh_token: str, api_key: str) -> None:
        self._session = session
        self.refresh_token = refresh_token
        self.api_key = api_key

    async def _id_token(self) -> str:
        res = await _post(self._session, REFRESH.format(key=self.api_key), form={"grant_type": "refresh_token", "refresh_token": self.refresh_token})
        self.refresh_token = res.get("refresh_token", self.refresh_token)
        token = res["id_token"]
        if CLAIMS not in jwt_payload(token):
            raise ApiError("Token enthält noch keinen Hasura-Claim")  # kurz nach Kontoerstellung möglich
        return token

    async def _graphql(self, token: str, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables
        res = await _post(self._session, GRAPHQL, json_body=body, headers={"Authorization": f"Bearer {token}"})
        if res.get("errors"):
            raise ApiError("GraphQL-Fehler: " + json.dumps(res["errors"], ensure_ascii=False)[:300])
        return res["data"]

    async def fetch(self) -> dict[str, Any]:
        """Boxen, Pakete und Microgreens des Kontos."""
        return await self._graphql(await self._id_token(), QUERY)

    async def mutate(self, name: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Eine der Änderungen aus MUTATIONS (Cloud-Modus). Liefert die Antwort des Servers."""
        return await self._graphql(await self._id_token(), MUTATIONS[name], variables)

    async def fetch_catalog(self) -> dict[str, Any]:
        """Pflanzenbibliothek (Rohdaten). Jeder Teil einzeln; nur Mixe und Pflanzen sind zwingend."""
        from .catalog_build import QUERIES, REQUIRED

        token = await self._id_token()
        raw: dict[str, Any] = {}
        for name, query in QUERIES.items():
            try:
                (raw[name],) = (await self._graphql(token, query)).values()
            except ApiError:
                if name in REQUIRED:
                    raise
                raw[name] = []
        return raw
