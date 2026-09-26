// Tests der Lovelace-Karte mit jsdom.   python tests/make_card_fixtures.py && cd tests/card && npm ci && npm test
const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");
const CARD = path.resolve(__dirname, "../../custom_components/greenbox/frontend/greenbox-garden-card.js");
const FIX = path.join(__dirname, "fixtures");
const dom = new JSDOM(`<!doctype html><body></body>`, { runScripts: "outside-only", pretendToBeVisual: true });
const { window } = dom;
window.eval(fs.readFileSync(CARD, "utf8"));
const rd = (f) => JSON.parse(fs.readFileSync(path.join(FIX, f), "utf8"));
const cat = rd("catalog.json"), catEmpty = rd("catalog_empty.json");
const stEmpty = rd("st_empty.json"), stPkg = rd("st_pkg.json"), stDouble = rd("st_double.json"), stCustom = rd("st_custom.json");
const MAC = stEmpty.attributes.box_key;
let fails = 0;
const ok = (c, m) => { console.log((c ? "  ok    " : "  FEHLT ") + m); if (!c) fails++; };
const tick = () => new Promise((r) => setTimeout(r, 0));

function make(state, cfg = {}, opts = {}) {
  const calls = [], ws = [];
  const el = window.document.createElement("greenbox-garden-card");
  window.document.body.appendChild(el);
  el.setConfig({ entity: "sensor.g", ...cfg });
  const hass = { language: opts.lang || "de", states: { "sensor.g": state },
    callWS: async (m) => { ws.push(m); return opts.catalog || cat; },
    callService: async (d, s, data) => { calls.push({ d, s, data }); if (opts.fail) throw new Error("Testfehler vom Server"); } };
  el.hass = hass;
  return { el, calls, ws, hass, $: (q) => el.shadowRoot.querySelector(q), $$: (q) => [...el.shadowRoot.querySelectorAll(q)] };
}
const setVal = (n, v) => { n.value = String(v); n.dispatchEvent(new window.Event("change", { bubbles: true })); };
async function open(t, kind, slot) { t.$(`.slot[data-kind="${kind}"][data-slot="${slot}"]`).click(); await tick(); await tick(); }
const optByText = (t, sel, text) => t.$$(`${sel} option`).find((o) => o.textContent === text).value;

