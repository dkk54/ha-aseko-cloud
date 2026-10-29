// Aseko pool dashboard: a dashboard strategy plus the cards it uses.
// Everything is built from the user's own Aseko Cloud devices; entities are
// matched by device and translation key, so unit names and the HA language
// do not matter.
//
//   strategy: { type: custom:aseko-pool }
//
// Optional: theme (a Home Assistant theme for the views), rotate_seconds (how
// long the showcase shows each unit, 20 by default).

const DOMAIN = "aseko_cloud";
const LOGO_URL = new URL("./aseko-logo.svg", import.meta.url).href;
const DEFAULT_UNIT_IMAGE = new URL("./unit-asin-aqua.webp", import.meta.url).href;
const REFRESH_HISTORY_MS = 5 * 60 * 1000;

const TEXTS = {
  en: {
    overview: "Pools",
    showcase: "Showcase",
    noUnitsTitle: "No pool unit yet",
    noUnitsText: "Pair an Aseko unit in the Aseko app and it appears here within a few minutes.",
    waterQuality: "Water quality",
    filtration: "Filtration",
    equipment: "Equipment",
    messages: "Messages",
    noMessages: "Everything is running smoothly",
    history: "Last 48 hours",
    settings: "Required values",
    allGood: "All good",
    attention: "Needs attention",
    problem: "Problem",
    offline: "Unit offline",
    water: "Water",
    air: "Air",
    solar: "Solar",
    target: "target",
    running: "Running",
    until: "until",
    scheduled: "Next run",
    nonstop: "Non-stop filtration",
    idle: "Not running",
    noSchedule: "No schedule reported",
    noData: "No data for this period",
    temperature: "Temperature",
    chlorine: "Free chlorine",
    lastSeen: "Updated",
  },
  cs: {
    overview: "Bazény",
    showcase: "Prezentace",
    noUnitsTitle: "Zatím tu není žádná jednotka",
    noUnitsText: "Spárujte jednotku v aplikaci Aseko a do několika minut se tu objeví.",
    waterQuality: "Kvalita vody",
    filtration: "Filtrace",
    equipment: "Technologie",
    messages: "Hlášení",
    noMessages: "Vše běží bez potíží",
    history: "Posledních 48 hodin",
    settings: "Požadované hodnoty",
    allGood: "Vše v pořádku",
    attention: "Vyžaduje pozornost",
    problem: "Porucha",
    offline: "Jednotka je offline",
    water: "Voda",
    air: "Vzduch",
    solar: "Solár",
    target: "cíl",
    running: "Běží",
    until: "do",
    scheduled: "Další filtrace",
    nonstop: "Filtrace nonstop",
    idle: "Neběží",
    noSchedule: "Plán filtrace není k dispozici",
    noData: "Za toto období nejsou data",
    temperature: "Teplota",
    chlorine: "Volný chlor",
    lastSeen: "Aktualizováno",
  },
};

// Tolerances around the unit's required value: within `ok` is fine, within
// `warn` needs a look, anything further is a problem.
const METRICS = {
  ph: { required: "ph_required", ok: 0.2, warn: 0.4, digits: 1, min: 6, max: 9 },
  redox: { required: "redox_required", ok: 50, warn: 100, digits: 0, min: 300, max: 900 },
  cl_free: { required: "cl_free_required", ok: 0.2, warn: 0.35, digits: 2, min: 0, max: 2 },
  salinity: { digits: 1, min: 0, max: 8 },
};

const EQUIPMENT = [
  ["binary_sensor.filtration", "mdi:pump"],
  ["binary_sensor.electrolyzer", "mdi:flash"],
  ["binary_sensor.heating", "mdi:radiator"],
  ["binary_sensor.solar", "mdi:solar-power-variant"],
  ["binary_sensor.water_filling", "mdi:water-plus"],
  ["binary_sensor.water_flow_to_probes", "mdi:waves-arrow-right"],
];

// ---------------------------------------------------------------- helpers

let strategyLanguage;

// Home Assistant regenerates a strategy dashboard only when devices or entities
// change, so the dashboard is rebuilt here when the viewer switches language.
function watchLanguage() {
  setInterval(() => {
    const ha = document.querySelector("home-assistant");
    const panel = ha?.shadowRoot
      ?.querySelector("home-assistant-main")
      ?.shadowRoot?.querySelector("partial-panel-resolver ha-panel-lovelace");
    const language = ha?.hass?.locale?.language;
    if (!language || panel?.lovelace?.rawConfig?.strategy?.type !== "custom:aseko-pool") {
      return;
    }
    if (strategyLanguage && language !== strategyLanguage) {
      strategyLanguage = language;
      panel.shadowRoot?.querySelector("hui-root")?.dispatchEvent(new CustomEvent("strategy-config-changed", { bubbles: true, composed: true }));
    }
  }, 1000);
}

function texts(hass) {
  const language = (hass?.locale?.language || hass?.language || "en").split("-")[0];
  return TEXTS[language] || TEXTS.en;
}

function esc(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}

function unitEntities(hass, deviceId) {
  const entities = {};
  for (const entry of Object.values(hass.entities)) {
    if (entry.platform === DOMAIN && entry.device_id === deviceId && !entry.hidden) {
      entities[`${entry.entity_id.split(".")[0]}.${entry.translation_key}`] = entry.entity_id;
    }
  }
  return entities;
}

function asekoDevices(hass) {
  const ids = new Set(
    Object.values(hass.entities)
      .filter((entry) => entry.platform === DOMAIN && entry.device_id)
      .map((entry) => entry.device_id),
  );
  return [...ids]
    .map((id) => hass.devices[id])
    .filter(Boolean)
    .sort((a, b) => deviceName(a).localeCompare(deviceName(b)));
}

function deviceName(device) {
  return device.name_by_user || device.name;
}

function unitPath(device) {
  return `unit-${device.serial_number || device.id}`;
}

class Unit {
  constructor(hass, deviceId) {
    this.hass = hass;
    this.device = hass.devices[deviceId];
    this.entities = this.device ? unitEntities(hass, deviceId) : {};
  }

  get name() {
    return this.device ? deviceName(this.device) : "";
  }

  id(key) {
    return this.entities[key];
  }

  stateObj(key) {
    return this.hass.states[this.entities[key]];
  }

  state(key) {
    const s = this.stateObj(key)?.state;
    return s === undefined || s === "unknown" || s === "unavailable" ? undefined : s;
  }

  number(key) {
    const value = Number.parseFloat(this.state(key));
    return Number.isFinite(value) ? value : undefined;
  }

  on(key) {
    return this.state(key) === "on";
  }

  formatted(key) {
    const obj = this.stateObj(key);
    return obj ? this.hass.formatEntityState(obj) : "";
  }

  // The registry name is in the server language, so the integration's
  // translations are used to follow the viewer's language.
  label(key) {
    const id = this.entities[key];
    const entry = this.hass.entities[id];
    const translated = entry?.translation_key
      ? this.hass.localize(`component.${DOMAIN}.entity.${key.split(".")[0]}.${entry.translation_key}.name`)
      : "";
    return translated || entry?.name || this.stateObj(key)?.attributes.friendly_name || "";
  }

  unit(key) {
    return this.stateObj(key)?.attributes.unit_of_measurement || "";
  }

  // Photo of the unit's family from the integration; its URL carries an
  // access token that rotates, so it is read on every render. The state is
  // when the photo last changed and makes the browser load the new one.
  // Units of a family without a photo have none.
  get photo() {
    const s = this.stateObj("image.photo");
    const url = s?.attributes.entity_picture;
    return url && `${url}&state=${encodeURIComponent(s.state)}`;
  }

