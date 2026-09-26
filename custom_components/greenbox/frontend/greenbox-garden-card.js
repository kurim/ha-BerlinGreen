/* GreenBox Garden Card - zeigt die Box wie die App: runde Töpfchen für Pflanzen, eckige Felder für das Microgreens-Modul.
 * Slot antippen zum Bepflanzen.
 * Konfiguration (YAML):
 *   type: custom:greenbox-garden-card
 *   entity: sensor.salatbox_garten        # der "Garten"-Sensor der Box (auch im visuellen Editor wählbar)
 *   show_images: false                    # optional: Pflanzenbilder statt Icons (nach „Katalog aktualisieren“ lokal gespeichert, in der Phasenfarbe gefärbt)
 *   microgreens: auto                     # auto | false (Microgreens-Modul ausblenden)
 *   editable: true                        # false = nur anzeigen
 *   style: app                            # app (wie die App) | tiles (einfache Kacheln, dann gilt columns)
 *   columns: 4                            # nur für style: tiles
 */
const PHASE = {
  empty:       { label: { de: "Leer", en: "Empty" },            color: "var(--disabled-color, #9e9e9e)" },
  germination: { label: { de: "Keimung", en: "Germination" },   color: "#f9a825" },
  growth:      { label: { de: "Wachstum", en: "Growth" },       color: "#43a047" },
  harvest:     { label: { de: "Ernte", en: "Harvest" },         color: "#e53935" },
  complete:    { label: { de: "Abgeschlossen", en: "Complete" }, color: "#607d8b" },
};

const ICON = { empty: "mdi:plus", germination: "mdi:seed-outline", growth: "mdi:sprout", harvest: "mdi:basket-outline", complete: "mdi:check-circle-outline" };

const T = {
  de: { newPackage: "Neues Paket pflanzen", plant: "Pflanze", mix: "Mix", custom: "Eigener Zeitplan", date: "Pflanzdatum",
        germ: "Keimung (Tage)", growth: "Wachstum (Tage)", harvest: "Ernte (Tage)", save: "Pflanzen", cancel: "Abbrechen",
        change: "Ändern", clear: "Slot leeren", removePkg: "Paket entfernen", confirmPkg: "Das ganze Paket wirklich entfernen?",
        slot: "Slot", micro: "Microgreens", module: "Modul", microOne: "Microgreen", loading: "Lade Katalog ...", err: "Fehler", choose: "– bitte wählen –",
        cloudNote: "Stand aus der Cloud – eine Änderung übernimmt ihn lokal.", plantName: "Pflanzenname", orName: "oder eigener Name", mgName: "Name", sproutDays: "Keimzeit (Tage)", growthMg: "Tage bis zur Ernte",
        noCatalog: "Kein Katalog geladen: Cloud-Konto verbinden (Dienst greenbox.update_catalog) oder Datei greenbox_catalog.json ablegen. Bis dahin geht \"Eigener Zeitplan\" mit frei getipptem Namen.", planted: "belegt", ready: "erntereif",
        readyShort: "erntereif", finished: "Zyklus beendet", harvestIn: (n) => `Ernte in ${n} T`, notFound: "nicht gefunden" },
  en: { newPackage: "Plant new package", plant: "Plant", mix: "Mix", custom: "Custom schedule", date: "Planting date",
        germ: "Germination (days)", growth: "Growth (days)", harvest: "Harvest (days)", save: "Plant", cancel: "Cancel",
        change: "Change", clear: "Empty slot", removePkg: "Remove package", confirmPkg: "Really remove the whole package?",
        slot: "Slot", micro: "Microgreens", module: "Modul", microOne: "Microgreen", loading: "Loading catalog ...", err: "Error", choose: "– please choose –",
        cloudNote: "State from the cloud – a change takes it over locally.", plantName: "Plant name", orName: "or a custom name", mgName: "Name", sproutDays: "Germination (days)", growthMg: "Days until harvest",
        noCatalog: "No catalog loaded: connect the cloud account (service greenbox.update_catalog) or add the file greenbox_catalog.json. Until then use \"Custom schedule\" with a typed name.", planted: "planted", ready: "ready",
        readyShort: "ready", finished: "cycle finished", harvestIn: (n) => `harvest in ${n} d`, notFound: "not found" },
};

class GreenboxGardenCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error("entity fehlt");
    this._config = { columns: 4, show_images: false, microgreens: "auto", editable: true, style: "app", ...config };
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.innerHTML = `<style>${GreenboxGardenCard.css}</style><div id="card"></div><div id="dlg"></div>`;
      this.shadowRoot.getElementById("card").addEventListener("click", (ev) => this._onClick(ev));
    }
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() { return 4; }

  static getConfigElement() { return document.createElement("greenbox-garden-card-editor"); }

  static getStubConfig(hass) {
    // erste Box vorschlagen: der "Garten"-Sensor trägt die Attribute box_key und slots
    const id = hass && Object.keys(hass.states).find((k) => k.startsWith("sensor.") && hass.states[k].attributes && hass.states[k].attributes.box_key && hass.states[k].attributes.slots);
    return { entity: id || "" };
  }

  get _de() { return ((this._hass && this._hass.language) || "en").startsWith("de"); }
  get _t() { return T[this._de ? "de" : "en"]; }
  _label(map) { return map[this._de ? "de" : "en"]; }

  _daysText(s) {
    const fmt = (n) => (Math.round(n * 10) / 10).toString().replace(".", this._de ? "," : ".");
    if (s.phase === "empty") return "";
    if (s.phase === "harvest") return this._t.readyShort;
    if (s.phase === "complete") return this._t.finished;
    return this._t.harvestIn(fmt(s.days_to_harvest));
  }

  _progress(s) {
    const total = (s.germination_days || 0) + (s.growth_days || 0);
    if (!total) return s.phase === "harvest" || s.phase === "complete" ? 100 : 0;
    return Math.max(0, Math.min(100, (s.days_elapsed / total) * 100));
  }

  // Lokale Fotos (Strichzeichnung als PNG mit Transparenz) dienen als Maske und werden in der Phasenfarbe gefärbt -> auf hellen
  // und dunklen Themes lesbar. Fremde Adressen (Fallback) bleiben normale Bilder.
  _photo(url) {
    if (url.startsWith("/greenbox_photos/")) return `<span class="glyph" style="--m:url('${this._esc(url)}')"></span>`;
    return `<img src="${this._esc(url)}" alt="">`;
  }

  _cell(s, kind, shape, editableSlot = true) {
    const p = PHASE[s.phase] || PHASE.empty;
    const icon = `<ha-icon icon="${ICON[s.phase] || ICON.empty}"></ha-icon>`;
    const img = this._config.show_images && s.image ? this._photo(s.image) : "";
    const name = s.plant ? this._esc(s.plant) : (shape === "tile" ? "—" : "");
    const edit = this._config.editable && editableSlot ? ` data-kind="${kind}" data-slot="${s.slot}" tabindex="0" role="button"` : "";
    const cls = `slot ${shape}${this._config.editable && editableSlot ? " editable" : ""}`;
    const style = `--c:${p.color};--p:${Math.round(this._progress(s))}`;
    const title = ` title="${this._esc(s.plant || "")}"`;
    if (shape === "pot") {
      return `<div class="${cls}" style="${style}"${title}${edit}>
        <div class="ring"><div class="face">${img || icon}</div><span class="badge">${s.slot + 1}</span></div>
        <div class="plant">${name}</div><div class="phase">${this._label(p.label)}</div><div class="days">${this._daysText(s)}</div></div>`;
    }
    if (shape === "sq") {
      return `<div class="${cls}" style="${style}"${title}${edit}>
        <div class="box">${img || `<span class="n">${s.slot + 1}</span>`}</div>
        <div class="plant">${s.plant ? name : ""}</div><div class="days">${s.phase === "empty" ? "" : this._label(p.label)} ${this._daysText(s)}</div></div>`;
    }
    return `<div class="${cls}" style="${style}"${title}${edit}>
      <div class="num">${s.slot + 1}</div>${img}
      <div class="plant">${name}</div><div class="phase">${icon} ${this._label(p.label)}</div>
      <div class="days">${this._daysText(s)}</div><div class="bar"><span style="width:${this._progress(s)}%"></span></div></div>`;
  }

  _cells(slots, kind) {
    const limit = kind === "micro" && Number(this._config.microgreen_slots) > 0 ? Number(this._config.microgreen_slots) : null;
    return (limit ? slots.slice(0, limit) : slots).map((s) => this._cell(s, kind, "tile")).join("");
  }

  _section(title, planted, ready, cells) {
    const t = this._t;
    const sub = `${planted} ${t.planted}${ready ? ` · ${ready} ${t.ready}` : ""}`;
    return `<div class="head"><span class="title">${this._esc(title)}</span><span class="sub">${sub}</span></div>
      <div class="grid" style="grid-template-columns: repeat(${Number(this._config.columns) || 4}, 1fr)">${cells}</div>`;
  }

  _render() {
    if (!this._config || !this._hass) return;
    const st = this._hass.states[this._config.entity];
    const card = this.shadowRoot.getElementById("card");
    if (!st) {
      card.innerHTML = `<ha-card><div style="padding:16px">Entität ${this._esc(this._config.entity)} nicht gefunden</div></ha-card>`;
      return;
    }
    const a = st.attributes;
    const t = this._t;
    const note = a.source === "cloud" && this._config.editable ? `<div class="note">${t.cloudNote}</div>` : "";
    const ready = (a.harvest_ready || 0) + (a.microgreens_ready || 0);
    const count = (Number(st.state) || 0) + (a.microgreens_planted || 0);
    const head = `<div class="head"><span class="title">${this._esc(a.name || a.friendly_name || "")}</span>
      <span class="sub">${count} ${t.planted}${ready ? ` · ${ready} ${t.ready}` : ""}</span></div>`;
    if (this._config.style === "tiles") {
      const micro = a.microgreens || [];
      const m = this._config.microgreens;
      const showMicro = m !== false && m !== "false" && micro.some((x) => x.phase !== "empty");
      const grid = (cells) => `<div class="grid" style="grid-template-columns: repeat(${Number(this._config.columns) || 4}, 1fr)">${cells}</div>`;
      card.innerHTML = `<ha-card>${head}${grid(this._cells(a.slots || [], "plant"))}${showMicro ? `<div class="head"><span class="title">Microgreens</span></div>${grid(this._cells(micro, "micro"))}` : ""}${note}</ha-card>`;
      return;
    }
    // App-Layout: ohne Modul 4 x 2 runde Töpfchen; mit Modul links das Microgreens-Modul (3 x 2 Felder), rechts 2 x 2 Töpfchen
    const slots = a.slots || [];
    const modules = a.microgreen_modules || (a.microgreens ? [a.microgreens] : []);
    const hasModule = a.mode === "mixed" || a.mode === "double";
    const hide = this._config.microgreens === false || this._config.microgreens === "false";
    const ids = hasModule && !hide && a.plant_slot_ids ? a.plant_slot_ids : slots.map((x) => x.slot);
    const pots = slots.filter((x) => ids.includes(x.slot)).map((x) => this._cell(x, "plant", "pot")).join("");
    let board;
    if (hasModule && !hide) {
      const blocks = modules.map((mod, i) => `<div class="mgblock">${mod.map((x) => this._cell(x, "micro", "sq", i === 0)).join("")}</div>`).join("");
      // DoubleMicrogreens: zwei Module, keine Pflanz-Töpfchen -> Module untereinander
      board = a.mode === "double" ? `<div class="board stack">${blocks}</div>` : `<div class="board">${blocks}<div class="plblock">${pots}</div></div>`;
    } else {
      board = `<div class="board"><div class="plblock full">${pots}</div></div>`;
    }
    const addMicro = !hasModule && !hide && this._config.editable && a.mode !== "mushroom"
      ? `<div class="add"><button data-action="addmicro">+ ${t.micro}-${t.module}</button></div>` : "";
    card.setAttribute("lang", this._de ? "de" : "en");
    card.innerHTML = `<ha-card>${head}${board}${addMicro}${note}</ha-card>`;
    const btn = card.querySelector('button[data-action="addmicro"]');
    if (btn) btn.addEventListener("click", () => this._open("micro", 0));
  }

  // ---------- Bedienung ----------
  _onClick(ev) {
    const el = ev.target.closest(".slot.editable");
    if (!el) return;
    this._open(el.dataset.kind, Number(el.dataset.slot));
  }

  async _catalog() {
    if (!this._cat) this._cat = await this._hass.callWS({ type: "greenbox/catalog" });
    return this._cat;
  }

  async _open(kind, slot) {
    const dlg = this.shadowRoot.getElementById("dlg");
    dlg.innerHTML = this._modal(`<p>${this._t.loading}</p>`);
    let cat;
    try { cat = await this._catalog(); } catch (e) { dlg.innerHTML = this._modal(`<p class="error">${this._esc(e.message || e)}</p>${this._btn("cancel", this._t.cancel)}`); this._wire(); return; }
    const a = this._hass.states[this._config.entity].attributes;
    const t = this._t;
    const list = kind === "plant" ? a.slots : a.microgreens;
    const cur = (list || []).find((s) => s.slot === slot) || {};
    const filled = cur.phase && cur.phase !== "empty";
    const today = new Date().toISOString().slice(0, 10);
    let body = `<h3>${kind === "plant" ? t.slot : t.microOne} ${slot + 1}${cur.plant ? ` – ${this._esc(cur.plant)}` : ""}</h3>`;
    this._ctx = { kind, slot };
    if (kind === "micro") {
      const slotOpts = Array.from({ length: (list || []).length || 6 }, (_, i) => `<option value="${i + 1}"${i === slot ? " selected" : ""}>${i + 1}</option>`).join("");
      const pick = cat.microgreens.length
        ? this._field(t.microOne, this._select("plant", cat.microgreens, cur.plant_id))
        : `<p class="hint">${t.noCatalog}</p>` + this._field(t.mgName, `<input id="mgname" type="text">`) + this._field(t.sproutDays, `<input id="sd" type="number" min="0" value="2">`) + this._field(t.growthMg, `<input id="gd" type="number" min="0" value="8">`);
      body += this._field(t.slot, `<select id="mslot">${slotOpts}</select>`) + pick + this._field(t.date, `<input id="date" type="date" value="${today}">`);
      body += `<div class="btns">${this._btn("save", filled ? t.change : t.save)}${filled ? this._btn("clear", t.clear) : ""}${this._btn("cancel", t.cancel)}</div>`;
    } else if (!a.has_package) {
      const first = cat.mixes.find((m) => !m.own) || cat.mixes[0];
      body += `<h4>${t.newPackage}</h4>${cat.empty ? `<p class="hint">${t.noCatalog}</p>` : ""}` + this._field(t.mix, this._select("mix", [...cat.mixes.map((m) => ({ ...m, name: `${m.name} (${m.schedule.join("/")})` })), { id: "custom", name: t.custom }], first ? first.id : "custom"));
      body += `<div id="custom" hidden>${this._field(t.germ, `<input id="d0" type="number" min="0" value="20">`)}${this._field(t.growth, `<input id="d1" type="number" min="0" value="20">`)}${this._field(t.harvest, `<input id="d2" type="number" min="0" value="20">`)}</div>`;
      body += `<div id="plantpick"></div>` + this._field(t.date, `<input id="date" type="date" value="${today}">`);
      body += `<div class="btns">${this._btn("save", t.save)}${this._btn("cancel", t.cancel)}</div>`;
    } else {
      body += `<div id="plantpick"></div>`;
      body += `<div class="btns">${this._btn("save", filled ? t.change : t.save)}${filled ? this._btn("clear", t.clear) : ""}${this._btn("removepkg", t.removePkg)}${this._btn("cancel", t.cancel)}</div>`;
    }
    body += `<p class="error" id="err" hidden></p>`;
    dlg.innerHTML = this._modal(body);
    this._cat = cat;
    this._ctx = { kind, slot, cur, hasPackage: a.has_package, mixId: a.mix_id, box: a.box_key };
    if (kind === "plant") {
      const mixSel = this.shadowRoot.getElementById("mix");
      if (mixSel) mixSel.addEventListener("change", () => this._fillPlants());
      this._fillPlants();
    }
    this._wire();
  }

  _fillPlants() {
    const cat = this._cat, ctx = this._ctx, t = this._t;
    const mixSel = this.shadowRoot.getElementById("mix");
    let mix = null, custom = false;
    if (mixSel) {
      custom = mixSel.value === "custom";
      mix = custom ? null : cat.mixes.find((m) => String(m.id) === mixSel.value);
      this.shadowRoot.getElementById("custom").hidden = !custom;
    } else if (ctx.mixId != null) {
      mix = cat.mixes.find((m) => m.id === ctx.mixId);
    }
    const plants = mix && !mix.own ? mix.plants : cat.plants;
    // frei getippte Namen erlaubt der Server nur bei eigenem Zeitplan (Paket ohne Mix)
    const freeText = custom || (!mixSel && ctx.mixId == null);
    const pick = plants.length ? this._field(t.plant, this._select("plant", plants, ctx.cur && ctx.cur.plant_id)) : "";
    const free = freeText ? this._field(plants.length ? t.orName : t.plantName, `<input id="plantname" type="text" value="${this._esc((ctx.cur && ctx.mixId == null && ctx.cur.plant) || "")}">`) : "";
    this.shadowRoot.getElementById("plantpick").innerHTML = pick + free;
  }

  _select(id, items, selected) {
    const opts = items.map((i) => `<option value="${this._esc(i.id)}"${String(i.id) === String(selected) ? " selected" : ""}>${this._esc(i.name)}</option>`).join("");
    return `<select id="${id}"><option value="">${this._t.choose}</option>${opts}</select>`;
  }

  _field(label, control) { return `<label class="field"><span>${this._esc(label)}</span>${control}</label>`; }
  _btn(action, text) { return `<button data-action="${action}" class="${action === "save" ? "primary" : ""}">${this._esc(text)}</button>`; }
  _modal(inner) { return `<div class="overlay"><div class="dialog">${inner}</div></div>`; }

  _wire() {
    const dlg = this.shadowRoot.getElementById("dlg");
    dlg.querySelector(".overlay").addEventListener("click", (ev) => { if (ev.target.classList.contains("overlay")) this._close(); });
    dlg.querySelectorAll("button[data-action]").forEach((b) => b.addEventListener("click", () => this._action(b.dataset.action)));
  }

  _close() { this.shadowRoot.getElementById("dlg").innerHTML = ""; this._ctx = null; }

  _error(msg) {
    const e = this.shadowRoot.getElementById("err");
    if (e) { e.textContent = msg; e.hidden = false; }
  }

  async _call(service, data) {
    try {
      await this._hass.callService("greenbox", service, { box: this._ctx.box, ...data });
      this._close();
    } catch (err) {
      this._error(`${this._t.err}: ${(err && err.message) || err}`);
    }
  }

  _val(id) { const el = this.shadowRoot.getElementById(id); return el ? el.value : ""; }

  async _action(action) {
    const ctx = this._ctx;
    if (!ctx) return;
    if (action === "cancel") return this._close();
    const slot = ctx.slot + 1;
    if (action === "clear") return this._call(ctx.kind === "micro" ? "clear_microgreen" : "clear_slot", { slot });
    if (action === "removepkg") {
      if (!window.confirm(this._t.confirmPkg)) return;
      return this._call("remove_package", {});
    }
    // save
    const date = this._val("date");
    if (ctx.kind === "micro") {
      const mslot = Number(this._val("mslot")) || slot;
      const typed = this._val("mgname").trim();
      if (this.shadowRoot.getElementById("mgname")) {   // ohne Katalog: Name und Zeiten selbst angeben
        if (!typed) return this._error(`${this._t.mgName}: ${this._t.choose}`);
        return this._call("plant_microgreen", { slot: mslot, microgreen: typed, sprout_days: Number(this._val("sd")), growth_days: Number(this._val("gd")), ...(date ? { planted_on: date } : {}) });
      }
      const mg = this._val("plant");
      if (!mg) return this._error(`${this._t.microOne}: ${this._t.choose}`);
      return this._call("plant_microgreen", { slot: mslot, microgreen: Number(mg), ...(date ? { planted_on: date } : {}) });
    }
    const typedPlant = this._val("plantname").trim();
    const picked = this._val("plant");
    const plant = typedPlant || (picked ? Number(picked) : "");
    if (plant === "") return this._error(`${this._t.plant}: ${this._t.choose}`);
    if (ctx.hasPackage) return this._call("plant_slot", { slot, plant });
    const mix = this._val("mix");
    if (!mix) return this._error(`${this._t.mix}: ${this._t.choose}`);
    const data = { plants: { [slot]: plant }, ...(date ? { planted_at: date } : {}) };
    if (mix === "custom") Object.assign(data, { germination_days: Number(this._val("d0")), growth_days: Number(this._val("d1")), harvest_days: Number(this._val("d2")) });
    else data.mix = Number(mix);
    return this._call("plant_package", data);
  }

  _esc(v) {
    return String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
}

