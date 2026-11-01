// Scene Studio room card (andrejem 2026)
// One card per area: room brightness, scene tiles with preset images, light rows
// (light helpers expandable to their member lights) and the Raumlicht motion switch.
// Everything is derived from the area, so new scenes and lights show up automatically.

(async () => {
// The card borrows Lit from Home Assistant's own elements. This module is loaded early as
// extra module, so wait until the dashboard elements exist.
await Promise.race([
  customElements.whenDefined("ha-panel-lovelace"),
  customElements.whenDefined("hui-view"),
  customElements.whenDefined("ha-card"),
]);
const base = customElements.get("ha-panel-lovelace") || customElements.get("hui-view") || customElements.get("ha-card");
const LitElement = Object.getPrototypeOf(base);
const html = LitElement.prototype.html;
const css = LitElement.prototype.css;

const DOUBLE_TAP_MS = 260;

// Texts: English by default, German when Home Assistant runs in German.
const TEXTS = {
  en: {
    on_of: "{on} of {total} on",
    off: "Off",
    lamps: "{n} lights",
    auto_on: "Auto: on",
    auto_off: "Auto: off",
    tile_dynamic: "Tap: dynamic · Double tap: static · Hold: details",
    tile_static: "Tap: activate · Hold: details",
    no_area: "Please choose an area (area: <area_id>)",
    card_description: "Room brightness, scene tiles with preset images and light rows for one area.",
    // editor
    area: "Room (area)",
    area_help: "Scenes and lights of this area show up automatically.",
    name: "Title",
    name_help: "Empty = name of the area",
    columns: "Scenes per row",
    light_columns: "Lights per row",
    light_columns_help: "Light groups always use the full width",
    show_lights: "Show lights",
    show_auto: "Motion chip (Raumlicht)",
    show_auto_help: "Only shown when the Raumlicht integration is used",
    chips: "Extra chips",
    chips_help: "E.g. a cabinet light or a fan: tap toggles, hold opens the details. Usually also add them to \"Hide\", so they are not shown twice.",
    hide: "Hide",
    hide_help: "Lights or scenes that should not be shown on the card, e.g. scenes only used by motion sensors",
    section_content: "Choose scenes and lights yourself",
    scenes: "Scene tiles",
    scenes_help: "Empty = all scenes of the area. Otherwise only these, in this order.",
    lights: "Lights",
    lights_help: "Empty = all lights of the area",
    section_advanced: "Advanced",
    master: "Room slider controls",
    master_help: "Light or light group for the slider at the top (on/off and brightness). Empty = the Raumlicht room group or all lights of the room.",
    structural: "Light groups without own row",
    structural_help: "These groups are not shown as a row, only their single lights (e.g. a group \"whole living room\").",
  },
  de: {
    on_of: "{on} von {total} an",
    off: "Aus",
    lamps: "{n} Lampen",
    auto_on: "Auto: an",
    auto_off: "Auto: aus",
    tile_dynamic: "Tippen: dynamisch · Doppeltippen: statisch · Halten: Details",
    tile_static: "Tippen: aktivieren · Halten: Details",
    no_area: "Bitte einen Bereich wählen (area: <area_id>)",
    card_description: "Raumhelligkeit, Szenen-Kacheln mit Bildern und Lampen eines Bereichs.",
    area: "Raum (Bereich)",
    area_help: "Szenen und Lampen dieses Bereichs erscheinen automatisch.",
    name: "Titel",
    name_help: "Leer = Name des Bereichs",
    columns: "Szenen pro Zeile",
    light_columns: "Lampen pro Zeile",
    light_columns_help: "Lichtgruppen nutzen immer die ganze Breite",
    show_lights: "Lampen anzeigen",
    show_auto: "Bewegungs-Chip (Raumlicht)",
    show_auto_help: "Erscheint nur, wenn die Raumlicht-Integration genutzt wird",
    chips: "Zusätzliche Chips",
    chips_help: "Z. B. Schranklicht oder Ventilator: Tippen schaltet, Halten öffnet die Details. Meist auch unter „Ausblenden“ eintragen, damit sie nicht doppelt erscheinen.",
    hide: "Ausblenden",
    hide_help: "Lampen oder Szenen, die nicht auf der Karte erscheinen sollen, z. B. Szenen nur für Bewegungsmelder",
    section_content: "Szenen und Lampen selbst wählen",
    scenes: "Szenen-Kacheln",
    scenes_help: "Leer = alle Szenen des Bereichs. Sonst nur diese, in dieser Reihenfolge.",
    lights: "Lampen",
    lights_help: "Leer = alle Lampen des Bereichs",
    section_advanced: "Erweitert",
    master: "Raum-Regler steuert",
    master_help: "Licht oder Lichtgruppe für den Regler oben (an/aus und Helligkeit). Leer = Raumlicht-Gruppe bzw. alle Lampen des Raums.",
    structural: "Lichtgruppen ohne eigene Zeile",
    structural_help: "Diese Gruppen erscheinen nicht als Zeile, nur ihre einzelnen Lampen (z. B. eine Gruppe „ganzes Wohnzimmer“).",
  },
};

function lang(hass) {
  const l = hass?.locale?.language || hass?.language || navigator.language || "en";
  return String(l).toLowerCase().startsWith("de") ? "de" : "en";
}

function t(hass, key, vars = {}) {
  const text = TEXTS[lang(hass)][key] ?? TEXTS.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (_, k) => (k in vars ? vars[k] : ""));
}
const HOLD_MS = 550;

function entityArea(hass, entityId) {
  const e = hass.entities?.[entityId];
  if (!e) return undefined;
  if (e.area_id) return e.area_id;
  const d = e.device_id ? hass.devices?.[e.device_id] : undefined;
  return d?.area_id;
}

function isVisible(hass, entityId) {
  const e = hass.entities?.[entityId];
  return !(e && (e.hidden || e.entity_category));
}

function members(hass, entityId) {
  const m = hass.states[entityId]?.attributes?.entity_id;
  return Array.isArray(m) ? m.filter((x) => x.startsWith("light.")) : null;
}

function leaves(hass, entityId, seen = new Set()) {
  if (seen.has(entityId)) return [];
  seen.add(entityId);
  const m = members(hass, entityId);
  if (!m) return [entityId];
  return m.flatMap((x) => leaves(hass, x, seen));
}

function lightName(hass, entityId, roomName) {
  const st = hass.states[entityId];
  let n = (st?.attributes?.friendly_name || entityId).trim();
  for (const prefix of ["Beleuchtung " + roomName, "Lampen " + roomName, roomName]) {
    if (roomName && n.startsWith(prefix + " ")) n = n.slice(prefix.length + 1);
  }
  return n.trim() || st?.attributes?.friendly_name || entityId;
}

// Chip label: like lightName, and also without the room name at the end ("Schrank Arbeitszimmer" -> "Schrank")
function chipName(hass, entityId, roomName) {
  const n = lightName(hass, entityId, roomName);
  return roomName && n.endsWith(" " + roomName) ? n.slice(0, -roomName.length - 1) : n;
}

function brightnessPct(st) {
  if (!st || st.state !== "on") return 0;
  const b = st.attributes.brightness;
  return b == null ? 100 : Math.max(1, Math.round((b / 255) * 100));
}

function lightColor(st) {
  const rgb = st?.attributes?.rgb_color;
  if (st?.state === "on" && Array.isArray(rgb)) return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
  return "var(--state-light-active-color, #ffc107)";
}

class SceneStudioRoomCard extends LitElement {
  static get properties() {
    return { hass: { attribute: false }, _config: { state: true }, _open: { state: true }, _drag: { state: true } };
  }

  static getStubConfig(hass) {
    const area = Object.values(hass.areas || {})[0];
    return { area: area?.area_id || "" };
  }

  static getConfigElement() {
    return document.createElement("scene-studio-room-card-editor");
  }

  setConfig(config) {
    if (!config || !config.area) throw new Error(t(this.hass, "no_area"));
    this._config = { columns: 3, light_columns: 2, show_lights: true, show_auto: true, ...config };
    this._open = this._open || {};
    this._drag = null;
  }

  getCardSize() {
    return 6;
  }

  // ------------------------------------------------------------------ model
  _model() {
    const hass = this.hass;
    const cfg = this._config;
    const area = cfg.area;
    const hide = new Set(cfg.hide || []);
    const roomName = cfg.name || hass.areas?.[area]?.name || area;

    // Raumlicht scene select of this area (exposes scene mapping and the room light groups)
    const select = Object.values(hass.states).find(
      (s) => s.entity_id.startsWith("select.") && Array.isArray(s.attributes.scenes) && s.attributes.area_id === area,
    );
    const rlScenes = select ? select.attributes.scenes : [];
    const sceneToRl = {};
    rlScenes.forEach((s, i) => s.entities.forEach((e) => (sceneToRl[e] = { ...s, index: i })));
    const rlDynamic = new Set(rlScenes.flatMap((s) => s.dynamic || []));

    // motion switch of the same Raumlicht device
    let motionSwitch;
    if (select && cfg.show_auto) {
      const dev = hass.entities?.[select.entity_id]?.device_id;
      motionSwitch = Object.values(hass.entities || {}).find(
        (e) => e.device_id === dev && e.entity_id.startsWith("switch.") && e.platform === "room_light",
      )?.entity_id;
    }

    // lights
    let lights;
    if (Array.isArray(cfg.lights)) {
      lights = cfg.lights.filter((e) => hass.states[e]);
    } else {
      lights = Object.keys(hass.states).filter(
        (e) => e.startsWith("light.") && entityArea(hass, e) === area && isVisible(hass, e) && !/_segment_\d+$/.test(e),
      );
    }
    lights = lights.filter((e) => !hide.has(e));
    // lights of the Raumlicht room groups belong to the room even without an area
    if (!Array.isArray(cfg.lights) && select) {
      for (const g of [select.attributes.room_lights, select.attributes.ambient_lights]) {
        if (g && hass.states[g] && !lights.includes(g)) lights.push(g);
      }
    }
    const groups = lights.filter((e) => members(hass, e));
    const leafSet = new Set(lights.filter((e) => !members(hass, e)));
    groups.forEach((g) => leaves(hass, g).forEach((l) => leafSet.add(l)));
    const allLeaves = [...leafSet].filter((e) => hass.states[e] && !hide.has(e));

    // master: Raumlicht room lights, a group that covers every light of the room, or all lights
    let master = cfg.master || select?.attributes.room_lights;
    if (!master || !hass.states[master]) {
      master = groups
        .map((g) => [g, new Set(leaves(hass, g))])
        .filter(([, l]) => allLeaves.every((x) => l.has(x)))
        .sort((a, b) => a[1].size - b[1].size)[0]?.[0];
    }
    const masterLeaves = master ? new Set(leaves(hass, master)) : new Set(allLeaves);

    // Structural groups (room and ambient light group of Raumlicht, room-wide groups) are not
    // shown as rows; the helpers inside them are.
    const structural = new Set([master, select?.attributes.room_lights, select?.attributes.ambient_lights, ...(cfg.structural || [])].filter(Boolean));
    groups.forEach((g) => {
      const gl = new Set(leaves(hass, g));
      if (allLeaves.length && allLeaves.every((x) => gl.has(x))) structural.add(g);
    });

    // rows: groups that are not structural and not inside another listed group, plus loose lights
    const rowGroups = groups.filter((g) => {
      if (structural.has(g)) return false;
      return !groups.some((o) => o !== g && !structural.has(o) && members(hass, o)?.includes(g));
    });
    const covered = new Set(rowGroups.flatMap((g) => leaves(hass, g)));
    const loose = allLeaves.filter((l) => !covered.has(l));
    const byName = (a, b) => lightName(hass, a, roomName).localeCompare(lightName(hass, b, roomName), lang(hass));
    const rows = [...rowGroups.sort(byName), ...loose.sort(byName)];

    // scenes
    // config "scenes": explicit list and order; otherwise all scene entities of the area
    const scenes = (Array.isArray(this._config.scenes)
      ? this._config.scenes.filter((e) => hass.states[e])
      : Object.keys(hass.states)
        .filter((e) => e.startsWith("scene.") && entityArea(hass, e) === area && isVisible(hass, e) && !hide.has(e))
        .sort((a, b) => {
          const ra = sceneToRl[a]?.index ?? 999;
          const rb = sceneToRl[b]?.index ?? 999;
          return ra - rb || this._sceneLabel(a, sceneToRl, roomName).localeCompare(this._sceneLabel(b, sceneToRl, roomName), lang(hass));
        }));
    // keep one tile per Raumlicht scene (a Raumlicht scene may start several scene entities)
    const seenRl = new Set();
    const tiles = scenes.filter((e) => {
      const rl = sceneToRl[e];
      if (!rl) return true;
      if (seenRl.has(rl.name)) return false;
      seenRl.add(rl.name);
      return true;
    });

    const masterOn = master ? hass.states[master]?.state === "on" : allLeaves.some((l) => hass.states[l]?.state === "on");
    let active;
    if (masterOn) {
      if (select && select.state && select.state !== "unknown") {
        const rlActive = tiles.find((t) => sceneToRl[t]?.name === select.state);
        const selChanged = Date.parse(select.last_changed) || 0;
        const newerOther = tiles
          .filter((t) => !sceneToRl[t])
          .map((t) => [t, Date.parse(hass.states[t].state) || 0])
          .filter(([, ts]) => ts > selChanged)
          .sort((a, b) => b[1] - a[1])[0];
        active = newerOther ? newerOther[0] : rlActive;
      } else {
        active = tiles
          .map((t) => [t, Date.parse(hass.states[t].state) || 0])
          .sort((a, b) => b[1] - a[1])[0]?.[0];
      }
    }

    return { roomName, select, sceneToRl, rlDynamic, motionSwitch, master, masterLeaves, allLeaves, rows, tiles, active, masterOn };
  }

  _sceneLabel(entityId, sceneToRl, roomName) {
    if (sceneToRl[entityId]) return sceneToRl[entityId].name;
    let n = this.hass.states[entityId]?.attributes?.friendly_name || entityId;
    if (roomName && n.startsWith(roomName + " ")) n = n.slice(roomName.length + 1);
    return n;
  }

  // ------------------------------------------------------------------ actions
  _call(domain, service, data) {
    return this.hass.callService(domain, service, data);
  }

  _moreInfo(entityId) {
    this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId }, bubbles: true, composed: true }));
  }

  _lightTargets(m, entityId) {
    if (entityId) return entityId;
    return m.master || m.allLeaves;
  }

  _toggleLights(m, entityId) {
    const target = this._lightTargets(m, entityId);
    const on = entityId ? this.hass.states[entityId]?.state === "on" : m.masterOn;
    this._call("light", on ? "turn_off" : "turn_on", { entity_id: target });
  }

  _setBrightness(m, entityId, pct) {
    const target = this._lightTargets(m, entityId);
    if (pct <= 0) this._call("light", "turn_off", { entity_id: target });
    else this._call("light", "turn_on", { entity_id: target, brightness_pct: pct });
  }

  _activateScene(m, entityId, statik) {
    const st = this.hass.states[entityId];
    const savedId = st?.attributes?.saved_scene_id;
    const isDynamic = !!(st?.attributes?.dynamic || m.rlDynamic.has(entityId));
    if (statik && savedId && isDynamic) {
      this._call("scene_studio", "activate_saved_scene", { id: savedId, dynamic: false });
      return;
    }
    const rl = m.sceneToRl[entityId];
    if (rl && m.select) {
      this._call("room_light", "set_scene", { area_id: this._config.area, scene: rl.name });
      return;
    }
    this._call("scene", "turn_on", { entity_id: entityId });
  }

  // tap / double tap / hold on scene tiles
  _tilePointerDown(ev, m, entityId) {
    this._holdFired = false;
    clearTimeout(this._holdTimer);
    this._holdTimer = setTimeout(() => {
      this._holdFired = true;
      this._moreInfo(entityId);
    }, HOLD_MS);
  }

  _tilePointerUp(ev, m, entityId) {
    clearTimeout(this._holdTimer);
    if (this._holdFired) return;
    if (this._tapTimer && this._tapEntity === entityId) {
      clearTimeout(this._tapTimer);
      this._tapTimer = null;
      this._activateScene(m, entityId, true);
      return;
    }
    this._tapEntity = entityId;
    this._tapTimer = setTimeout(() => {
      this._tapTimer = null;
      this._activateScene(m, entityId, false);
    }, DOUBLE_TAP_MS);
  }

  // slider rows: tap = toggle, drag = brightness, hold = more-info
  _sliderDown(ev, m, key, entityId) {
    const el = ev.currentTarget;
    el.setPointerCapture?.(ev.pointerId);
    const rect = el.getBoundingClientRect();
    this._slide = { key, entityId, rect, x0: ev.clientX, moved: false, hold: false };
    clearTimeout(this._holdTimer);
    this._holdTimer = setTimeout(() => {
      if (this._slide && !this._slide.moved) {
        this._slide.hold = true;
        this._moreInfo(entityId || m.master || m.allLeaves[0]);
      }
    }, HOLD_MS);
  }

  _sliderMove(ev) {
    const s = this._slide;
    if (!s) return;
    if (!s.moved && Math.abs(ev.clientX - s.x0) < 8) return;
    s.moved = true;
    clearTimeout(this._holdTimer);
    const pct = Math.min(100, Math.max(0, Math.round(((ev.clientX - s.rect.left) / s.rect.width) * 100)));
    this._drag = { key: s.key, pct };
  }

  _sliderUp(ev, m) {
    const s = this._slide;
    this._slide = null;
    clearTimeout(this._holdTimer);
    if (!s || s.hold) return;
    if (s.moved && this._drag) this._setBrightness(m, s.entityId, this._drag.pct);
    else this._toggleLights(m, s.entityId);
    setTimeout(() => (this._drag = null), 600);
  }

  // ------------------------------------------------------------------ render
  _slider(m, key, entityId, label, sub, opts = {}) {
    const hass = this.hass;
    let pct;
    let on;
    let color;
    if (entityId) {
      const st = hass.states[entityId];
      pct = brightnessPct(st);
      on = st?.state === "on";
      color = lightColor(st);
    } else {
      const st = m.master ? hass.states[m.master] : null;
      const ons = m.allLeaves.map((l) => hass.states[l]).filter((s) => s?.state === "on");
      on = m.masterOn;
      pct = st ? brightnessPct(st) : ons.length ? Math.round(ons.reduce((a, s) => a + brightnessPct(s), 0) / ons.length) : 0;
      color = lightColor(st || ons[0]);
    }
    if (this._drag?.key === key) pct = this._drag.pct;
    const unavailable = entityId && ["unavailable", "unknown"].includes(hass.states[entityId]?.state);
    return html`
      <div
        class="slider ${opts.small ? "small" : ""} ${opts.cls || ""} ${on ? "on" : ""} ${unavailable ? "unavailable" : ""}"
        style="--fill:${on || this._drag?.key === key ? pct : 0}%; --color:${color}"
        @pointerdown=${(e) => this._sliderDown(e, m, key, entityId)}
        @pointermove=${(e) => this._sliderMove(e)}
        @pointerup=${(e) => this._sliderUp(e, m)}
        @pointercancel=${() => ((this._slide = null), clearTimeout(this._holdTimer))}
        @contextmenu=${(e) => e.preventDefault()}
      >
        <div class="fill"></div>
        <ha-icon class="licon" .icon=${opts.icon || (on ? "mdi:lightbulb-on" : "mdi:lightbulb-outline")}></ha-icon>
        <div class="label"><span class="name">${label}</span>${sub ? html`<span class="sub">${sub}</span>` : ""}</div>
        <div class="value">${unavailable ? "–" : on ? `${pct} %` : t(hass, "off")}</div>
        ${opts.expandable
          ? html`<ha-icon
              class="chevron ${this._open[entityId] ? "open" : ""}"
              icon="mdi:chevron-right"
              @pointerdown=${(e) => e.stopPropagation()}
              @pointerup=${(e) => e.stopPropagation()}
              @click=${(e) => {
                e.stopPropagation();
                this._open = { ...this._open, [entityId]: !this._open[entityId] };
              }}
            ></ha-icon>`
          : ""}
      </div>
    `;
  }

  _tile(m, entityId) {
    const st = this.hass.states[entityId];
    const pic = st?.attributes?.entity_picture;
    const dynamic = !!(st?.attributes?.dynamic || m.rlDynamic.has(entityId));
    const active = m.active === entityId;
    return html`
      <div
        class="tile ${active ? "active" : ""}"
        style=${pic ? `background-image:url('${pic}')` : ""}
        @pointerdown=${(e) => this._tilePointerDown(e, m, entityId)}
        @pointerup=${(e) => this._tilePointerUp(e, m, entityId)}
        @pointercancel=${() => clearTimeout(this._holdTimer)}
        @contextmenu=${(e) => e.preventDefault()}
        title=${t(this.hass, dynamic ? "tile_dynamic" : "tile_static")}
      >
        ${pic ? "" : html`<ha-icon class="noimg" icon=${st?.attributes?.icon || "mdi:palette"}></ha-icon>`}
        <div class="badges">
          <span>${dynamic ? html`<ha-icon icon="mdi:motion-play-outline"></ha-icon>` : ""}</span>
          <span>${active ? html`<ha-icon icon="mdi:check-circle"></ha-icon>` : ""}</span>
        </div>
        <div class="tname">${this._sceneLabel(entityId, m.sceneToRl, m.roomName)}</div>
      </div>
    `;
  }

  // Extra chip (option `chips`): tap toggles, hold opens the details
  _chip(entityId, roomName) {
    const st = this.hass.states[entityId];
    const on = st.state === "on";
    const isLight = entityId.startsWith("light.");
    const pct = isLight && on ? brightnessPct(st) : null;
    const icon = st.attributes.icon || (isLight ? (on ? "mdi:lightbulb" : "mdi:lightbulb-outline") : on ? "mdi:toggle-switch" : "mdi:toggle-switch-off-outline");
    let timer = null;
    let held = false;
    const down = () => {
      held = false;
      timer = setTimeout(() => { held = true; this._moreInfo(entityId); }, HOLD_MS);
    };
    const up = () => {
      clearTimeout(timer);
      if (!held) this._call("homeassistant", "toggle", { entity_id: entityId });
    };
    return html`<button class="chip ${on ? "on" : ""}" title=${st.attributes.friendly_name || entityId}
        @pointerdown=${down} @pointerup=${up} @pointerleave=${() => clearTimeout(timer)} @contextmenu=${(e) => e.preventDefault()}>
      <ha-icon icon=${icon}></ha-icon>
      ${chipName(this.hass, entityId, roomName)}${pct != null ? html`<span class="chip-val">${pct} %</span>` : ""}
    </button>`;
  }

  render() {
    if (!this.hass || !this._config) return html``;
    const m = this._model();
    const cfg = this._config;
    const onCount = m.allLeaves.filter((l) => this.hass.states[l]?.state === "on").length;
    const motion = cfg.show_auto && m.motionSwitch ? this.hass.states[m.motionSwitch] : null;
    const extra = (cfg.chips || []).filter((e) => this.hass.states[e]);
    return html`
      <ha-card>
        <div class="content">
          ${this._slider(m, "__master", null, m.roomName, m.allLeaves.length ? t(this.hass, "on_of", { on: onCount, total: m.allLeaves.length }) : "", {
            icon: m.masterOn ? "mdi:lightbulb-group" : "mdi:lightbulb-group-outline",
          })}
          ${m.tiles.length
            ? html`<div class="tiles" style="--cols:${cfg.columns}">${m.tiles.map((t) => this._tile(m, t))}</div>`
            : ""}
          ${cfg.show_lights && m.rows.length > 0 && !(m.rows.length === 1 && m.rows[0] === m.master)
            ? html`<div class="rows" style="--lcols:${cfg.light_columns}">
                ${m.rows.map((r) => {
                  const mem = members(this.hass, r);
                  return html`
                    ${this._slider(m, r, r, lightName(this.hass, r, m.roomName), mem ? t(this.hass, "lamps", { n: mem.length }) : "", {
                      expandable: !!mem,
                      cls: mem ? "full" : "",
                    })}
                    ${mem && this._open[r]
                      ? html`<div class="members full">
                          ${mem.map((x) => this._slider(m, x, x, lightName(this.hass, x, m.roomName), "", { small: true }))}
                        </div>`
                      : ""}
                  `;
                })}
              </div>`
            : ""}
          ${motion || extra.length
            ? html`<div class="chips">
                ${motion
                  ? html`<button class="chip ${motion.state === "on" ? "on" : ""}" @click=${() => this._call("switch", "toggle", { entity_id: m.motionSwitch })}>
                      <ha-icon icon=${motion.state === "on" ? "mdi:motion-sensor" : "mdi:motion-sensor-off"}></ha-icon>
                      ${t(this.hass, motion.state === "on" ? "auto_on" : "auto_off")}
                    </button>`
                  : ""}
                ${extra.map((e) => this._chip(e, m.roomName))}
              </div>`
            : ""}
        </div>
      </ha-card>
    `;
  }

  static get styles() {
    return css`
      ha-card {
        overflow: hidden;
      }
      .content {
        padding: 12px;
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .slider {
        position: relative;
        display: flex;
        align-items: center;
        gap: 10px;
        height: 52px;
        padding: 0 14px;
        border-radius: 14px;
        background: var(--secondary-background-color, rgba(127, 127, 127, 0.12));
        overflow: hidden;
        cursor: pointer;
        user-select: none;
        touch-action: pan-y;
        -webkit-tap-highlight-color: transparent;
      }
      .slider.small {
        height: 40px;
        border-radius: 11px;
        padding: 0 12px;
      }
      .slider .fill {
        position: absolute;
        inset: 0 auto 0 0;
        width: var(--fill);
        background: var(--color);
        opacity: 0.35;
        transition: width 0.25s ease;
        pointer-events: none;
      }
      .slider > :not(.fill) {
        position: relative;
      }
      .slider .licon {
        --mdc-icon-size: 22px;
        color: var(--secondary-text-color);
        flex: none;
      }
      .slider.on .licon {
        color: var(--color);
        filter: brightness(1.1);
      }
      .slider.small .licon {
        --mdc-icon-size: 18px;
      }
      .slider .label {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
        line-height: 1.2;
      }
      .slider .name {
        font-weight: 600;
        font-size: 15px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .slider.small .name {
        font-weight: 500;
        font-size: 14px;
      }
      .slider .sub {
        font-size: 12px;
        color: var(--secondary-text-color);
      }
      .slider .value {
        font-size: 13px;
        color: var(--secondary-text-color);
        flex: none;
      }
      .slider.on .value {
        color: var(--primary-text-color);
        font-weight: 600;
      }
      .slider.unavailable {
        opacity: 0.5;
      }
      .chevron {
        --mdc-icon-size: 22px;
        margin-right: -6px;
        padding: 6px;
        color: var(--secondary-text-color);
        transition: transform 0.2s ease;
      }
      .chevron.open {
        transform: rotate(90deg);
      }
      .tiles {
        display: grid;
        grid-template-columns: repeat(var(--cols), minmax(0, 1fr));
        gap: 8px;
      }
      .tile {
        position: relative;
        height: 88px;
        border-radius: 14px;
        overflow: hidden;
        background: linear-gradient(135deg, var(--primary-color), var(--accent-color, #555));
        background-size: cover;
        background-position: center;
        cursor: pointer;
        user-select: none;
        -webkit-tap-highlight-color: transparent;
        transition: transform 0.12s ease, box-shadow 0.2s ease;
      }
      .tile:active {
        transform: scale(0.97);
      }
      .tile.active {
        box-shadow: 0 0 0 3px var(--primary-color);
      }
      .tile .noimg {
        position: absolute;
        top: 22px;
        left: 50%;
        transform: translateX(-50%);
        --mdc-icon-size: 30px;
        color: white;
        opacity: 0.8;
      }
      .tile .badges {
        position: absolute;
        inset: 6px 6px auto 8px;
        display: flex;
        justify-content: space-between;
        color: white;
        filter: drop-shadow(0 0 2px rgba(0, 0, 0, 0.8));
        --mdc-icon-size: 18px;
      }
      .tile .tname {
        position: absolute;
        inset: auto 0 0 0;
        padding: 16px 9px 7px;
        font-size: 13px;
        font-weight: 600;
        color: white;
        background: linear-gradient(transparent, rgba(0, 0, 0, 0.65));
        line-height: 1.2;
      }
      .rows {
        display: grid;
        grid-template-columns: repeat(var(--lcols, 2), minmax(0, 1fr));
        gap: 6px;
      }
      .rows .full {
        grid-column: 1 / -1;
      }
      .rows > .slider:not(.full) {
        height: 46px;
        padding: 0 10px;
        gap: 8px;
      }
      .rows > .slider:not(.full) .name {
        font-size: 14px;
      }
      .members {
        display: grid;
        grid-template-columns: repeat(var(--lcols, 2), minmax(0, 1fr));
        gap: 5px;
        padding-left: 14px;
        border-left: 2px solid var(--divider-color);
        margin-left: 10px;
      }
      .chips {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
      .chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        height: 32px;
        padding: 0 12px;
        border-radius: 16px;
        border: 1px solid var(--divider-color);
        background: none;
        color: var(--secondary-text-color);
        font: inherit;
        font-size: 13px;
        cursor: pointer;
        --mdc-icon-size: 18px;
      }
      .chip.on {
        color: var(--primary-text-color);
        border-color: var(--primary-color);
      }
      .chip.on ha-icon {
        color: var(--primary-color);
      }
      .chip-val {
        color: var(--secondary-text-color);
      }
    `;
  }
}