  // Signature of everything this unit shows, to skip needless re-renders.
  signature() {
    return Object.values(this.entities)
      .map((id) => {
        const s = this.hass.states[id];
        return s ? `${s.state}|${s.last_updated}` : "";
      })
      .join(";");
  }

  metric(name) {
    const spec = METRICS[name];
    const value = this.number(`sensor.${name}`);
    const required = spec.required ? this.number(`sensor.${spec.required}`) : undefined;
    let status = "neutral";
    if (value !== undefined && required !== undefined) {
      const diff = Math.abs(value - required);
      status = diff <= spec.ok ? "ok" : diff <= spec.warn ? "warn" : "bad";
    }
    return { name, spec, value, required, status };
  }

  qualityMetrics() {
    return Object.keys(METRICS)
      .filter((name) => this.id(`sensor.${name}`))
      .map((name) => this.metric(name));
  }

  messages() {
    return this.stateObj("binary_sensor.problem")?.attributes.messages || [];
  }

  overall() {
    if (this.id("binary_sensor.online") && !this.on("binary_sensor.online")) {
      return "offline";
    }
    if (this.on("binary_sensor.problem")) {
      return "bad";
    }
    const statuses = this.qualityMetrics().map((m) => m.status);
    if (statuses.includes("bad") || statuses.includes("warn")) {
      return "warn";
    }
    return "ok";
  }

  filtration() {
    const start = this.state("sensor.filtration_period_start");
    const end = this.state("sensor.filtration_period_end");
    return {
      running: this.on("binary_sensor.filtration"),
      nonstop: this.on("binary_sensor.filtration_nonstop"),
      start,
      end,
      speed: this.id("sensor.filtration_speed") ? this.formatted("sensor.filtration_speed") : "",
    };
  }
}

function formatNumber(hass, value, digits) {
  if (value === undefined) {
    return "–";
  }
  return new Intl.NumberFormat(hass.locale?.language || "en", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function minutes(hhmm) {
  const match = /^(\d{1,2}):(\d{2})/.exec(hhmm || "");
  return match ? Number(match[1]) * 60 + Number(match[2]) : undefined;
}

function fire(node, type, detail) {
  node.dispatchEvent(new CustomEvent(type, { detail, bubbles: true, composed: true }));
}

function moreInfo(node, entityId) {
  if (entityId) {
    fire(node, "hass-more-info", { entityId });
  }
}

function navigate(path) {
  const base = window.location.pathname.split("/")[1];
  window.history.pushState(null, "", `/${base}/${path}`);
  window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
}

function statusText(t, status) {
  return { ok: t.allGood, warn: t.attention, bad: t.problem, offline: t.offline }[status];
}

const STATUS_ICON = {
  ok: "mdi:check-circle",
  warn: "mdi:alert",
  bad: "mdi:alert-octagon",
  offline: "mdi:cloud-off-outline",
};

const SHARED_CSS = `
  :host {
    --aseko-blue: #149fe2;
    --aseko-cyan: #00c0ff;
    --aseko-deep: #00405b;
    --aseko-ok: #3fbf6f;
    --aseko-warn: #f5a524;
    --aseko-bad: #ef4444;
    --aseko-neutral: var(--secondary-text-color);
    display: block;
  }
  ha-card { overflow: hidden; height: 100%; box-sizing: border-box; }
  .s-ok { --tone: var(--aseko-ok); }
  .s-warn { --tone: var(--aseko-warn); }
  .s-bad { --tone: var(--aseko-bad); }
  .s-offline, .s-neutral { --tone: var(--aseko-neutral); }
  .clickable { cursor: pointer; }
  .title {
    font-size: 13px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
    color: var(--secondary-text-color); margin: 0 0 var(--aseko-title-gap, 14px);
  }
  @media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
`;

const WAVES_SVG = `
  <svg class="waves" viewBox="0 0 1200 120" preserveAspectRatio="none" aria-hidden="true">
    <path class="w1" d="M0 60 Q150 20 300 60 T600 60 T900 60 T1200 60 V120 H0Z"/>
    <path class="w2" d="M0 70 Q150 35 300 70 T600 70 T900 70 T1200 70 V120 H0Z"/>
    <path class="w3" d="M0 82 Q150 55 300 82 T600 82 T900 82 T1200 82 V120 H0Z"/>
  </svg>`;

const WAVES_CSS = `
  .waves { position: absolute; left: 0; bottom: 0; width: 200%; height: 46%; pointer-events: none; }
  .waves path { fill: #fff; }
  .waves .w1 { opacity: .08; animation: drift 14s linear infinite; }
  .waves .w2 { opacity: .1; animation: drift 9s linear infinite reverse; }
  .waves .w3 { opacity: .14; animation: drift 6s linear infinite; }
  @keyframes drift { from { transform: translateX(0); } to { transform: translateX(-50%); } }
`;

// Base class: renders when the relevant states change and keeps config handy.
class AsekoCard extends HTMLElement {
  setConfig(config) {
    if (!config.device_id) {
      throw new Error("device_id is required");
    }
    this._config = config;
    this._signature = undefined;
  }

  set hass(hass) {
    this._hass = hass;
    const unit = new Unit(hass, this._config.device_id);
    const signature = `${hass.locale?.language}|${unit.signature()}`;
    if (signature === this._signature) {
      return;
    }
    this._signature = signature;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    this.render(unit, texts(hass));
  }

  getCardSize() {
    return 4;
  }

  bindMoreInfo(root = this.shadowRoot) {
    root.querySelectorAll("[data-entity]").forEach((el) =>
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        moreInfo(this, el.dataset.entity);
      }),
    );
  }
}

// ---------------------------------------------------------------- hero card

// The integration provides a photo per unit; the dashboard can override it by
// device model, or set the photo shown without units, with
// `unit_images: { default: <url>, "ASIN AQUA": <url> }`.
function unitImage(images, device) {
  return images?.[device?.model];
}

