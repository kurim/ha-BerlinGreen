"""Metadaten wie hassfest/HACS sie prüfen (ohne Netz): Manifest, Dienste, Übersetzungen, HACS-Datei, keine persönlichen Daten.   python tests/test_metadata.py"""
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # PyYAML ist in Home Assistant enthalten, für den Test aber optional
    yaml = None

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "custom_components" / "greenbox"
fails = 0


def check(cond, msg):
    global fails
    print(("  ok    " if cond else "  FEHLT ") + msg)
    fails += not cond


def keys(d, prefix=""):
    out = set()
    for k, v in d.items():
        out |= keys(v, f"{prefix}{k}.") if isinstance(v, dict) else {f"{prefix}{k}"}
    return out


m = json.loads((PKG / "manifest.json").read_text())
order = list(m)
check(order[:2] == ["domain", "name"] and order[2:] == sorted(order[2:]), "manifest.json: domain, name, dann alphabetisch (hassfest)")
need = {"domain", "name", "codeowners", "config_flow", "documentation", "iot_class", "issue_tracker", "requirements", "version", "integration_type"}
check(need <= set(m) and m["domain"] == "greenbox" and re.fullmatch(r"\d+\.\d+\.\d+", m["version"]), "Pflichtfelder und Versionsnummer")
check(all(c.startswith("@") for c in m["codeowners"]) and m["documentation"].startswith("https://github.com/") and m["issue_tracker"].endswith("/issues"), "Codeowner, Dokumentation, Issue-Tracker")
hacs = json.loads((ROOT / "hacs.json").read_text())
check(hacs.get("name") and hacs.get("homeassistant"), "hacs.json")
changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
check(f"## [{m['version']}]" in changelog, f"CHANGELOG.md hat einen Abschnitt für {m['version']}")
check((ROOT / "LICENSE").read_text().startswith("MIT License") and [l for l in (ROOT / "CODEOWNERS").read_text().splitlines() if l.strip() and not l.startswith("#")][0].split()[0] == "*", "LICENSE (MIT) und CODEOWNERS")
check(all((PKG / "brand" / f).is_file() for f in ("icon.png", "icon@2x.png", "logo.png", "logo@2x.png")), "Brand-Bilder")

en = json.loads((PKG / "translations" / "en.json").read_text(encoding="utf-8"))
de = json.loads((PKG / "translations" / "de.json").read_text(encoding="utf-8"))
check(keys(en) == keys(de), "Deutsch und Englisch haben dieselben Schlüssel" + ("" if keys(en) == keys(de) else f": {sorted(keys(en) ^ keys(de))[:6]}"))

def strings(d):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from ((f"{k}.{kk}", vv) for kk, vv in strings(v))
        elif isinstance(v, str):
            yield k, v