(async () => {
  console.log("1) Nur Pflanzen: 4 x 2 runde Töpfchen wie in der App");
  let t = make(stEmpty);
  ok(t.$$(".slot.pot").length === 8 && t.$(".plblock.full") && !t.$(".mgblock"), "8 runde Töpfchen, kein Microgreens-Modul");
  ok(t.$$(".slot.pot .badge").map((e) => e.textContent).join(",") === "1,2,3,4,5,6,7,8", "Nummern 1-8");
  ok(t.$('button[data-action="addmicro"]') && t.$('button[data-action="addmicro"]').textContent.includes("Microgreens-Modul"), "Knopf zum Hinzufügen des Microgreens-Moduls");
  await open(t, "plant", 0);
  ok(t.$(".dialog h4").textContent.includes("Neues Paket") && t.ws[0].type === "greenbox/catalog", "Dialog 'Neues Paket', Katalog per Websocket geladen");
  const mixes = t.$$("#mix option").map((o) => o.textContent);
  ok(mixes.some((x) => x.includes("Test Herbs (15/20/15)")) && mixes.some((x) => x.includes("Eigener Zeitplan")) && !mixes.some((x) => x.includes("Hidden")), "Mixe mit Zeitplan, eigener Zeitplan, kein Cannabis");
  setVal(t.$("#mix"), 1);
  const plants = t.$$("#plant option").map((o) => o.textContent).filter((x) => !x.includes("bitte"));
  ok(plants.join(",") === "Basil,Cilantro,Thyme,Mint" && !t.$("#plantname"), "nur Pflanzen des Mixes, kein freies Namensfeld: " + plants.join(", "));
  t.$("button.primary").click(); await tick(); ok(t.calls.length === 0 && !t.$("#err").hidden, "ohne Pflanze: Fehlermeldung, kein Aufruf");
  setVal(t.$("#plant"), optByText(t, "#plant", "Cilantro")); setVal(t.$("#date"), "2026-09-25"); t.$("button.primary").click(); await tick();
  const c1 = t.calls[0];
  ok(c1 && c1.d === "greenbox" && c1.s === "plant_package" && c1.data.box === MAC && c1.data.mix === 1 && c1.data.planted_at === "2026-09-25" && c1.data.plants["1"] === 102, "plant_package: " + JSON.stringify(c1 && c1.data));
  ok(t.$("#dlg").innerHTML === "", "Dialog schließt sich nach Erfolg");

  console.log("2) Eigener Zeitplan mit frei getipptem Namen");
  t = make(stEmpty); await open(t, "plant", 4); setVal(t.$("#mix"), "custom");
  ok(!t.$("#custom").hidden && t.$("#plantname") && t.$$("#plant option").length >= 9, "Zeitplan-Felder, Namensfeld und alle Katalogpflanzen");
  setVal(t.$("#d0"), 5); setVal(t.$("#d1"), 10); setVal(t.$("#d2"), 7); setVal(t.$("#plantname"), " Erdbeere "); t.$("button.primary").click(); await tick();
  const c2 = t.calls[0];
  ok(c2.data.mix === undefined && c2.data.germination_days === 5 && c2.data.growth_days === 10 && c2.data.harvest_days === 7 && c2.data.plants["5"] === "Erdbeere", "getippter Name wird gesendet: " + JSON.stringify(c2.data));
  t = make(stEmpty); await open(t, "plant", 0); setVal(t.$("#mix"), "custom"); setVal(t.$("#plant"), optByText(t, "#plant", "My Pepper")); t.$("button.primary").click(); await tick();
  ok(t.calls[0].data.plants["1"] === 201, "oder eine Katalogpflanze aus der Liste");

  console.log("3) Ohne Katalog");
  t = make(stEmpty, {}, { catalog: catEmpty }); await open(t, "plant", 0);
  ok(t.$(".hint") && t.$(".hint").textContent.includes("update_catalog") && t.$("#mix").value === "custom" && !t.$("#custom").hidden && !t.$("#plant") && t.$("#plantname"), "Hinweis, 'Eigener Zeitplan' vorgewählt, nur Namensfeld");
  setVal(t.$("#plantname"), "Minze"); t.$("button.primary").click(); await tick();
  ok(t.calls[0].s === "plant_package" && t.calls[0].data.plants["1"] === "Minze" && t.calls[0].data.germination_days === 20, "plant_package mit freiem Namen und Standardzeiten");
  t = make(stEmpty, {}, { catalog: catEmpty }); t.$('button[data-action="addmicro"]').click(); await tick(); await tick();
  ok(t.$("#mgname") && t.$("#sd") && t.$("#gd") && !t.$("#plant"), "Microgreen ohne Katalog: Name und Zeiten selbst angeben");
  t.$("button.primary").click(); await tick(); ok(t.calls.length === 0 && !t.$("#err").hidden, "ohne Name: Fehlermeldung");
  setVal(t.$("#mgname"), "Erbse"); setVal(t.$("#sd"), 3); setVal(t.$("#gd"), 9); t.$("button.primary").click(); await tick();
  ok(t.calls[0].s === "plant_microgreen" && t.calls[0].data.microgreen === "Erbse" && t.calls[0].data.sprout_days === 3 && t.calls[0].data.growth_days === 9, "plant_microgreen mit Zeiten: " + JSON.stringify(t.calls[0].data));

  console.log("4) Microgreens-Modul hinzufügen (Knopf)");
  t = make(stEmpty); t.$('button[data-action="addmicro"]').click(); await tick(); await tick();
  ok(t.$("#mslot") && t.$$("#mslot option").length === 6 && t.$$("#plant option").length === 7, "Slot 1-6 wählbar, 6 Microgreens zur Auswahl");
  setVal(t.$("#mslot"), 3); setVal(t.$("#plant"), optByText(t, "#plant", "Arugula")); t.$("button.primary").click(); await tick();
  ok(t.calls[0].s === "plant_microgreen" && t.calls[0].data.slot === 3 && t.calls[0].data.microgreen === 1, "plant_microgreen Slot 3: " + JSON.stringify(t.calls[0].data));

  console.log("5) Mit Modul: links 3 x 2 eckige Felder, rechts 2 x 2 Töpfchen (Slots 1, 2, 5, 6)");
  t = make(stPkg);
  ok(t.$$(".mgblock .slot.sq").length === 6 && t.$$(".plblock .slot.pot").length === 4 && !t.$(".plblock.full"), "6 Felder + 4 Töpfchen");
  ok(t.$$(".plblock .badge").map((e) => e.textContent).join(",") === "1,2,5,6", "Töpfchen tragen die Nummern 1, 2, 5, 6 wie in der App");
  ok(!t.$('button[data-action="addmicro"]'), "kein Hinzufügen-Knopf, wenn das Modul schon da ist");
  ok(t.$$(".sq .plant").map((e) => e.textContent).slice(0, 3).join(",") === "Rucola,Kresse,", "Feld 1 = Rucola, Feld 2 = Kresse, Feld 3 leer (Namen in der Sprache der Oberfläche)");
  await open(t, "plant", 4);
  ok(!t.$("#mix") && t.$$("#plant option").length === 5 && !t.$("#plantname"), "Pflanz-Slot 5: nur Pflanzen des Mixes");
  setVal(t.$("#plant"), t.$$("#plant option")[3].value); t.$("button.primary").click(); await tick();
  ok(t.calls[0].s === "plant_slot" && t.calls[0].data.slot === 5 && t.calls[0].data.plant === 103, "plant_slot 5: " + JSON.stringify(t.calls[0].data));
  t = make(stPkg); await open(t, "plant", 0);
  ok(t.$("#plant").selectedOptions[0].textContent === "Basil" && t.$$("button").map((b) => b.textContent).join("|").includes("Slot leeren"), "belegter Topf: Pflanze vorgewählt, 'Slot leeren'");
  t.$('button[data-action="clear"]').click(); await tick(); ok(t.calls[0].s === "clear_slot" && t.calls[0].data.slot === 1, "clear_slot 1");
  t = make(stPkg); await open(t, "plant", 0); window.confirm = () => false; t.$('button[data-action="removepkg"]').click(); await tick();
  ok(t.calls.length === 0, "Paket entfernen: 'Abbrechen' -> nichts"); window.confirm = () => true; t.$('button[data-action="removepkg"]').click(); await tick(); ok(t.calls[0].s === "remove_package", "Paket entfernen nach Bestätigung");
  t = make(stPkg); await open(t, "micro", 0);
  ok(t.$("#plant").selectedOptions[0].textContent === "Arugula" && t.$('button[data-action="clear"]'), "Microgreen-Feld 1: Arugula vorgewählt, 'Leeren' vorhanden");
  t.$('button[data-action="clear"]').click(); await tick(); ok(t.calls[0].s === "clear_microgreen" && t.calls[0].data.slot === 1, "clear_microgreen 1");
  t = make(stPkg); await open(t, "micro", 4); setVal(t.$("#plant"), optByText(t, "#plant", "Mustard")); setVal(t.$("#date"), "2026-09-27"); t.$("button.primary").click(); await tick();
  ok(t.calls[0].s === "plant_microgreen" && t.calls[0].data.slot === 5 && t.calls[0].data.planted_on === "2026-09-27" && t.calls[0].data.microgreen === 3, "plant_microgreen Feld 5: " + JSON.stringify(t.calls[0].data));
  t = make(stCustom); await open(t, "plant", 3);
  ok(t.$("#plantname") && t.$("#plant"), "Paket mit eigenem Zeitplan: Namensfeld und Liste");
  setVal(t.$("#plantname"), "Gurke"); t.$("button.primary").click(); await tick(); ok(t.calls[0].s === "plant_slot" && t.calls[0].data.plant === "Gurke", "plant_slot mit freiem Namen");

  console.log("6) Zwei Module: getrennt, nur das erste bedienbar");
  t = make(stDouble);
  ok(t.$$(".mgblock").length === 2 && t.$(".board.stack") && t.$$(".plblock").length === 0, "zwei Blöcke untereinander, keine Pflanz-Töpfchen");
  ok(t.$$(".mgblock")[0].querySelector(".sq .plant").textContent === "Cress" && t.$$(".mgblock")[1].querySelector(".sq .plant").textContent === "Arugula", "keine Vermischung");
  ok(t.$$(".mgblock")[0].querySelectorAll(".editable").length === 6 && t.$$(".mgblock")[1].querySelectorAll(".editable").length === 0, "Modul 2 nur Anzeige");

  console.log("7) Optionen und Stile");
  t = make(stPkg, { microgreens: false }); ok(!t.$(".mgblock") && t.$$(".slot.pot").length === 8 && t.$(".plblock.full"), "microgreens: false -> Modul ausgeblendet");
  t = make(stPkg, { style: "tiles", columns: 3 }); ok(t.$$(".slot.pot").length === 0 && t.$$(".slot .bar").length === 14 && t.$(".grid").style.gridTemplateColumns.includes("repeat(3"), "style: tiles");
  t = make(stPkg, { style: "tiles", microgreen_slots: 3 }); ok(t.$$(".slot").length === 8 + 3, "tiles + microgreen_slots: 3");
  t = make({ state: "1", attributes: { ...stPkg.attributes, slots: stPkg.attributes.slots.map((x, i) => i === 0 ? { ...x, image: "https://example.com/x.jpg" } : x) } }, { show_images: true });
  ok(t.$(".pot .face img").getAttribute("src") === "https://example.com/x.jpg", "show_images: Foto rund im Topf");
  t = make({ state: "1", attributes: { ...stPkg.attributes, slots: stPkg.attributes.slots.map((x, i) => i === 0 ? { ...x, image: "/greenbox_photos/abc123.png" } : x) } }, { show_images: true });
  ok(t.$(".pot .face .glyph") && !t.$(".slot[data-slot=\"0\"] .face img") && t.$(".pot .face .glyph").getAttribute("style") === "--m:url('/greenbox_photos/abc123.png')",
    "lokales Bild: Maske in der Phasenfarbe statt <img> (auf hellem und dunklem Theme lesbar)");
  ok(/mask:\s*var\(--m\)/.test(t.el.shadowRoot.innerHTML) && /background:\s*var\(--c\)/.test(t.el.shadowRoot.innerHTML.replace(/\s+/g, " ")), "Stil färbt die Maske mit --c");
  t = make({ state: "1", attributes: { ...stPkg.attributes, slots: stPkg.attributes.slots.map((x, i) => i === 0 ? { ...x, image: "/greenbox_photos/\"><script>x</script>.png" } : x) } }, { show_images: true });
  ok(!t.$(".pot .face script"), "Bildadresse wird maskiert");
  const icons = make(stPkg).$$("ha-icon").map((e) => e.getAttribute("icon")); ok(icons.includes("mdi:seed-outline") && icons.includes("mdi:plus"), "Icons je Phase");
  t = make(stEmpty, { editable: false }); ok(t.$$(".editable").length === 0 && !t.$('button[data-action="addmicro"]'), "editable: false -> keine Bedienung");

  console.log("8) Fehler, Sicherheit, Aktualisierung");
  t = make(stPkg, {}, { fail: true }); await open(t, "plant", 4); setVal(t.$("#plant"), t.$$("#plant option")[1].value); t.$("button.primary").click(); await tick();
  ok(!t.$("#err").hidden && t.$("#err").textContent.includes("Testfehler vom Server") && t.$("#dlg").innerHTML !== "", "Serverfehler im Dialog, Dialog bleibt offen");
  t.$('button[data-action="cancel"]').click(); await tick(); ok(t.$("#dlg").innerHTML === "", "Abbrechen schließt");
  t = make({ ...stPkg, attributes: { ...stPkg.attributes, slots: stPkg.attributes.slots.map((x, i) => i === 0 ? { ...x, plant: "<b>x</b>" } : x) } });
  ok(t.$$("#card b").length === 0 && t.$$(".pot .plant")[0].textContent === "<b>x</b>", "HTML im Pflanzennamen wird als Text angezeigt");
  t = make({ ...stPkg, attributes: { ...stPkg.attributes, source: "cloud" } }); ok(t.$(".note") && t.$(".note").textContent.includes("Cloud"), "Hinweis bei Cloud-Stand");
  t.el.hass = { ...t.hass, states: { "sensor.g": stPkg } }; await tick(); ok(!t.$(".note"), "Hinweis verschwindet bei lokalem Stand");
  t = make(stPkg); await open(t, "plant", 4); const sel = t.$("#plant"); t.el.hass = { ...t.hass }; ok(t.$("#plant") === sel, "offener Dialog bleibt bei Zustandsupdate erhalten");
  t = make({ state: "2", attributes: { name: "Alt", slots: stPkg.attributes.slots, microgreens: stPkg.attributes.microgreens } }); ok(t.$$(".slot.pot").length === 8, "Sensor ohne 'mode' (älterer Stand): 8 Töpfchen, kein Absturz");
  const c3 = window.document.createElement("greenbox-garden-card"); c3.setConfig({ entity: "x" }); c3.hass = { language: "de", states: {} }; ok(c3.shadowRoot.innerHTML.includes("nicht gefunden"), "fehlende Entität");
  t = make(stEmpty, {}, { lang: "en" }); ok(t.$(".sub").textContent.includes("planted"), "englische Oberfläche");

  console.log("9) Visueller Editor");
  const Card = window.customElements.get("greenbox-garden-card");
  ok(window.customElements.get("greenbox-garden-card-editor") !== undefined && Card.getConfigElement().tagName.toLowerCase() === "greenbox-garden-card-editor", "Editor registriert, getConfigElement liefert ihn");
  ok(Card.getStubConfig({ states: { "light.a": { attributes: {} }, "sensor.greenbox_garten": { attributes: { box_key: "AA", slots: [] } } } }).entity === "sensor.greenbox_garten" && Card.getStubConfig(undefined).entity === "", "Standardkonfiguration wählt den ersten Garten-Sensor");
  window.customElements.define("ha-form", class extends window.HTMLElement {});
  const ed = window.document.createElement("greenbox-garden-card-editor"); window.document.body.appendChild(ed);
  const events = []; ed.addEventListener("config-changed", (e) => events.push(e.detail.config));
  ed.hass = { language: "de" }; ed.setConfig({ type: "custom:greenbox-garden-card", entity: "sensor.g", microgreens: false });
  const form = ed.querySelector("ha-form");
  ok(form.schema.map((f) => f.name).join(",") === "entity,style,microgreens,show_images,editable,columns,microgreen_slots", "Formular mit allen Optionen");
  const f0 = form.schema[0].selector.entity.filter[0];
  ok(form.schema[0].required && f0.integration === "greenbox" && f0.domain === "sensor", "Auswahl nur für Garten-Sensoren der Integration");
  ok(form.data.entity === "sensor.g" && form.data.microgreens === "false" && form.data.style === "app" && form.data.editable === true, "Formular zeigt Konfiguration mit Voreinstellungen");
  const fire = (value) => form.dispatchEvent(new window.CustomEvent("value-changed", { detail: { value }, bubbles: true }));
  fire({ ...form.data, style: "tiles", columns: 3 });
  ok(events[0].style === "tiles" && events[0].columns === 3 && events[0].type === "custom:greenbox-garden-card" && events[0].microgreens === false, "Änderung sendet config-changed, 'false' wird echtes false");
  fire({ ...form.data, style: "app", columns: 4, microgreens: "auto", editable: true, show_images: false });
  const last = events[events.length - 1]; ok(last.style === undefined && last.columns === undefined && last.microgreens === undefined && last.entity === "sensor.g", "Voreinstellungen landen nicht in der YAML");
  fire({ ...form.data, microgreen_slots: "" }); ok(events[events.length - 1].microgreen_slots === undefined, "leeres Zahlenfeld entfernt die Option");
  ed.hass = { language: "en" }; ok(form.computeLabel({ name: "entity" }) === "Garden sensor of the box", "englische Beschriftungen");
  console.log(fails ? `\n${fails} FEHLER` : "\nalle Card-Tests ok");
  process.exit(fails ? 1 : 0);
})();