function heroMarkup(unit, t, { large = false, footer = "", image } = {}) {
  image = image ?? unit.photo;
  const overall = unit.overall();
  const temp = unit.number("sensor.water_temperature");
  const f = unit.filtration();
  const temps = [
    ["sensor.air_temperature", t.air, "mdi:weather-partly-cloudy"],
    ["sensor.solar_temperature", t.solar, "mdi:solar-power-variant"],
  ].filter(([key]) => unit.id(key));
  const filtrationLine = f.nonstop
    ? t.nonstop
    : f.running
      ? `${t.running}${f.end ? ` ${t.until} ${f.end}` : ""}`
      : f.start
        ? `${t.scheduled} ${f.start}${f.end ? `–${f.end}` : ""}`
        : unit.id("binary_sensor.filtration")
          ? t.idle
          : "";
  const target = unit.number("sensor.water_temperature_required");
  return `
    <div class="hero ${large ? "large" : ""} ${image ? "has-img" : ""} s-${overall}">
      <div class="glow"></div>
      ${image ? `<img class="unit-img" src="${esc(image)}" alt="">` : ""}
      ${WAVES_SVG}
      <div class="top">
        <div>
          <img class="logo" src="${LOGO_URL}" alt="Aseko">
          <div class="model">${esc(unit.device?.model || "Aseko")}</div>
          <div class="name">${esc(unit.name)}</div>
        </div>
        <div class="pill" data-entity="${esc(unit.id("binary_sensor.problem") || "")}">
          <ha-icon icon="${STATUS_ICON[overall]}"></ha-icon>${esc(statusText(t, overall))}
        </div>
      </div>
      <div class="main">
        <div class="temp" data-entity="${esc(unit.id("sensor.water_temperature") || "")}">
          <span class="value">${formatNumber(unit.hass, temp, 1)}</span><span class="deg">°C</span>
          <div class="sub">${esc(t.water)}${target !== undefined ? ` · ${esc(t.target)} ${formatNumber(unit.hass, target, 0)} °C` : ""}</div>
        </div>
        <div class="side">
          ${temps
            .map(
              ([key, label, icon]) => `
            <div class="mini" data-entity="${esc(unit.id(key))}">
              <ha-icon icon="${icon}"></ha-icon>
              <span>${esc(label)}</span><b>${formatNumber(unit.hass, unit.number(key), 1)} °C</b>
            </div>`,
            )
            .join("")}
          ${
            filtrationLine
              ? `<div class="mini ${f.running || f.nonstop ? "spin" : ""}" data-entity="${esc(unit.id("binary_sensor.filtration") || "")}">
                  <ha-icon icon="mdi:fan"></ha-icon><span>${esc(t.filtration)}</span><b>${esc(filtrationLine)}</b>
                </div>`
              : ""
          }
          ${
            unit.id("sensor.mode")
              ? `<div class="mini" data-entity="${esc(unit.id("sensor.mode"))}">
                  <ha-icon icon="mdi:tune-variant"></ha-icon><span>${esc(unit.label("sensor.mode"))}</span><b>${esc(unit.formatted("sensor.mode"))}</b>
                </div>`
              : ""
          }
        </div>
      </div>
      ${footer}
    </div>`;
}

const HERO_CSS = `
  .hero {
    position: relative; overflow: hidden; color: #fff; padding: 22px 24px 26px;
    min-height: 210px; box-sizing: border-box; border-radius: var(--ha-card-border-radius, 16px);
    background: linear-gradient(135deg, #003049 0%, var(--aseko-deep) 35%, #0a7fc0 75%, var(--aseko-blue) 100%);
  }
  .hero.s-offline { background: linear-gradient(135deg, #1f2a30, #3a4a52); }
  .hero { container-type: inline-size; }
  .unit-img {
    position: absolute; left: 50%; bottom: 24px; height: calc(100% - 64px); max-height: 180px; max-width: 60%; transform: translateX(-50%);
    object-fit: contain; pointer-events: none; opacity: .95; filter: drop-shadow(0 16px 24px rgba(0,0,0,.35));
    animation: unit-in .8s ease both;
  }
  .s-offline .unit-img { opacity: .5; filter: grayscale(1) drop-shadow(0 16px 24px rgba(0,0,0,.35)); }
  @keyframes unit-in { from { opacity: 0; } }
  @container (max-width: 760px) {
    .hero:not(.large) .unit-img { left: auto; right: 22px; top: 62px; bottom: auto; height: 92px; max-width: 120px; transform: none; }
    .hero.has-img:not(.large) .name { padding-right: 140px; }
  }
  .hero.large .unit-img { left: auto; right: 40px; top: 96px; bottom: auto; height: 36%; max-height: 340px; max-width: 40%; transform: none; }
  .glow {
    position: absolute; inset: -40% -10% auto auto; width: 60%; aspect-ratio: 1; border-radius: 50%;
    background: radial-gradient(circle, rgba(0,192,255,.35), transparent 65%); pointer-events: none;
  }
  ${WAVES_CSS}
  .top { position: relative; display: grid; grid-template-columns: 1fr auto; align-items: start; column-gap: 12px; }
  .top > div:first-child { display: contents; }
  .model, .name { grid-column: 1 / -1; }
  .pill { grid-column: 2; grid-row: 1; }
  .logo { display: block; height: 22px; margin-bottom: 14px; filter: invert(1) drop-shadow(0 2px 8px rgba(0,0,0,.25)); }
  .model { font-size: 12px; letter-spacing: .14em; text-transform: uppercase; opacity: .7; }
  .name { font-size: 22px; font-weight: 600; margin-top: 2px; }
  .pill {
    display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px 6px 8px; border-radius: 999px;
    font-size: 13px; font-weight: 600; background: rgba(255,255,255,.14); backdrop-filter: blur(6px);
    box-shadow: inset 0 0 0 1px rgba(255,255,255,.18); cursor: pointer; white-space: nowrap;
  }
  .pill ha-icon { --mdc-icon-size: 18px; color: var(--tone); filter: drop-shadow(0 0 6px var(--tone)); }
  .s-ok .pill ha-icon { color: #7dffb0; }
  .main { position: relative; display: flex; align-items: flex-end; justify-content: space-between; gap: 18px; margin-top: 18px; flex-wrap: wrap; }
  .temp { cursor: pointer; }
  .temp .value { font-size: 76px; font-weight: 300; line-height: .9; letter-spacing: -.03em; }
  .temp .deg { font-size: 28px; font-weight: 300; vertical-align: top; margin-left: 4px; opacity: .85; }
  .temp .sub { font-size: 14px; opacity: .75; margin-top: 8px; }
  .side { display: grid; gap: 8px; min-width: 220px; }
  .mini {
    display: grid; grid-template-columns: 22px auto 1fr; align-items: center; gap: 8px; cursor: pointer;
    padding: 8px 12px; border-radius: 12px; background: rgba(255,255,255,.1); font-size: 13px;
  }
  .mini ha-icon { --mdc-icon-size: 18px; opacity: .9; }
  .mini span { opacity: .75; }
  .mini b { font-weight: 600; text-align: right; }
  .mini.spin ha-icon { animation: spin 2.4s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .hero.large { min-height: 340px; padding: 36px 40px 44px; }
  .hero.large .name { font-size: 34px; }
  .hero.large .logo { height: 40px; margin-bottom: 22px; }
  .hero.large .temp .value { font-size: 150px; }
  .hero.large .temp .deg { font-size: 48px; }
  .hero.large .temp .sub { font-size: 20px; }
  .hero.large .mini { font-size: 17px; padding: 12px 16px; }
  .hero.large .side { min-width: 320px; gap: 12px; }
`;

class AsekoHeroCard extends AsekoCard {
  render(unit, t) {
    this.shadowRoot.innerHTML = `
      <style>${SHARED_CSS}${HERO_CSS} ha-card { background: none; box-shadow: none; border: none; }</style>
      <ha-card>${heroMarkup(unit, t, { image: this._config.image })}</ha-card>`;
    this.bindMoreInfo();
  }

  getGridOptions() {
    return { columns: "full", min_columns: 6 };
  }
}

// ---------------------------------------------------------------- empty states

// Shown instead of units when none is paired yet.
function idleMarkup(t, { image, clock = false } = {}) {
  return `
    <div class="hero large idle">
      <div class="glow"></div>
      ${WAVES_SVG}
      <div class="idle-body">
        <img class="idle-logo" src="${LOGO_URL}" alt="Aseko">
        ${image ? `<img class="idle-unit" src="${esc(image)}" alt="">` : ""}
        <div class="idle-title">${esc(t.noUnitsTitle)}</div>
        <div class="idle-text">${esc(t.noUnitsText)}</div>
        ${clock ? `<div class="clock idle-clock"></div>` : ""}
      </div>
    </div>`;
}

