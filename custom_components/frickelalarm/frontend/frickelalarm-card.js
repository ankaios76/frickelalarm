/* Frickelalarm – Lovelace-Karte im Frickelfabrik-Look.
   Vanilla Custom Element, keine Build-Kette. Konfig: { type, entity } */

const STATES = {
  disarmed:       { label: "Unscharf",            accent: "#2f7d6b", tri: false },
  arming:         { label: "Wird scharf …",       accent: "#d4870a", tri: false },
  pending:        { label: "Eingang – unscharf schalten", accent: "#d4870a", tri: true },
  armed_home:     { label: "Zuhause scharf",       accent: "#1f3b39", tri: false },
  armed_away:     { label: "Abwesend scharf",      accent: "#1f3b39", tri: false },
  armed_night:    { label: "Nacht scharf",         accent: "#1f3b39", tri: false },
  armed_vacation: { label: "Urlaub scharf",        accent: "#1f3b39", tri: false },
  triggered:      { label: "ALARM!",               accent: "#c0392b", tri: true },
  unavailable:    { label: "Nicht verfügbar",      accent: "#888",    tri: false },
};

const ARM_BUTTONS = [
  { svc: "alarm_arm_home", label: "Zuhause" },
  { svc: "alarm_arm_away", label: "Abwesend" },
  { svc: "alarm_arm_night", label: "Nacht" },
  { svc: "alarm_arm_vacation", label: "Urlaub" },
];

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

  getCardSize() { return 4; }

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
    const name = this._config.name || (a.friendly_name) || "Frickelalarm";
    const rest = a.restzeit_s;
    const reason = a.ausloeser;
    const offen = a.offene_sensoren || [];
    const umgangen = a.umgangene_sensoren || [];
    const needCode = !!a.code_format;

    this._root.innerHTML = `
      <style>
        :host { --petrol:#0e3b3a; --amber:#f0b44c; --amber2:#d4870a; }
        ha-card { overflow:hidden; }
        .head { background:${meta.accent}; color:#fff; padding:18px 20px; display:flex; align-items:center; gap:14px; ${meta.tri ? "animation:pulse 1s infinite;" : ""} }
        @keyframes pulse { 0%,100%{filter:brightness(1)} 50%{filter:brightness(1.25)} }
        .bell { width:40px; height:40px; flex:0 0 auto; }
        .htxt { line-height:1.2; }
        .state { font-size:1.45rem; font-weight:700; }
        .area { font-size:.85rem; opacity:.85; }
        .count { margin-left:auto; font-size:1.8rem; font-weight:700; font-variant-numeric:tabular-nums; }
        .body { padding:16px 20px; }
        .reason { color:var(--amber2); font-weight:600; margin-bottom:10px; }
        .grid { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; }
        button { font:inherit; font-weight:600; cursor:pointer; border:none; border-radius:12px; padding:12px 6px; background:#e7efec; color:var(--petrol); transition:background .15s,transform .05s; }
        button:hover { background:#d6e5e0; }
        button:active { transform:translateY(1px); }
        .disarm { grid-column:1/-1; margin-top:8px; background:var(--amber); color:var(--petrol); }
        .disarm:hover { background:var(--amber2); color:#fff; }
        .code { width:100%; box-sizing:border-box; margin-top:12px; padding:11px 12px; border:1px solid #cfdcd8; border-radius:10px; font:inherit; }
        .info { margin-top:12px; font-size:.85rem; color:#5a6b68; }
        .chip { display:inline-block; background:#f0e2c6; color:#7a5a12; border-radius:8px; padding:2px 8px; margin:2px 4px 0 0; font-size:.78rem; }
        .chip.open { background:#f6d9d4; color:#8c2e22; }
      </style>
      <ha-card>
        <div class="head">
          <svg class="bell" viewBox="0 0 512 512" fill="currentColor"><path d="M256 96c-54 0-78 40-78 94 0 58-18 74-32 92-6 8 0 22 14 22h192c14 0 20-14 14-22-14-18-32-34-32-92 0-54-24-94-78-94z"/><circle cx="256" cy="86" r="20"/><path d="M224 440c0 18 14 32 32 32s32-14 32-32z"/></svg>
          <div class="htxt">
            <div class="state">${meta.label}</div>
            <div class="area">${name}</div>
          </div>
          ${rest != null && (meta.tri || state === "arming") ? `<div class="count">${rest}s</div>` : ""}
        </div>
        <div class="body">
          ${reason && (state === "triggered" || state === "pending") ? `<div class="reason">Ausgelöst durch: ${reason}</div>` : ""}
          <div class="grid">
            ${ARM_BUTTONS.map((b) => `<button data-svc="${b.svc}">${b.label}</button>`).join("")}
            <button class="disarm" data-svc="alarm_disarm">Unscharf schalten</button>
          </div>
          ${needCode ? `<input id="code" class="code" type="${a.code_format === "number" ? "tel" : "text"}" inputmode="${a.code_format === "number" ? "numeric" : "text"}" placeholder="Code/PIN" autocomplete="off"/>` : ""}
          ${offen.length ? `<div class="info">Offen: ${offen.map((s) => `<span class="chip open">${s}</span>`).join("")}</div>` : ""}
          ${umgangen.length ? `<div class="info">Umgangen: ${umgangen.map((s) => `<span class="chip">${s}</span>`).join("")}</div>` : ""}
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
});
console.info("%c FRICKELALARM-CARD %c geladen ", "background:#0e3b3a;color:#f0b44c;border-radius:3px 0 0 3px;padding:2px 4px", "background:#f0b44c;color:#0e3b3a;border-radius:0 3px 3px 0;padding:2px 4px");