bad = [(lang, k, v) for lang, tr in (("en", en), ("de", de)) for k, v in strings(tr)
       if any(not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", x) for x in re.findall(r"\{([^{}]*)\}", v)) or v.count("{") != v.count("}")]
check(not bad, "Platzhalter in den Übersetzungen sind gültige Namen (hassfest)" + (f": {bad[:3]}" if bad else ""))

code = {p.name: p.read_text(encoding="utf-8") for p in PKG.glob("*.py")}
init = code["__init__.py"]
services_in_code = set(re.findall(r'^\s{4}"(\w+)": vol\.Schema', init, re.M))
if yaml:
    services_yaml = set(yaml.safe_load((PKG / "services.yaml").read_text()))
else:
    services_yaml = set(re.findall(r"^(\w+):", (PKG / "services.yaml").read_text(), re.M))
check(services_in_code == services_yaml == set(en["services"]) and len(services_in_code) == 8, f"Dienste stimmen überein (Code, services.yaml, Übersetzung): {sorted(services_in_code)}")
fields_ok = True
if yaml:
    sy = yaml.safe_load((PKG / "services.yaml").read_text())
    for name, spec in sy.items():
        f_yaml = set((spec or {}).get("fields") or {})
        f_tr = set(en["services"][name].get("fields", {}))
        if f_yaml != f_tr:
            fields_ok = False
            print(f"        {name}: services.yaml {sorted(f_yaml)} != Übersetzung {sorted(f_tr)}")
    check(fields_ok, "Felder der Dienste in services.yaml und Übersetzungen gleich")

used = {}
for fname, text in code.items():
    platform = fname[:-3]
    for key in re.findall(r'_attr_translation_key\s*=\s*"(\w+)"', text):
        used.setdefault(platform, set()).add(key)
    for key in re.findall(r'_attr_translation_key\s*=\s*f"(\w+?)\{', text):
        used.setdefault(platform, set()).add(key + "*")
missing = []
platform_of = {"garden_sensor": "sensor"}
for platform, ks in used.items():
    pl = platform_of.get(platform, platform)
    for k in ks:
        if k.endswith("*"):
            continue
        if k not in en["entity"].get(pl, {}):
            missing.append(f"{pl}.{k}")
check(not missing, "alle translation_key des Codes stehen in den Übersetzungen" + (f": fehlt {missing}" if missing else ""))
sensor_keys = {"garden", "slot", "microgreen", "water_level", "water_status", "firmware", "hardware"}
check(sensor_keys <= set(en["entity"]["sensor"]), "Sensor-Übersetzungen vollständig")

steps = set(en["config"]["step"])
flow = code["config_flow.py"]
flow_steps = set(re.findall(r'step_id="(\w+)"', flow))
check(flow_steps - {"init"} <= steps and "init" in en["options"]["step"], "alle Schritte des Einrichtungs- und Optionsablaufs sind übersetzt")
aborts = set(re.findall(r'(?:reason="|abort\(reason=")(\w+)', flow)) | {"already_configured"}
check(aborts <= set(en["config"]["abort"]), "alle Abbruchgründe sind übersetzt" + (f": fehlt {sorted(aborts - set(en['config']['abort']))}" if not aborts <= set(en['config']['abort']) else ""))

# HACS zeigt die README in Home Assistant an: relative Links und Bilder laufen dort ins Leere
rel = [(f, m_) for f in ("README.md", "README.de.md") for m_ in re.findall(r"\]\((?!https?://|#|mailto:)([^)\s]+)\)", (ROOT / f).read_text(encoding="utf-8"))]
check(not rel, "README-Links sind absolut (HACS-Anzeige)" + (f": {rel[:3]}" if rel else ""))

# nichts Persönliches und keine Herstellerdaten im Repo
personal = re.compile(r"8C:4B:14|2109B82B|332824A8|netge4r|/home/kurim|C:\\Users|\\\\wsl", re.I)
offenders = []
for p in ROOT.rglob("*"):
    if not p.is_file() or any(x in p.parts for x in ("_alt", ".git", "node_modules", "__pycache__")) or p.suffix in (".png", ".lock"):
        continue
    if p.name in ("test_metadata.py", "package-lock.json"):
        continue
    if personal.search(p.read_text(encoding="utf-8", errors="ignore")):
        offenders.append(str(p.relative_to(ROOT)))
check(not offenders, "keine persönlichen Kennungen im Repo" + (f": {offenders}" if offenders else ""))
key_pat = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
keys_found = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
              if p.is_file() and not any(x in p.parts for x in ("_alt", ".git", "node_modules", "__pycache__")) and p.suffix not in (".png", ".lock")
              and key_pat.search(p.read_text(encoding="utf-8", errors="ignore"))]
check(not keys_found, "kein Google-API-Schlüssel im Repo (Secret-Scanning)" + (f": {keys_found}" if keys_found else ""))
check(not (PKG / "catalog.json").exists() and not list(ROOT.glob("**/cloud_dump.json")), "kein Herstellerkatalog und keine Kontodaten im Repo")
check(not any(p.suffix == ".xapk" for p in ROOT.rglob("*") if "_alt" not in p.parts), "keine Hersteller-App im Repo")
if yaml:
    class Loader(yaml.SafeLoader):
        pass

    Loader.add_constructor("!input", lambda loader, node: ("input", loader.construct_scalar(node)))
    hub_src = (PKG / "hub.py").read_text(encoding="utf-8")
    for bp in sorted((ROOT / "blueprints" / "automation" / "greenbox").glob("*.yaml")):
        doc = yaml.load(bp.read_text(encoding="utf-8"), Loader=Loader)
        meta = doc["blueprint"]
        used = set(re.findall(r"!input (\w+)", bp.read_text(encoding="utf-8")))
        check(meta["domain"] == "automation" and meta["source_url"].endswith(f"blueprints/automation/greenbox/{bp.name}") and used <= set(meta["input"]) and doc["triggers"] and doc["actions"],
              f"Blueprint {bp.name}: Kopf, source_url, alle !input-Verweise definiert")
        event = next((t.get("event_type") for t in doc["triggers"] if t.get("trigger") == "event"), None)
        check(event is None or f'"{event}"' in hub_src, f"Blueprint {bp.name}: Ereignisname gibt es im Code")
print("\n" + ("%d FEHLER" % fails if fails else "alle Tests ok"))
sys.exit(1 if fails else 0)