const IDLE_CSS = `
  .hero.idle { display: flex; align-items: center; justify-content: center; text-align: center; min-height: 420px; }
  .idle-body { position: relative; display: flex; flex-direction: column; align-items: center; gap: 12px; max-width: 640px; }
  .idle-logo { height: 40px; margin-bottom: 18px; filter: invert(1) drop-shadow(0 2px 8px rgba(0,0,0,.25)); }
  .idle-unit {
    height: min(30vh, 260px); max-width: 100%; object-fit: contain; margin-bottom: 18px;
    filter: drop-shadow(0 22px 30px rgba(0,0,0,.4)); animation: float 7s ease-in-out infinite;
  }
  @keyframes float { 50% { transform: translateY(-10px); } }
  .idle-title { font-size: 34px; font-weight: 600; letter-spacing: -.01em; }
  .idle-text { font-size: 18px; line-height: 1.45; opacity: .8; }
  .idle-clock { margin-top: 22px; font-size: 14px; letter-spacing: .14em; text-transform: uppercase; opacity: .65; }
`;

class AsekoEmptyCard extends HTMLElement {
  setConfig(config) {
    this._config = config;
  }

  set hass(hass) {
    const language = hass.locale?.language;
    if (language === this._language) {
      return;
    }
    this._language = language;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    this.shadowRoot.innerHTML = `
      <style>${SHARED_CSS}${HERO_CSS}${IDLE_CSS} ha-card { background: none; box-shadow: none; border: none; }</style>
      <ha-card>${idleMarkup(texts(hass), { image: this._config.image })}</ha-card>`;
  }

  getGridOptions() {
    return { columns: "full" };
  }
}

// ---------------------------------------------------------------- summary card (overview)

class AsekoSummaryCard extends AsekoCard {
  render(unit, t) {
    const metrics = unit.qualityMetrics().filter((m) => m.name !== "salinity");
    const overall = unit.overall();
    this.shadowRoot.innerHTML = `
      <style>
        ${SHARED_CSS}${HERO_CSS}
        ha-card { background: none; box-shadow: none; border: none; cursor: pointer; transition: transform .2s; container-type: inline-size; }
        ha-card:hover { transform: translateY(-2px); }
        @container (max-width: 560px) {
          .main { flex-direction: column; align-items: stretch; }
          .side { min-width: 0; }
        }
        .hero { min-height: 0; padding: 18px 20px 20px; }
        .temp .value { font-size: 56px; }
        .chips { position: relative; display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap; }
        .chip {
          display: flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 10px;
          background: rgba(255,255,255,.12); font-size: 13px;
        }
        .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--tone); box-shadow: 0 0 8px var(--tone); }
        .chip b { font-weight: 600; }
      </style>
      <ha-card class="s-${overall}">
        ${heroMarkup(unit, t, {
          image: this._config.image,
          footer: `<div class="chips">${metrics
            .map(
              (m) => `<div class="chip s-${m.status}"><span class="dot"></span>${esc(unit.label(`sensor.${m.name}`))}
                <b>${formatNumber(unit.hass, m.value, m.spec.digits)}</b></div>`,
            )
            .join("")}</div>`,
        })}
      </ha-card>`;
    this.shadowRoot.querySelector("ha-card").addEventListener("click", () => navigate(this._config.navigation_path));
    this.bindMoreInfo();
  }

  getGridOptions() {
    return { columns: "full" };
  }
}

// ---------------------------------------------------------------- water quality card

class AsekoQualityCard extends AsekoCard {
  render(unit, t) {
    const metrics = unit.qualityMetrics();
    const rows = metrics.map((m) => {
      const { spec, value, required } = m;
      const span = spec.max - spec.min;
      const pos = (v) => `${Math.min(100, Math.max(0, ((v - spec.min) / span) * 100))}%`;
      const band = (width, cls) =>
        required === undefined
          ? ""
          : `<div class="band ${cls}" style="left:${pos(required - width)};right:calc(100% - ${pos(required + width)})"></div>`;
      const unitText = unit.unit(`sensor.${m.name}`);
      return `
        <div class="metric s-${m.status}" data-entity="${esc(unit.id(`sensor.${m.name}`))}">
          <div class="head">
            <span class="label">${esc(unit.label(`sensor.${m.name}`))}</span>
            <span class="value">${formatNumber(unit.hass, value, spec.digits)}<small>${esc(unitText)}</small></span>
          </div>
          <div class="track">
            ${band(spec.warn ?? 0, "warn")}${band(spec.ok ?? 0, "ok")}
            ${value !== undefined ? `<div class="marker" style="left:${pos(value)}"></div>` : ""}
          </div>
          <div class="foot">
            <span>${formatNumber(unit.hass, spec.min, spec.digits ? 1 : 0)}</span>
            <span>${required !== undefined ? `${esc(t.target)} ${formatNumber(unit.hass, required, spec.digits)}` : ""}</span>
            <span>${formatNumber(unit.hass, spec.max, spec.digits ? 1 : 0)}</span>
          </div>
        </div>`;
    });
    this.shadowRoot.innerHTML = `
      <style>
        ${SHARED_CSS}
        ha-card { padding: var(--aseko-pad, 20px); }
        .grid { display: grid; grid-template-columns: var(--aseko-quality-columns, 1fr); gap: var(--aseko-gap, 22px) 24px; }
        .metric { cursor: pointer; }
        .head { display: flex; justify-content: space-between; align-items: baseline; }
        .label { font-weight: 500; }
        .value { font-size: 28px; font-weight: 600; color: var(--tone); font-variant-numeric: tabular-nums; }
        .s-neutral .value { color: var(--primary-text-color); }
        .value small { font-size: 13px; font-weight: 500; margin-left: 4px; color: var(--secondary-text-color); }
        .track {
          position: relative; height: 10px; margin: 10px 0 6px; border-radius: 999px;
          background: color-mix(in srgb, var(--aseko-bad) 22%, var(--card-background-color));
        }
        .s-neutral .track { background: color-mix(in srgb, var(--aseko-blue) 18%, var(--card-background-color)); }
        .band { position: absolute; top: 0; bottom: 0; border-radius: 999px; }
        .band.warn { background: color-mix(in srgb, var(--aseko-warn) 45%, var(--card-background-color)); }
        .band.ok { background: var(--aseko-ok); }
        .marker {
          position: absolute; top: 50%; width: 18px; height: 18px; border-radius: 50%; transform: translate(-50%, -50%);
          background: var(--card-background-color); border: 4px solid var(--tone); box-sizing: border-box;
          box-shadow: 0 0 0 4px color-mix(in srgb, var(--tone) 25%, transparent), 0 2px 6px rgba(0,0,0,.3);
          transition: left .6s cubic-bezier(.2,.8,.2,1);
        }
        .s-neutral .marker { --tone: var(--aseko-blue); }
        .foot { display: flex; justify-content: space-between; font-size: 12px; color: var(--secondary-text-color); }
      </style>
      <ha-card>
        <div class="title">${esc(t.waterQuality)}</div>
        <div class="grid">${rows.join("")}</div>
      </ha-card>`;
    this.bindMoreInfo();
  }

  getGridOptions() {
    return { columns: "full" };
  }
}

// ---------------------------------------------------------------- filtration + equipment card

