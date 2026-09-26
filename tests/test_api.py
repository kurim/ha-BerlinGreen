"""Cloud-Zugriff: Änderungen (Cloud-Modus) gegen einen Ersatz-Server.   python tests/test_api.py"""
import asyncio
import base64
import importlib
import json
import re
import sys

import _stubs

_stubs.install()
_stubs.package(with_init=False)
api = importlib.import_module("greenbox.api")
fails = 0


def check(cond, msg):
    global fails
    print(("  ok    " if cond else "  FEHLT ") + msg)
    fails += not cond


def token() -> str:
    part = base64.urlsafe_b64encode(json.dumps({api.CLAIMS: {"x-hasura-user-id": "u"}}).encode()).decode().rstrip("=")
    return f"h.{part}.s"


class Resp:
    def __init__(self, status, body): self.status, self._body = status, body
    async def text(self): return self._body
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


class Session:
    def __init__(self, graphql): self.graphql, self.calls = graphql, []
    def post(self, url, json=None, data=None, headers=None, timeout=None):
        self.calls.append((url, json, data, headers))
        if url.startswith("https://securetoken"):
            return Resp(200, globals()["json"].dumps({"id_token": token(), "refresh_token": "NEW"}))
        return Resp(200, globals()["json"].dumps(self.graphql(json)))


async def main():
    print("Änderungen")
    for name, query in api.MUTATIONS.items():
        declared = set(re.findall(r"\\$(\\w+):", query.split(")")[0]))
        used = set(re.findall(r"\\$(\\w+)", query.split(")", 1)[1]))
        check(query.count("{") == query.count("}") and query.strip().startswith("mutation") and declared == used, f"{name}: ausgeglichen, alle Variablen deklariert und benutzt")
    session = Session(lambda body: {"data": {"insert_package": {"affected_rows": 1}}})
    cloud = api.GreenboxCloud(session, "REFRESH", "AIza" + "x" * 35)
    res = await cloud.mutate("insert_slot", {"packageId": 7, "slot": 1, "plantId": 103})
    url, body, _, headers = session.calls[-1]
    check(res == {"insert_package": {"affected_rows": 1}} and url == api.GRAPHQL and body["variables"] == {"packageId": 7, "slot": 1, "plantId": 103}
          and "insert_planted" in body["query"] and headers["Authorization"] == "Bearer " + token() and cloud.refresh_token == "NEW",
          "Änderung mit Variablen und Bearer-Token an die GraphQL-Adresse")
    await cloud.fetch()
    check("variables" not in session.calls[-1][1], "Abfragen ohne Variablen bleiben wie bisher")
    bad = api.GreenboxCloud(Session(lambda body: {"errors": [{"message": "permission denied"}]}), "R", "AIza" + "x" * 35)
    try:
        await bad.mutate("delete_module", {"id": "x"})
        check(False, "GraphQL-Fehler werden gemeldet")
    except api.ApiError as err:
        check("permission denied" in str(err), "GraphQL-Fehler werden als ApiError gemeldet")


asyncio.run(main())
print("\n" + ("%d FEHLER" % fails if fails else "alle Tests ok"))
sys.exit(1 if fails else 0)