GreenboxGardenCard.css = `
  .head { padding: 12px 16px 0; display: flex; justify-content: space-between; align-items: baseline; }
  .title { font-size: 1.1em; font-weight: 500; }
  .sub { color: var(--secondary-text-color); font-size: .85em; }
  .note { padding: 0 16px 12px; color: var(--secondary-text-color); font-size: .8em; }
  .grid { display: grid; gap: 8px; padding: 12px 16px 16px; }
  .slot { border: 1px solid var(--divider-color); border-left: 4px solid var(--c); border-radius: 8px; padding: 8px; min-width: 0; position: relative; }
  .slot.editable { cursor: pointer; }
  .slot.editable:hover { background: var(--secondary-background-color); }
  .num { position: absolute; top: 4px; right: 8px; font-size: .75em; color: var(--secondary-text-color); }
  .plant { font-weight: 500; line-height: 1.25; min-height: 2.5em; padding-right: 14px; overflow: hidden; overflow-wrap: anywhere;
           display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .phase { color: var(--c); font-size: .85em; }
  .days { color: var(--secondary-text-color); font-size: .8em; min-height: 1.1em; }
  .bar { height: 4px; background: var(--divider-color); border-radius: 2px; margin-top: 6px; overflow: hidden; }
  .bar span { display: block; height: 100%; background: var(--c); }
  .glyph { display: block; width: 100%; height: 100%; min-height: 40px; background: var(--c); -webkit-mask: var(--m) center / contain no-repeat; mask: var(--m) center / contain no-repeat; }
  .pot .face .glyph { width: 84%; height: 84%; min-height: 0; margin: auto; }
  .tile > .glyph { height: 56px; margin-bottom: 4px; }
  img { width: 100%; height: 56px; object-fit: cover; border-radius: 4px; margin-bottom: 4px; }
  .phase ha-icon { --mdc-icon-size: 16px; vertical-align: -3px; }
  .slot.pot { border: none; border-radius: 12px; padding: 4px; text-align: center; }
  .pot .ring { width: min(100%, 76px); aspect-ratio: 1; margin: 0 auto 6px; border-radius: 50%; position: relative;
               display: flex; align-items: center; justify-content: center;
               background: conic-gradient(var(--c) calc(var(--p) * 1%), var(--divider-color) 0); }
  .pot .face { width: calc(100% - 10px); height: calc(100% - 10px); border-radius: 50%; background: var(--card-background-color, #fff);
               display: flex; align-items: center; justify-content: center; overflow: hidden; color: var(--c); }
  .pot .face ha-icon { --mdc-icon-size: 28px; }
  .pot .face img { width: 100%; height: 100%; object-fit: cover; margin: 0; border-radius: 50%; }
  .pot .plant { padding-right: 0; font-size: .8em; overflow-wrap: normal; word-break: normal; hyphens: auto; min-height: 2.5em; }
  .pot .phase { font-size: .75em; }
  .pot .days { font-size: .7em; }
  .board { display: flex; gap: 10px; margin: 12px 16px 16px; padding: 10px; border: 1px solid var(--divider-color); border-radius: 20px; }
  .mgblock { flex: 3; display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px 8px; align-content: center; align-items: start; padding: 6px; border: 1px solid var(--divider-color); border-radius: 14px; }
  .board.stack { flex-direction: column; }
  .plblock { flex: 2.6; display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; align-content: start; padding: 6px; }
  .plblock.full { flex: 1; grid-template-columns: repeat(4, 1fr); }
  .slot.sq { border: none; padding: 2px; text-align: center; }
  .sq .box { aspect-ratio: 1; border-radius: 10px; display: flex; align-items: center; justify-content: center; overflow: hidden;
             border: 2px solid var(--c); background: color-mix(in srgb, var(--c) 22%, transparent); font-size: 1.4em; font-weight: 500; }
  .sq .box img { width: 100%; height: 100%; object-fit: cover; margin: 0; border-radius: 0; }
  .sq .plant { font-size: .75em; min-height: 1.3em; padding: 0; margin-top: 4px; line-height: 1.2; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .sq .days { font-size: .65em; }
  .add { padding: 0 16px 14px; }
  .pot .badge { position: absolute; top: -2px; right: -2px; background: var(--card-background-color, #fff); border: 1px solid var(--divider-color);
                border-radius: 50%; width: 18px; height: 18px; display: flex; align-items: center; justify-content: center; font-size: .7em; }
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 10; }
  .dialog { background: var(--card-background-color, #fff); color: var(--primary-text-color); border-radius: 12px; padding: 16px; width: min(92vw, 420px); max-height: 90vh; overflow: auto; }
  .dialog h3, .dialog h4 { margin: 0 0 8px; }
  .field { display: flex; flex-direction: column; gap: 4px; margin: 8px 0; }
  .field span { font-size: .85em; color: var(--secondary-text-color); }
  select, input { padding: 8px; border-radius: 6px; border: 1px solid var(--divider-color); background: var(--card-background-color, #fff); color: inherit; font: inherit; }
  .btns { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
  button { padding: 8px 14px; border-radius: 6px; border: 1px solid var(--divider-color); background: transparent; color: inherit; cursor: pointer; font: inherit; }
  button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
  .hint { color: var(--secondary-text-color); font-size: .85em; margin: 4px 0 8px; }
  .error { color: var(--error-color, #d32f2f); }
`;