class AsekoOperationCard extends AsekoCard {
  render(unit, t) {
    const f = unit.filtration();
    const start = minutes(f.start);
    const end = minutes(f.end);
    const now = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    const pct = (m) => (m / 1440) * 100;
    let windows = [];
    if (f.nonstop) {
      windows = [[0, 1440]];
    } else if (start !== undefined && end !== undefined) {
      windows = end > start ? [[start, end]] : [[start, 1440], [0, end]];
    }
    const status = f.nonstop
      ? t.nonstop
      : f.running
        ? `${t.running}${f.end ? ` ${t.until} ${f.end}` : ""}`
        : f.start
          ? `${t.scheduled} ${f.start}${f.end ? `–${f.end}` : ""}`
          : t.noSchedule;
    const equipment = EQUIPMENT.filter(([key]) => unit.id(key));
    this.shadowRoot.innerHTML = `
      <style>
        ${SHARED_CSS}
        ha-card { padding: var(--aseko-pad, 20px); }
        .status { display: flex; align-items: center; gap: 10px; font-size: 18px; font-weight: 600; cursor: pointer; }
        .status ha-icon { color: var(--aseko-blue); }
        .status.on ha-icon { animation: spin 2.4s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .speed { margin-left: auto; font-size: 13px; font-weight: 500; color: var(--secondary-text-color); }
        .timeline { position: relative; height: 34px; margin: 18px 0 6px; border-radius: 10px;
          background: repeating-linear-gradient(90deg, color-mix(in srgb, var(--primary-text-color) 7%, transparent) 0 1px, transparent 1px calc(100% / 24)),
            color-mix(in srgb, var(--primary-text-color) 5%, transparent); }
        .win { position: absolute; top: 4px; bottom: 4px; border-radius: 7px;
          background: linear-gradient(90deg, var(--aseko-blue), var(--aseko-cyan));
          box-shadow: 0 0 14px color-mix(in srgb, var(--aseko-cyan) 50%, transparent); }
        .win.idle { opacity: .45; box-shadow: none; }
        .now { position: absolute; top: -4px; bottom: -4px; width: 2px; background: var(--primary-text-color); border-radius: 2px; }
        .now::after { content: ""; position: absolute; top: -4px; left: -3px; width: 8px; height: 8px; border-radius: 50%; background: inherit; }
        .hours { display: flex; justify-content: space-between; font-size: 11px; color: var(--secondary-text-color); }
        .equip { display: grid; grid-template-columns: repeat(auto-fill, minmax(118px, 1fr)); gap: 10px; margin-top: var(--aseko-gap, 22px); }
        .eq { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-radius: 12px; cursor: pointer;
          background: color-mix(in srgb, var(--primary-text-color) 5%, transparent); font-size: 13px; color: var(--secondary-text-color); }
        .eq ha-icon { --mdc-icon-size: 20px; }
        .eq.on { color: var(--primary-text-color); background: color-mix(in srgb, var(--aseko-blue) 18%, transparent); }
        .eq.on ha-icon { color: var(--aseko-cyan); filter: drop-shadow(0 0 6px var(--aseko-cyan)); }
        .extra { display: var(--aseko-extra, flex); flex-wrap: wrap; gap: 16px; margin-top: var(--aseko-gap, 18px); font-size: 13px; color: var(--secondary-text-color); }
        .extra b { color: var(--primary-text-color); font-weight: 600; margin-left: 4px; }
        .extra div { cursor: pointer; }
      </style>
      <ha-card>
        <div class="title">${esc(t.filtration)}</div>
        <div class="status ${f.running || f.nonstop ? "on" : ""}" data-entity="${esc(unit.id("binary_sensor.filtration") || "")}">
          <ha-icon icon="mdi:fan"></ha-icon>${esc(status)}
          ${f.speed ? `<span class="speed">${esc(unit.label("sensor.filtration_speed"))}: ${esc(f.speed)}</span>` : ""}
        </div>
        <div class="timeline">
          ${windows.map(([a, b]) => `<div class="win ${f.running || f.nonstop ? "" : "idle"}" style="left:${pct(a)}%;width:${pct(b - a)}%"></div>`).join("")}
          <div class="now" style="left:${pct(nowMin)}%"></div>
        </div>
        <div class="hours"><span>0</span><span>6</span><span>12</span><span>18</span><span>24</span></div>
        <div class="extra">
          ${["sensor.filter_pressure", "sensor.filter_flow_speed", "sensor.pool_flow", "sensor.water_level", "sensor.electrode_power"]
            .filter((key) => unit.id(key))
            .map((key) => `<div data-entity="${esc(unit.id(key))}">${esc(unit.label(key))}<b>${esc(unit.formatted(key))}</b></div>`)
            .join("")}
        </div>
        ${
          equipment.length
            ? `<div class="title" style="margin-top:var(--aseko-gap, 24px)">${esc(t.equipment)}</div>
               <div class="equip" style="margin-top:0">
                 ${equipment
                   .map(
                     ([key, icon]) => `<div class="eq ${unit.on(key) ? "on" : ""}" data-entity="${esc(unit.id(key))}">
                       <ha-icon icon="${icon}"></ha-icon>${esc(unit.label(key))}</div>`,
                   )
                   .join("")}
               </div>`
            : ""
        }
      </ha-card>`;
    this.bindMoreInfo();
  }

  connectedCallback() {
    this._tick = setInterval(() => {
      this._signature = undefined;
      if (this._hass) {
        this.hass = this._hass;
      }
    }, 60 * 1000);
  }

  disconnectedCallback() {
    clearInterval(this._tick);
  }

  getGridOptions() {
    return { columns: "full" };
  }
}

// ---------------------------------------------------------------- messages card

const SEVERITY = {
  ERROR: ["bad", "mdi:alert-octagon"],
  WARNING: ["warn", "mdi:alert"],
  INFO: ["neutral", "mdi:information"],
};

class AsekoMessagesCard extends AsekoCard {
  render(unit, t) {
    const messages = unit.messages();
    const settings = ["sensor.ph_required", "sensor.redox_required", "sensor.cl_free_required", "sensor.water_temperature_required"]
      .filter((key) => unit.id(key));
    this.shadowRoot.innerHTML = `
      <style>
        ${SHARED_CSS}
        ha-card { padding: 20px; }
        .msg { display: grid; grid-template-columns: 28px 1fr; gap: 4px 10px; padding: 12px 14px; border-radius: 12px; margin-bottom: 10px;
          background: color-mix(in srgb, var(--tone) 12%, transparent); border-left: 3px solid var(--tone); }
        .s-neutral { --tone: var(--aseko-blue); }
        .msg ha-icon { color: var(--tone); grid-row: span 2; }
        .msg b { font-weight: 600; }
        .msg span { font-size: 13px; color: var(--secondary-text-color); }
        .empty { display: flex; align-items: center; gap: 10px; color: var(--secondary-text-color); }
        .empty ha-icon { color: var(--aseko-ok); }
        .settings { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 10px; }
        .set { padding: 10px 12px; border-radius: 12px; cursor: pointer; background: color-mix(in srgb, var(--primary-text-color) 5%, transparent); }
        .set span { display: block; font-size: 12px; color: var(--secondary-text-color); }
        .set b { font-size: 18px; font-weight: 600; }
      </style>
      <ha-card>
        <div class="title">${esc(t.messages)}</div>
        ${
          messages.length
            ? messages
                .map((m) => {
                  const [tone, icon] = SEVERITY[m.severity] || SEVERITY.INFO;
                  return `<div class="msg s-${tone}"><ha-icon icon="${icon}"></ha-icon><b>${esc(m.message)}</b><span>${esc(m.detail || "")}</span></div>`;
                })
                .join("")
            : `<div class="empty"><ha-icon icon="mdi:check-circle"></ha-icon>${esc(t.noMessages)}</div>`
        }
        ${
          settings.length
            ? `<div class="title" style="margin-top:22px">${esc(t.settings)}</div>
               <div class="settings">${settings
                 .map((key) => `<div class="set" data-entity="${esc(unit.id(key))}"><span>${esc(unit.label(key))}</span><b>${esc(unit.formatted(key))}</b></div>`)
                 .join("")}</div>`
            : ""
        }
      </ha-card>`;
    this.bindMoreInfo();
  }