// Visual editor: every option of the card. Lists left empty mean "automatic" and are removed from
// the config, so the card behaves exactly as without the option.
const LIST_KEYS = ["scenes", "lights", "hide", "chips", "structural"];

class SceneStudioRoomCardEditor extends LitElement {
  static get properties() {
    return { hass: { attribute: false }, _config: { state: true } };
  }

  setConfig(config) {
    this._config = { ...config };
  }

  _schema() {
    return [
      { name: "area", required: true, selector: { area: {} } },
      { name: "name", selector: { text: {} } },
      {
        type: "grid",
        name: "",
        schema: [
          { name: "columns", selector: { number: { min: 1, max: 6, mode: "box" } } },
          { name: "light_columns", selector: { number: { min: 1, max: 4, mode: "box" } } },
          { name: "show_lights", selector: { boolean: {} } },
          { name: "show_auto", selector: { boolean: {} } },
        ],
      },
      { name: "chips", selector: { entity: { multiple: true, filter: [{ domain: ["light", "switch", "fan", "input_boolean"] }] } } },
      { name: "hide", selector: { entity: { multiple: true, filter: [{ domain: ["light", "scene"] }] } } },
      {
        type: "expandable",
        name: "",
        title: t(this.hass, "section_content"),
        flatten: true,
        schema: [
          { name: "scenes", selector: { entity: { multiple: true, reorder: true, filter: [{ domain: "scene" }] } } },
          { name: "lights", selector: { entity: { multiple: true, filter: [{ domain: "light" }] } } },
        ],
      },
      {
        type: "expandable",
        name: "",
        title: t(this.hass, "section_advanced"),
        flatten: true,
        schema: [
          { name: "master", selector: { entity: { filter: [{ domain: "light" }] } } },
          { name: "structural", selector: { entity: { multiple: true, filter: [{ domain: "light" }] } } },
        ],
      },
    ];
  }