const EDITOR_TEXT = {
  de: { entity: "Garten-Sensor der Box", style: "Darstellung", microgreens: "Microgreens-Modul", show_images: "Fotos statt Icons anzeigen",
        editable: "Bedienen erlauben (Slot antippen)", columns: "Spalten (nur Kacheln)", microgreen_slots: "Microgreen-Felder begrenzen (nur Kacheln)",
        app: "Wie die App (runde Töpfchen)", tiles: "Einfache Kacheln", auto: "Automatisch", hide: "Ausblenden" },
  en: { entity: "Garden sensor of the box", style: "Style", microgreens: "Microgreens module", show_images: "Show photos instead of icons",
        editable: "Allow editing (tap a slot)", columns: "Columns (tiles only)", microgreen_slots: "Limit microgreen fields (tiles only)",
        app: "Like the app (round pots)", tiles: "Simple tiles", auto: "Automatic", hide: "Hide" },
};

class GreenboxGardenCardEditor extends HTMLElement {
  setConfig(config) { this._config = { ...config }; this._render(); }
  set hass(hass) { this._hass = hass; if (this._form) this._form.hass = hass; }
  get _t() { return EDITOR_TEXT[((this._hass && this._hass.language) || "en").startsWith("de") ? "de" : "en"]; }

  _schema() {
    const t = this._t;
    return [
      { name: "entity", required: true, selector: { entity: { filter: [{ domain: "sensor", integration: "greenbox" }] } } },
      { name: "style", selector: { select: { mode: "dropdown", options: [{ value: "app", label: t.app }, { value: "tiles", label: t.tiles }] } } },
      { name: "microgreens", selector: { select: { mode: "dropdown", options: [{ value: "auto", label: t.auto }, { value: "false", label: t.hide }] } } },
      { name: "show_images", selector: { boolean: {} } },
      { name: "editable", selector: { boolean: {} } },
      { name: "columns", selector: { number: { min: 1, max: 8, mode: "box" } } },
      { name: "microgreen_slots", selector: { number: { min: 1, max: 6, mode: "box" } } },
    ];
  }