  getGridOptions() {
    return { columns: "full" };
  }
}

// ---------------------------------------------------------------- history chart card

class AsekoHistoryCard extends AsekoCard {
  setConfig(config) {
    super.setConfig(config);
    this._selected = config.metric || undefined;
    this._history = {};
  }

  connectedCallback() {
    this._timer = setInterval(() => this._load(true), REFRESH_HISTORY_MS);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    const unit = new Unit(hass, this._config.device_id);
    const series = this._series(unit);
    if (!this._selected || !series.find((s) => s.key === this._selected)) {
      this._selected = series[0]?.key;
    }
    if (first) {
      this._load(false);
    }
    const signature = `${this._selected}|${unit.signature()}|${this._loadedAt || ""}`;
    if (signature !== this._signature) {
      this._signature = signature;
      this.render(unit, texts(hass), series);
    }
  }

  _series(unit) {
    return [
      { key: "ph", entity: "sensor.ph", digits: 1 },
      { key: "redox", entity: "sensor.redox", digits: 0 },
      { key: "cl_free", entity: "sensor.cl_free", digits: 2 },
      { key: "water_temperature", entity: "sensor.water_temperature", digits: 1 },
    ].filter((s) => unit.id(s.entity));
  }

  async _load(force) {
    if (!this._hass || (this._loading && !force)) {
      return;
    }
    this._loading = true;
    const unit = new Unit(this._hass, this._config.device_id);
    const ids = this._series(unit).map((s) => unit.id(s.entity));
    if (!ids.length) {
      return;
    }
    const end = new Date();
    const start = new Date(end.getTime() - 48 * 3600 * 1000);
    try {
      const result = await this._hass.callWS({
        type: "history/history_during_period",
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        entity_ids: ids,
        minimal_response: true,
        no_attributes: true,
        significant_changes_only: false,
      });
      this._history = {};
      for (const [id, points] of Object.entries(result)) {
        this._history[id] = points
          .map((p) => [((p.lu ?? p.lc) || 0) * 1000, Number.parseFloat(p.s)])
          .filter(([time, value]) => time && Number.isFinite(value));
      }
      this._range = [start.getTime(), end.getTime()];
      this._loadedAt = end.getTime();
    } catch (err) {
      this._history = {};
    }
    this._loading = false;
    this._signature = undefined;
    this.hass = this._hass;
  }

  render(unit, t, series) {
    const current = series.find((s) => s.key === this._selected);
    const tabs = series
      .map(
        (s) => `<button class="${s.key === this._selected ? "active" : ""}" data-key="${s.key}">${esc(
          s.key === "water_temperature" ? t.temperature : unit.label(s.entity),
        )}</button>`,
      )
      .join("");
    let chart = `<div class="empty">${esc(t.noData)}</div>`;
    if (current && this._range) {
      const id = unit.id(current.entity);
      const points = [...(this._history[id] || [])];
      const live = unit.number(current.entity);
      if (live !== undefined) {
        points.push([this._range[1], live]);
      }
      const spec = METRICS[current.key];
      const required = spec?.required ? unit.number(`sensor.${spec.required}`) : undefined;
      if (points.length >= 2) {
        chart = this._chart(points, required, spec, current.digits, unit.hass);
      }
    }
    this.shadowRoot.innerHTML = `
      <style>
        ${SHARED_CSS}
        ha-card { padding: 20px; }
        .tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }
        button { font: inherit; font-size: 13px; padding: 6px 12px; border-radius: 999px; border: none; cursor: pointer;
          color: var(--secondary-text-color); background: color-mix(in srgb, var(--primary-text-color) 6%, transparent); }
        button.active { color: #fff; background: var(--aseko-blue); }
        .wrap { position: relative; }
        svg { width: 100%; height: 220px; display: block; overflow: visible; }
        .area { fill: url(#fill); }
        .line { fill: none; stroke: var(--aseko-blue); stroke-width: 2.5; vector-effect: non-scaling-stroke; stroke-linejoin: round; }
        .band { fill: var(--aseko-ok); opacity: .14; }
        .target { stroke: var(--aseko-ok); stroke-dasharray: 4 4; stroke-width: 1.5; vector-effect: non-scaling-stroke; }
        .grid line { stroke: color-mix(in srgb, var(--primary-text-color) 8%, transparent); vector-effect: non-scaling-stroke; }
        .labels { position: absolute; inset: 0; pointer-events: none; font-size: 11px; color: var(--secondary-text-color); }
        .labels span { position: absolute; transform: translateY(-50%); right: 0; background: var(--card-background-color); padding: 0 2px; }
        .axis { display: flex; justify-content: space-between; font-size: 11px; color: var(--secondary-text-color); margin-top: 6px; }
        .empty { height: 220px; display: grid; place-items: center; color: var(--secondary-text-color); }
      </style>
      <ha-card>
        <div class="title">${esc(t.history)}</div>
        <div class="tabs">${tabs}</div>
        ${chart}
      </ha-card>`;
    this.shadowRoot.querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => {
        this._selected = b.dataset.key;
        this._signature = undefined;
        this.hass = this._hass;
      }),
    );
  }

  _chart(points, required, spec, digits, hass) {
    const t1 = this._range[1];
    const t0 = Math.max(this._range[0], points[0][0] - (t1 - points[0][0]) * 0.05);
    const values = points.map(([, v]) => v);
    let lo = Math.min(...values);
    let hi = Math.max(...values);
    if (required !== undefined) {
      lo = Math.min(lo, required - spec.ok);
      hi = Math.max(hi, required + spec.ok);
    }
    const pad = (hi - lo || 1) * 0.15;
    lo -= pad;
    hi += pad;
    const W = 1000;
    const H = 220;
    const x = (time) => ((time - t0) / (t1 - t0)) * W;
    const y = (v) => H - ((v - lo) / (hi - lo)) * H;
    // Sensor history is a step function: hold each value until the next one.
    let d = `M${x(points[0][0]).toFixed(1)},${y(points[0][1]).toFixed(1)}`;
    for (let i = 1; i < points.length; i += 1) {
      d += ` H${x(points[i][0]).toFixed(1)} V${y(points[i][1]).toFixed(1)}`;
    }
    const area = `${d} V${H} H${x(points[0][0]).toFixed(1)} Z`;
    const ticks = [0.25, 0.5, 0.75].map((f) => lo + (hi - lo) * (1 - f));
    const band =
      required !== undefined
        ? `<rect class="band" x="0" width="${W}" y="${y(required + spec.ok)}" height="${y(required - spec.ok) - y(required + spec.ok)}"/>
           <line class="target" x1="0" x2="${W}" y1="${y(required)}" y2="${y(required)}"/>`
        : "";
    const timeFmt = new Intl.DateTimeFormat(hass.locale?.language || "en", { weekday: "short", hour: "2-digit", minute: "2-digit" });
    const axis = [0, 0.5, 1].map((f) => timeFmt.format(new Date(t0 + (t1 - t0) * f)));
    return `
      <div class="wrap">
        <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
          <defs><linearGradient id="fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stop-color="#149fe2" stop-opacity=".35"/><stop offset="1" stop-color="#149fe2" stop-opacity="0"/>
          </linearGradient></defs>
          <g class="grid">${ticks.map((v) => `<line x1="0" x2="${W}" y1="${y(v)}" y2="${y(v)}"/>`).join("")}</g>
          ${band}
          <path class="area" d="${area}"/>
          <path class="line" d="${d}"/>
        </svg>
        <div class="labels">${ticks
          .map((v) => `<span style="top:${(y(v) / H) * 100}%">${formatNumber(hass, v, digits)}</span>`)
          .join("")}</div>
      </div>
      <div class="axis">${axis.map((a) => `<span>${esc(a)}</span>`).join("")}</div>`;
  }

  getGridOptions() {
    return { columns: "full" };
  }
}