  _changed(ev) {
    const config = { ...ev.detail.value };
    for (const key of LIST_KEYS) {
      if (Array.isArray(config[key]) && config[key].length === 0) delete config[key];
    }
    for (const key of ["name", "master"]) {
      if (config[key] === "" || config[key] == null) delete config[key];
    }
    this._config = config;
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
  }

  render() {
    if (!this.hass || !this._config) return html``;
    const data = { columns: 3, light_columns: 2, show_lights: true, show_auto: true, ...this._config };
    return html`<ha-form
      .hass=${this.hass}
      .data=${data}
      .schema=${this._schema()}
      .computeLabel=${(s) => t(this.hass, s.name)}
      .computeHelper=${(s) => {
        const key = `${s.name}_help`;
        const text = t(this.hass, key);
        return text === key ? undefined : text;
      }}
      @value-changed=${this._changed}
    ></ha-form>`;
  }
}

if (!customElements.get("scene-studio-room-card")) {
  customElements.define("scene-studio-room-card", SceneStudioRoomCard);
  customElements.define("scene-studio-room-card-editor", SceneStudioRoomCardEditor);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "scene-studio-room-card",
    name: "Scene Studio Room Card",
    description: t(document.querySelector("home-assistant")?.hass, "card_description"),
    preview: true,
  });
}
})();