  _data() {
    const c = this._config || {};
    return { style: "app", microgreens: "auto", show_images: false, editable: true, columns: 4, ...c,
             microgreens: c.microgreens === false || c.microgreens === "false" ? "false" : "auto" };
  }

  _render() {
    if (!this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (schema) => this._t[schema.name] || schema.name;
      this._form.addEventListener("value-changed", (ev) => { ev.stopPropagation(); this._changed(ev.detail.value); });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = this._data();
    this._form.schema = this._schema();
  }

  _changed(value) {
    const config = { ...this._config, ...value };
    config.microgreens = value.microgreens === "false" ? false : "auto";   // "false" aus dem Auswahlfeld -> echtes false
    // Voreinstellungen nicht in die YAML schreiben, damit sie schlank bleibt
    const defaults = { style: "app", microgreens: "auto", show_images: false, editable: true, columns: 4 };
    for (const [k, v] of Object.entries(defaults)) if (config[k] === v) delete config[k];
    for (const k of ["columns", "microgreen_slots"]) if (config[k] === "" || config[k] === undefined || config[k] === null) delete config[k];
    this._config = config;
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
  }
}
// Doppeltes Laden (z. B. alte Ressource von Hand plus automatisch eingebunden) darf keinen Fehler auslösen
if (!customElements.get("greenbox-garden-card-editor")) customElements.define("greenbox-garden-card-editor", GreenboxGardenCardEditor);

if (!customElements.get("greenbox-garden-card")) {
customElements.define("greenbox-garden-card", GreenboxGardenCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "greenbox-garden-card", name: "GreenBox Garten", description: "Slots, Pflanzen und Wachstumsphasen einer GreenBox – Slot antippen zum Bepflanzen", preview: false });
}