// ---------------------------------------------------------------- showcase (TV / kiosk)

class AsekoShowcaseCard extends HTMLElement {
  setConfig(config) {
    this._config = { rotate_seconds: 20, ...config };
    this._index = 0;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this._build();
    }
    this._update();
  }

  connectedCallback() {
    this._startTimer();
    this._clockTimer = setInterval(() => this._updateClock(), 15 * 1000);
    if (kioskWanted()) {
      applyKiosk();
    }
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    clearInterval(this._clockTimer);
    removeKiosk();
  }

  _devices() {
    const devices = asekoDevices(this._hass);
    const online = devices.filter((device) => {
      const unit = new Unit(this._hass, device.id);
      return !unit.id("binary_sensor.online") || unit.on("binary_sensor.online");
    });
    return online.length ? online : devices;
  }

  _startTimer() {
    clearInterval(this._timer);
    this._timer = setInterval(() => this._next(), this._config.rotate_seconds * 1000);
  }

  _next() {
    this._show(this._index + 1);
  }

  // Manual switching restarts the countdown so the chosen unit stays a while.
  _show(index, manual = false) {
    const count = this._devices().length;
    if (count > 1) {
      this._index = (index + count) % count;
      this._signature = undefined;
      this._update(true);
    }
    if (manual) {
      this._startTimer();
    }
  }

  _bindGestures() {
    const slot = this.shadowRoot.querySelector(".hero-slot");
    let start;
    slot.addEventListener("pointerdown", (ev) => {
      start = { x: ev.clientX, y: ev.clientY };
      this._swiped = false;
    });
    slot.addEventListener("pointerup", (ev) => {
      if (!start) {
        return;
      }
      const dx = ev.clientX - start.x;
      const dy = ev.clientY - start.y;
      start = undefined;
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy)) {
        this._swiped = true;
        this._show(this._index + (dx < 0 ? 1 : -1), true);
      }
    });
    // A swipe must not also open the entity under the finger.
    slot.addEventListener(
      "click",
      (ev) => {
        if (this._swiped) {
          this._swiped = false;
          ev.stopPropagation();
        }
      },
      true,
    );
    this.shadowRoot.querySelector(".dots").addEventListener("click", (ev) => {
      const dot = ev.target.closest("[data-index]");
      if (dot) {
        this._show(Number(dot.dataset.index), true);
      }
    });
  }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>
        ${SHARED_CSS}${HERO_CSS}${IDLE_CSS}
        :host { height: 100%; }
        .stage[hidden], .idle-host[hidden] { display: none; }
        .idle-host { display: flex; box-sizing: border-box; padding: 24px; min-height: calc(100vh - var(--header-height, 56px));
          background: var(--primary-background-color); }
        .idle-host.kiosk { min-height: 100vh; }
        .idle-host .hero { flex: 1; }
        .stage { min-height: calc(100vh - var(--header-height, 56px)); box-sizing: border-box; padding: 24px;
          display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); grid-template-rows: auto 1fr; gap: 20px;
          background: radial-gradient(1200px 600px at 10% -10%, color-mix(in srgb, var(--aseko-blue) 18%, transparent), transparent),
            var(--primary-background-color); }
        .stage.kiosk { min-height: 100vh; }
        .hero-slot { grid-column: 1; grid-row: 1 / span 2; display: flex; flex-direction: column; gap: 20px; touch-action: pan-y; user-select: none; }
        .hero-host { flex: 1; display: flex; }
        .hero-host .hero { flex: 1; display: flex; flex-direction: column; justify-content: space-between; }
        .fade { animation: fade .8s ease; }
        @keyframes fade { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
        .panel { display: flex; flex-direction: column; gap: 20px; }
        .dots { display: flex; justify-content: center; }
        .dots span { padding: 6px 4px; cursor: pointer; }
        .dots i { display: block; width: 8px; height: 8px; border-radius: 50%; background: color-mix(in srgb, var(--primary-text-color) 25%, transparent); transition: all .3s; }
        .dots i.on { width: 26px; border-radius: 999px; background: var(--aseko-blue); }
        .brand { display: flex; align-items: center; justify-content: flex-end; font-size: 13px; color: var(--secondary-text-color);
          letter-spacing: .12em; text-transform: uppercase; }

        .brand b { font-size: 22px; letter-spacing: -.02em; text-transform: none; color: var(--primary-text-color); }
        @media (max-width: 900px) { .stage { grid-template-columns: 1fr; } .hero-slot { grid-row: auto; } }
        @media (max-height: 900px) {
          .stage { padding: 16px; gap: 14px; --aseko-pad: 16px; --aseko-gap: 12px; --aseko-title-gap: 8px; --aseko-extra: none;
            --aseko-quality-columns: repeat(2, minmax(0, 1fr)); }
          .hero.large .main { flex-direction: column; align-items: stretch; }
          .hero.large .side { grid-template-columns: repeat(2, minmax(0, 1fr)); min-width: 0; }
          .hero-slot, .panel { gap: 12px; }
          .hero.large { min-height: 0; padding: 24px 28px 28px; }
          .hero.large .logo { height: 30px; margin-bottom: 14px; }
          .hero.large .name { font-size: 28px; }
          .hero.large .temp .value { font-size: 112px; }
          .hero.large .temp .deg { font-size: 38px; }
          .hero.large .temp .sub { font-size: 17px; }
          .hero.large .side { gap: 8px; min-width: 280px; }
          .hero.large .mini { font-size: 15px; padding: 9px 14px; }
        }
      </style>
      <div class="idle-host" hidden></div>
      <div class="stage">
        <div class="hero-slot"><div class="hero-host"></div><div class="dots"></div></div>
        <div class="panel">
          <div class="brand"><span class="clock"></span></div>
          <aseko-quality-card></aseko-quality-card>
          <aseko-operation-card></aseko-operation-card>
        </div>
      </div>`;
    if (kioskWanted()) {
      this.shadowRoot.querySelector(".stage").classList.add("kiosk");
      this.shadowRoot.querySelector(".idle-host").classList.add("kiosk");
    }
    this._bindGestures();
  }

  _update(animate = false) {
    const devices = this._devices();
    const idle = this.shadowRoot.querySelector(".idle-host");
    const stage = this.shadowRoot.querySelector(".stage");
    if (!devices.length) {
      const signature = `idle|${this._hass.locale?.language}`;
      if (signature !== this._signature) {
        this._signature = signature;
        idle.innerHTML = idleMarkup(texts(this._hass), { image: this._config.unit_images?.default ?? DEFAULT_UNIT_IMAGE, clock: true });
      }
      idle.hidden = false;
      stage.hidden = true;
      this._updateClock();
      return;
    }
    idle.hidden = true;
    stage.hidden = false;
    this._index %= devices.length;
    const device = devices[this._index];
    const unit = new Unit(this._hass, device.id);
    const signature = `${devices.map((d) => d.id).join(",")}|${device.id}|${unit.signature()}`;
    const host = this.shadowRoot.querySelector(".hero-host");
    if (signature !== this._signature) {
      this._signature = signature;
      host.innerHTML = heroMarkup(unit, texts(this._hass), { large: true, image: unitImage(this._config.unit_images, device) });
      host.querySelectorAll("[data-entity]").forEach((el) => el.addEventListener("click", () => moreInfo(this, el.dataset.entity)));
      if (animate) {
        this.shadowRoot.querySelectorAll(".hero-host, aseko-quality-card, aseko-operation-card").forEach((el) => {
          el.classList.remove("fade");
          void el.offsetWidth;
          el.classList.add("fade");
        });
      }
      this.shadowRoot.querySelector(".dots").innerHTML = devices.map((_, i) => `<span data-index="${i}"><i class="${i === this._index ? "on" : ""}"></i></span>`).join("");
    }
    for (const tag of ["aseko-quality-card", "aseko-operation-card"]) {
      const card = this.shadowRoot.querySelector(tag);
      if (card._config?.device_id !== device.id) {
        card.setConfig({ device_id: device.id });
      }
      card.hass = this._hass;
    }
    this._fit();
    this._updateClock();
  }

  _updateClock() {
    if (!this._hass || !this.shadowRoot) {
      return;
    }
    const now = new Intl.DateTimeFormat(this._hass.locale?.language || "en", {
      weekday: "long",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date());
    this.shadowRoot.querySelectorAll(".clock").forEach((el) => {
      el.textContent = now;
    });
  }

  // On a wall display the whole showcase must stay on screen whatever the unit
  // reports, so it is scaled down when its content would overflow.
  _fit() {
    const stage = this.shadowRoot.querySelector(".stage");
    if (!kioskWanted()) {
      return;
    }
    requestAnimationFrame(() => {
      stage.style.zoom = "";
      const overflow = stage.scrollHeight / window.innerHeight;
      if (overflow > 1) {
        stage.style.zoom = String(1 / overflow);
      }
    });
  }

  getCardSize() {
    return 12;
  }
}

// Hides the HA header and sidebar while the showcase is open, for a wall
// display: with ?kiosk in the URL, or always in the Home Assistant app on a
// tablet. Leaving the showcase brings them back; nothing is persisted.
const KIOSK_ID = "aseko-kiosk";

function kioskWanted() {
  return new URLSearchParams(window.location.search).has("kiosk") || /Home ?Assistant\//i.test(navigator.userAgent);
}

function kioskRoots() {
  const main = document.querySelector("home-assistant")?.shadowRoot?.querySelector("home-assistant-main");
  const panel = main?.shadowRoot?.querySelector("partial-panel-resolver")?.querySelector("ha-panel-lovelace");
  return {
    drawer: main?.shadowRoot?.querySelector("ha-drawer")?.shadowRoot,
    root: panel?.shadowRoot?.querySelector("hui-root")?.shadowRoot,
  };
}

function applyKiosk() {
  const css = (root, rules) => {
    if (root && !root.getElementById(KIOSK_ID)) {
      const style = document.createElement("style");
      style.id = KIOSK_ID;
      style.textContent = rules;
      root.appendChild(style);
    }
  };
  const attempt = (tries) => {
    const { drawer, root } = kioskRoots();
    css(drawer, ".sidebar-shell { display: none !important; } .app-content { padding-inline-start: 0 !important; padding-left: 0 !important; }");
    css(root, ".header { display: none !important; } #view { padding-top: 0 !important; min-height: 100vh !important; }");
    if ((!drawer || !root) && tries > 0) {
      setTimeout(() => attempt(tries - 1), 300);
    }
  };
  attempt(20);
}

function removeKiosk() {
  const { drawer, root } = kioskRoots();
  drawer?.getElementById(KIOSK_ID)?.remove();
  root?.getElementById(KIOSK_ID)?.remove();
}

// ---------------------------------------------------------------- strategy

function strategySection(cards, span = 2) {
  return { type: "grid", column_span: span, cards };
}

class AsekoPoolDashboardStrategy extends HTMLElement {
  static async generate(config, hass) {
    strategyLanguage = hass.locale?.language;
    const t = texts(hass);
    const devices = asekoDevices(hass);
    const theme = config.theme;
    const images = config.unit_images;
    const overview = {
      title: t.overview,
      path: "overview",
      icon: "mdi:pool",
      theme,
      type: "sections",
      max_columns: 2,
      sections: devices.length
        ? devices.map((device) => ({
            type: "grid",
            cards: [{ type: "custom:aseko-summary-card", device_id: device.id, navigation_path: unitPath(device), image: unitImage(images, device) }],
          }))
        : [{ type: "grid", column_span: 3, cards: [{ type: "custom:aseko-empty-card", image: images?.default ?? DEFAULT_UNIT_IMAGE }] }],
    };
    const showcase = {
      title: t.showcase,
      path: "showcase",
      icon: "mdi:television-play",
      theme,
      panel: true,
      cards: [{ type: "custom:aseko-showcase-card", rotate_seconds: config.rotate_seconds || 20, unit_images: images }],
    };
    const unitViews = devices.map((device) => {
      const card = (type) => ({ type: `custom:${type}`, device_id: device.id });
      return {
        title: deviceName(device),
        path: unitPath(device),
        icon: "mdi:pool",
        subview: true,
        theme,
        type: "sections",
        max_columns: 4,
        sections: [
          strategySection([{ ...card("aseko-hero-card"), image: unitImage(images, device) }], 4),
          strategySection([card("aseko-quality-card")]),
          strategySection([card("aseko-operation-card")]),
          strategySection([card("aseko-history-card")]),
          strategySection([card("aseko-messages-card")]),
        ],
      };
    });
    return { views: [overview, showcase, ...unitViews] };
  }
}

const ELEMENTS = {
  "aseko-hero-card": AsekoHeroCard,
  "aseko-summary-card": AsekoSummaryCard,
  "aseko-quality-card": AsekoQualityCard,
  "aseko-operation-card": AsekoOperationCard,
  "aseko-messages-card": AsekoMessagesCard,
  "aseko-history-card": AsekoHistoryCard,
  "aseko-showcase-card": AsekoShowcaseCard,
  "aseko-empty-card": AsekoEmptyCard,
  "ll-strategy-dashboard-aseko-pool": AsekoPoolDashboardStrategy,
};

for (const [tag, element] of Object.entries(ELEMENTS)) {
  if (!customElements.get(tag)) {
    customElements.define(tag, element);
  }
}

watchLanguage();

window.customCards = window.customCards || [];
for (const [type, name] of [
  ["aseko-hero-card", "Aseko pool"],
  ["aseko-summary-card", "Aseko pool summary"],
  ["aseko-quality-card", "Aseko water quality"],
  ["aseko-operation-card", "Aseko filtration & equipment"],
  ["aseko-messages-card", "Aseko messages"],
  ["aseko-history-card", "Aseko history"],
  ["aseko-showcase-card", "Aseko showcase"],
]) {
  if (!window.customCards.some((c) => c.type === type)) {
    window.customCards.push({ type, name, description: "Aseko Cloud pool dashboard card" });
  }
}

export { AsekoPoolDashboardStrategy };
