/* Frickelalarm – Lovelace-Karte im Frickelfabrik-Look.
   Vanilla Custom Element, keine Build-Kette. Konfig: { type, entity, name? } */

const STATES = {
  disarmed:       { label: "Unscharf",            accent: "#2f7d6b", grad: "#256055", tri: false },
  arming:         { label: "Wird scharf …",       accent: "#d4870a", grad: "#b5720a", tri: false },
  pending:        { label: "Eingang – unscharf schalten", accent: "#d4870a", grad: "#b5720a", tri: true },
  armed_home:     { label: "Zuhause scharf",       accent: "#1f3b39", grad: "#0e2b2a", tri: false },
  armed_away:     { label: "Abwesend scharf",      accent: "#1f3b39", grad: "#0e2b2a", tri: false },
  armed_night:    { label: "Nacht scharf",         accent: "#1f3b39", grad: "#0e2b2a", tri: false },
  armed_vacation: { label: "Urlaub scharf",        accent: "#1f3b39", grad: "#0e2b2a", tri: false },
  triggered:      { label: "ALARM!",               accent: "#c0392b", grad: "#8c2318", tri: true },
  unavailable:    { label: "Nicht verfügbar",      accent: "#7a8a87", grad: "#5a6b68", tri: false },
};

const ICONS = {
  home: '<path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z"/>',
  away: '<path d="M10 3h8a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1h-8v-2h7V5h-7zM4 12l4-4v3h6v2H8v3z"/>',
  night: '<path d="M12 3a9 9 0 1 0 9 9c0-.5 0-1-.1-1.5A7 7 0 0 1 12.5 3.1 9 9 0 0 0 12 3z"/>',
  vacation: '<circle cx="12" cy="12" r="4"/><g stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none"><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5 5l1.8 1.8M17.2 17.2 19 19M19 5l-1.8 1.8M6.8 17.2 5 19"/></g>',
  disarm: '<path d="M17 9V7A5 5 0 0 0 7.1 6H9.3A3 3 0 0 1 15 7v2H6a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-9a1 1 0 0 0-1-1z"/>',
};

const ARM_BUTTONS = [
  { svc: "alarm_arm_home", label: "Zuhause", mode: "armed_home", icon: "home" },
  { svc: "alarm_arm_away", label: "Abwesend", mode: "armed_away", icon: "away" },
  { svc: "alarm_arm_night", label: "Nacht", mode: "armed_night", icon: "night" },
  { svc: "alarm_arm_vacation", label: "Urlaub", mode: "armed_vacation", icon: "vacation" },
];

const svg = (inner) => `<svg viewBox="0 0 24 24" fill="currentColor">${inner}</svg>`;

class FrickelalarmCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.entity) throw new Error("Bitte eine 'entity' angeben (alarm_control_panel.…)");
    this._config = config;
    if (!this._root) this._root = this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() { return 5; }

  _call(service) {
    const data = { entity_id: this._config.entity };
    const code = this._root.getElementById("code");
    if (code && code.value) data.code = code.value;
    this._hass.callService("alarm_control_panel", service, data);
    if (code) code.value = "";
  }

  _render() {
    if (!this._hass || !this._config) return;
    const st = this._hass.states[this._config.entity];
    const state = st ? st.state : "unavailable";
    const meta = STATES[state] || STATES.unavailable;
    const a = st ? st.attributes : {};
    const name = this._config.name || a.friendly_name || "Frickelalarm";
    const rest = a.restzeit_s;
    const reason = a.ausloeser;
    const activeMode = a.modus;
    const offen = a.offene_sensoren || [];
    const umgangen = a.umgangene_sensoren || [];
    const needCode = !!a.code_format;
    const showCount = rest != null && (meta.tri || state === "arming");

    this._root.innerHTML = `
      <style>
        :host { --petrol:#0e3b3a; --amber:#f0b44c; --amber2:#d4870a; --ink:#16302e; --muted:#5a6b68; }
        ha-card { overflow:hidden; border-radius:18px; }
        .head { position:relative; background:linear-gradient(135deg, ${meta.accent}, ${meta.grad}); color:#fff; padding:20px; display:flex; align-items:center; gap:16px; }
        ${meta.tri ? ".head::after{content:'';position:absolute;inset:0;background:#fff;opacity:0;animation:flash 1.1s infinite;pointer-events:none}@keyframes flash{0%,100%{opacity:0}50%{opacity:.14}}" : ""}
        .badge { width:52px; height:52px; border-radius:50%; background:rgba(255,255,255,.16); display:flex; align-items:center; justify-content:center; flex:0 0 auto; }
        .badge svg { width:30px; height:30px; fill:#fff; }
        .htxt { line-height:1.25; min-width:0; }
        .state { font-size:1.5rem; font-weight:800; letter-spacing:.2px; }
        .area { font-size:.9rem; opacity:.85; }
        .count { margin-left:auto; text-align:center; flex:0 0 auto; }
        .count .n { font-size:2rem; font-weight:800; font-variant-numeric:tabular-nums; line-height:1; }
        .count .u { font-size:.7rem; opacity:.85; text-transform:uppercase; letter-spacing:1px; }
        .body { padding:18px 20px 8px; }
        .reason { background:#fbeae7; color:#8c2e22; font-weight:600; padding:8px 12px; border-radius:10px; margin-bottom:14px; font-size:.9rem; }
        .grid { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }
        .mode { display:flex; flex-direction:column; align-items:center; gap:6px; cursor:pointer; border:2px solid transparent; border-radius:14px; padding:12px 4px; background:#eef3f1; color:var(--petrol); font:inherit; font-weight:600; font-size:.82rem; transition:all .15s; }
        .mode svg { width:22px; height:22px; fill:currentColor; opacity:.9; }
        .mode:hover { background:#e1ebe7; transform:translateY(-1px); }
        .mode:active { transform:translateY(0); }
        .mode.active { background:var(--petrol); color:#fff; border-color:var(--amber); box-shadow:0 4px 14px rgba(14,59,58,.3); }
        .disarm { width:100%; margin-top:12px; display:flex; align-items:center; justify-content:center; gap:10px; cursor:pointer; border:none; border-radius:14px; padding:15px; font:inherit; font-weight:800; font-size:1rem; color:var(--petrol); background:var(--amber); transition:all .15s; }
        .disarm svg { width:22px; height:22px; fill:currentColor; }
        .disarm:hover { background:var(--amber2); color:#fff; }
        .disarm:active { transform:translateY(1px); }
        .code { width:100%; box-sizing:border-box; margin-top:12px; padding:13px 14px; border:1px solid #cfdcd8; border-radius:12px; font:inherit; font-size:1rem; outline:none; transition:border-color .15s; }
        .code:focus { border-color:var(--amber2); }
        .chips { margin-top:14px; font-size:.82rem; color:var(--muted); }
        .chips .lbl { font-weight:600; margin-right:4px; }
        .chip { display:inline-block; border-radius:8px; padding:3px 9px; margin:3px 5px 0 0; font-size:.78rem; }
        .chip.open { background:#f6d9d4; color:#8c2e22; }
        .chip.byp { background:#f0e2c6; color:#7a5a12; }
        .foot { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-top:14px; padding:12px 20px; border-top:1px solid #edf1ef; background:#f7faf9; }
        .wm { font-weight:800; font-size:.92rem; letter-spacing:.2px; }
        .wm b { font-weight:800; }
        .wm .p { color:var(--petrol); } .wm .a { color:var(--amber2); }
        .foot a { color:var(--muted); font-size:.75rem; text-decoration:none; }
        .foot a:hover { color:var(--amber2); text-decoration:underline; }
      </style>
      <ha-card>
        <div class="head">
          <div class="badge">${svg('<path d="M12 2a2 2 0 0 1 2 2v.6a7 7 0 0 1 5 6.7c0 4 1 5.3 2.3 6.9.5.6 0 1.6-.8 1.6H3.5c-.8 0-1.3-1-.8-1.6C4 16.9 5 15.6 5 11.6a7 7 0 0 1 5-6.7V4a2 2 0 0 1 2-2z"/><path d="M9.5 20a2.5 2.5 0 0 0 5 0z"/>')}</div>
          <div class="htxt">
            <div class="state">${meta.label}</div>
            <div class="area">${name}</div>
          </div>
          ${showCount ? `<div class="count"><div class="n">${rest}</div><div class="u">Sek.</div></div>` : ""}
        </div>
        <div class="body">
          ${reason && (state === "triggered" || state === "pending") ? `<div class="reason">⚠︎ Ausgelöst durch: ${reason}</div>` : ""}
          <div class="grid">
            ${ARM_BUTTONS.map((b) => `<button class="mode${activeMode === b.mode ? " active" : ""}" data-svc="${b.svc}">${svg(ICONS[b.icon])}<span>${b.label}</span></button>`).join("")}
          </div>
          <button class="disarm" data-svc="alarm_disarm">${svg(ICONS.disarm)}<span>Unscharf schalten</span></button>
          ${needCode ? `<input id="code" class="code" type="${a.code_format === "number" ? "tel" : "text"}" inputmode="${a.code_format === "number" ? "numeric" : "text"}" placeholder="Code / PIN" autocomplete="off"/>` : ""}
          ${(offen.length || umgangen.length) ? `<div class="chips">
              ${offen.length ? `<div><span class="lbl">Offen:</span>${offen.map((s) => `<span class="chip open">${s}</span>`).join("")}</div>` : ""}
              ${umgangen.length ? `<div><span class="lbl">Umgangen:</span>${umgangen.map((s) => `<span class="chip byp">${s}</span>`).join("")}</div>` : ""}
            </div>` : ""}
        </div>
        <div class="foot">
          <span class="wm"><b class="p">Frickel</b><b class="a">alarm</b></span>
          <a href="https://frickelfabrik.de" target="_blank" rel="noopener">powered by Frickelfabrik</a>
        </div>
      </ha-card>
    `;

    this._root.querySelectorAll("button[data-svc]").forEach((btn) => {
      btn.addEventListener("click", () => this._call(btn.dataset.svc));
    });
  }
}

customElements.define("frickelalarm-card", FrickelalarmCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "frickelalarm-card",
  name: "Frickelalarm",
  description: "Bedienfeld für einen Frickelalarm-Bereich im Frickelfabrik-Look",
  preview: true,
});
console.info("%c FRICKELALARM-CARD %c geladen ", "background:#0e3b3a;color:#f0b44c;border-radius:3px 0 0 3px;padding:2px 4px", "background:#f0b44c;color:#0e3b3a;border-radius:0 3px 3px 0;padding:2px 4px");
