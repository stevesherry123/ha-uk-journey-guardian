/* Beta read-only Lovelace card. No services or network requests. */
export function validTime(value) {
  return typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value));
}

export function formatTime(value, timezone = "Europe/London", locale = "en-GB") {
  if (!validTime(value)) return "Unknown";
  try {
    return new Intl.DateTimeFormat(locale, {
      hour: "2-digit", minute: "2-digit", hour12: false,
      timeZone: timezone, timeZoneName: "short"
    }).format(new Date(value));
  } catch { return "Unknown"; }
}

export function readDashboard(hass, config) {
  const entity = hass?.states?.[config.entity];
  if (!entity || ["unknown", "unavailable"].includes(entity.state)) return null;
  const data = entity.attributes?.dashboard;
  return data?.schema_version === 1 ? data : null;
}

export function chartRows(data) {
  return (Array.isArray(data?.segments) ? data.segments : []).filter(
    row => validTime(row.start) && validTime(row.end) &&
      Date.parse(row.end) > Date.parse(row.start)
  ).slice(0, 4);
}

const BaseElement = typeof HTMLElement === "undefined" ? class {} : HTMLElement;

export class JourneyGuardianCard extends BaseElement {
  setConfig(config) {
    if (!config?.entity?.startsWith("sensor.")) {
      throw new Error("Select the Journey Guardian status sensor.");
    }
    this.config = { ...config };
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.render();
  }

  set hass(value) {
    const previous = this._hass;
    this._hass = value;
    if (previous?.states?.[this.config?.entity] !== value?.states?.[this.config?.entity] ||
        previous?.locale !== value?.locale || previous?.config?.time_zone !== value?.config?.time_zone) this.render();
  }
  getCardSize() { return 12; }
  connectedCallback() {
    if (!this.timer) this.timer = setInterval(() => this.render(), 60000);
  }
  disconnectedCallback() { clearInterval(this.timer); this.timer = null; }

  render() {
    if (!this.config || !this.shadowRoot) return;
    const expanded = this.shadowRoot.querySelector("details")?.open ?? true;
    // Only constant markup enters innerHTML. Calendar/provider values use textContent.
    this.shadowRoot.innerHTML = `<style>
      :host{display:block;color:var(--primary-text-color,#202322);font:14px/1.5 var(--paper-font-body1_-_font-family,system-ui);letter-spacing:0}
      *{box-sizing:border-box}ha-card{display:block;background:var(--ha-card-background,var(--card-background-color,#fff));border:1px solid var(--divider-color,#dadddf);border-radius:8px;padding:22px}
      h1,h2,p{margin:0}h1{font-size:18px;font-weight:600}h2{font-size:14px;font-weight:600;margin:20px 0 10px}.route{font-size:22px;font-weight:600;margin:8px 0;overflow-wrap:anywhere}
      header,.meta,.axis,.row-title{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}.muted,.meta,.axis{color:var(--secondary-text-color,#5d6568)}.meta{font-size:12px}.status{font-weight:500}
      .notice{border-left:3px solid var(--warning-color,#c78512);padding:8px 12px;margin-top:12px;background:var(--secondary-background-color,#f3f5f5)}
      .timeline{margin-top:16px}.track{height:14px;background:var(--secondary-background-color,#eef1f2);position:relative;margin:6px 0 13px;border-radius:2px;overflow:hidden}.bar{height:100%;background:var(--primary-color,#008b9a);border-radius:2px}.rail{background:var(--success-color,#288262)}.now{position:absolute;top:0;bottom:0;width:2px;background:var(--primary-text-color,#202322)}
      .row-title{font-size:13px}.axis{font-size:12px}.rows{list-style:none;margin:0;padding:0}.rows li{display:grid;grid-template-columns:68px minmax(0,1fr);gap:12px;padding:10px 0;border-top:1px solid var(--divider-color,#dadddf)}time{font-variant-numeric:tabular-nums;font-weight:500}.secondary{font-size:12px;color:var(--secondary-text-color,#5d6568);overflow-wrap:anywhere}.routing{display:grid;grid-template-columns:1fr auto;gap:6px 16px}.routing dd,.routing dt{margin:0}.routing dd{text-align:right;font-variant-numeric:tabular-nums}.evidence{margin-top:16px;padding-top:12px;border-top:1px solid var(--divider-color,#dadddf)}summary{font-weight:500;cursor:pointer}details[open] summary{margin-bottom:10px}.empty{padding:24px 0}.bookings{margin-top:12px}.bookings strong{font-weight:500}.badge{color:var(--warning-color,#a46b05)}
      input,button{font:inherit;max-width:100%;padding:8px;margin:6px 8px 6px 0}input{width:100px}button{white-space:normal;cursor:pointer}button:disabled{cursor:default;opacity:.6}label{display:block;overflow-wrap:anywhere}
      @media(max-width:420px){ha-card{padding:16px}.route{font-size:19px}.row-title{display:block}.row-title span{display:block}.routing{grid-template-columns:minmax(0,1fr) auto}.rows li{grid-template-columns:58px minmax(0,1fr);gap:8px}}
    </style><ha-card><header><h1>Journey Guardian</h1><span class="status"></span></header><div class="content"></div></ha-card>`;
    const root = this.shadowRoot.querySelector(".content");
    const add = (tag, text, parent = root, className = "") => {
      const el = document.createElement(tag);
      el.textContent = text ?? "";
      if (className) el.className = className;
      parent.append(el);
      return el;
    };
    const data = readDashboard(this._hass, this.config);
    const status = this.shadowRoot.querySelector(".status");
    if (!data) {
      status.textContent = "Unavailable";
      add("p", "No dashboard data from the selected status sensor.", root, "empty");
      return;
    }
    const timezone = this._hass?.config?.time_zone || Intl.DateTimeFormat().resolvedOptions().timeZone;
    const format = value => formatTime(value, timezone, this._hass?.locale?.language || "en-GB");
    const day = value => validTime(value) ? new Intl.DateTimeFormat(
      this._hass?.locale?.language || "en-GB", { day: "numeric", month: "short", timeZone: timezone }
    ).format(new Date(value)) : "Unknown date";
    status.textContent = data.simulation ? "Simulation" : (data.phase || "Unknown").replaceAll("_", " ");
    if (!data.healthy) add("p", "Journey data needs attention. Times may be retained.", root, "notice");
    for (const warning of (Array.isArray(data.integrity_warnings) ? data.integrity_warnings : []).slice(0, 3)) {
      if (typeof warning.message !== "string") continue;
      const notice = add("p", warning.message, root, "notice");
      notice.setAttribute("role", "status");
      if (validTime(warning.recorded_at)) add("span", ` Last failed check: ${format(warning.recorded_at)}.`, notice, "secondary");
    }
    if (validTime(data.checked_at) && Date.now() - Date.parse(data.checked_at) > 20 * 60000) {
      add("p", "Snapshot is over 20 minutes old.", root, "notice");
    }
    if (data.connection_monitor_enabled && data.connection_monitor_supported === false) add("p", "Connection monitoring requires Railinfo as the selected rail provider.", root, "notice");
    if (data.connection_alert_error) add("p", "Connection alert history could not be saved or loaded. Announcements may be paused.", root, "notice");
    if (data.connection_storage_error) add("p", "Connection settings could not be loaded.", root, "notice");
    if ((data.connections || []).length) {
      add("h2", "Booked connections");
      add("p", data.connection_monitor_enabled ? "Confirmed connections use bounded live checks. Warnings follow your live notification setting." : "Confirm intended changes of train. Live connection monitoring is disabled.", root, "secondary");
      for (const pair of data.connections) {
        const section = add("div", "", root, "evidence");
        add("strong", `Change at ${pair.station}`, section);
        add("p", `Booked arrival ${format(pair.inbound_arrival)} / onward departure ${format(pair.outbound_departure)}`, section, "secondary");
        if (pair.confirmed && pair.assessment) {
          const risk = pair.assessment;
          if (validTime(risk.inbound_event_at) && validTime(risk.outbound_event_at)) add("p", `${risk.inbound_kind === "actual" ? "Recorded" : "Predicted"} arrival ${format(risk.inbound_event_at)} / onward ${format(risk.outbound_event_at)}`, section, "secondary");
          add("p", risk.classification === "unknown" ? `Connection risk unknown / ${risk.reason.replaceAll("_", " ")}` : `${risk.classification === "viable" ? "Transfer allowance met" : "Connection at risk"} / ${risk.minutes_available} minutes available / ${risk.minimum_minutes} required`, section, risk.classification === "at_risk" ? "notice" : "secondary");
        }
        if (pair.confirmed && pair.last_alert && ["risk", "update"].includes(pair.last_alert.kind) && (!pair.assessment || pair.assessment.classification === "unknown")) add("p", "A previous assessment found this connection at risk. Current evidence is unavailable.", section, "notice");
        if (pair.last_alert) {
          const deliveries = {claimed: "delivery unconfirmed", announcement_engine: "sent to travel announcements", persistent_notification: "saved in Home Assistant", suppressed: "not sent", failed: "delivery failed"};
          add("p", `Last connection alert attempt: ${pair.last_alert.kind} / ${format(pair.last_alert.recorded_at)} / ${deliveries[pair.last_alert.delivery] || "unknown result"} / device receipt unconfirmed`, section, "secondary");
        }
        const allowanceLabels = {connection_override: "this connection", station_default: "station default", global_fallback: "global fallback"};
        if (Number.isInteger(pair.allowance_minutes)) add("p", `Required transfer: ${pair.allowance_minutes} minutes / ${allowanceLabels[pair.allowance_source] || "unknown source"}`, section, "secondary");
        add("p", pair.confirmed ? "Connection confirmed" : "Suggested connection — please confirm", section);
        const label = add("label", "Transfer allowance override (minutes, optional) ", section);
        const input = add("input", "", label);
        input.type = "number"; input.min = "0"; input.max = "1440"; input.step = "1";
        input.value = pair.override_minutes ?? "";
        const pairKey = `${pair.inbound_id}:${pair.outbound_id}`;
        const message = add("p", this._connectionMessages?.[pairKey] || "", section, "secondary");
        message.setAttribute("role", "status");
        const buttons = [];
        const submit = async action => {
          if (this._connectionPending) return;
          const payload = {inbound_id: pair.inbound_id, outbound_id: pair.outbound_id};
          if (action === "confirm_connection" && input.value !== "") {
            const minutes = Number(input.value);
            if (!Number.isInteger(minutes) || minutes < 0 || minutes > 1440) {
              message.textContent = "Enter whole minutes from 0 to 1440."; return;
            }
            payload.override_minutes = minutes;
          }
          this._connectionPending = true;
          buttons.forEach(button => button.disabled = true);
          message.textContent = "Saving…";
          try {
            await this._hass.callService("journey_guardian", action, payload);
            message.textContent = "Saved. Connection status will refresh.";
          } catch (_) {
            message.textContent = "Could not save. Refresh the calendar and try again.";
          } finally {
            this._connectionMessages = {...this._connectionMessages, [pairKey]: message.textContent};
            this._connectionPending = false;
            buttons.forEach(button => button.disabled = false);
            this.render();
          }
        };
        const confirm = add("button", pair.confirmed ? "Save allowance" : "Confirm connection", section);
        confirm.disabled = !pair.can_confirm || Boolean(this._connectionPending);
        confirm.addEventListener("click", () => submit("confirm_connection"));
        buttons.push(confirm);
        if (pair.confirmed) {
          const revoke = add("button", "Remove confirmation", section);
          revoke.disabled = Boolean(this._connectionPending) || data.connection_storage_error;
          revoke.addEventListener("click", () => submit("revoke_connection"));
          buttons.push(revoke);
        }
      }
    }
    const journey = data.journey;
    if (!journey) { add("p", "No timed rail journey selected.", root, "empty"); return; }
    add("div", `${journey.origin} to ${journey.destination}`, root, "route");
    const meta = add("div", "", root, "meta");
    add("span", `${day(journey.departure)} / departure ${format(journey.departure)} / booked arrival ${day(journey.booked_arrival)} ${format(journey.booked_arrival)}`, meta);
    add("span", `Updated ${format(data.checked_at)} / ${timezone}`, meta);
    if (journey.cancelled) add("p", "Service cancelled. Planned travel is not a recovery itinerary.", root, "notice");
    const rows = chartRows(data);
    if (rows.length) {
      add("h2", "Travel timeline");
      const timeline = add("div", "", root, "timeline");
      timeline.setAttribute("role", "img");
      timeline.setAttribute("aria-label", "Calculated stages. Arrival is booked, not confirmed. " + rows.map(row =>
        `${row.label}: ${day(row.start)} ${format(row.start)} to ${day(row.end)} ${format(row.end)}`
      ).join(". "));
      const start = Math.min(...rows.map(row => Date.parse(row.start)));
      const end = Math.max(...rows.map(row => Date.parse(row.end)));
      const percent = value => Math.max(0, Math.min(100, (value - start) / (end - start) * 100));
      for (const row of rows) {
        const label = add("div", "", timeline, "row-title");
        add("span", row.label, label);
        add("span", `${format(row.start)} - ${day(row.start) === day(row.end) ? "" : `${day(row.end)} `}${format(row.end)}`, label);
        const track = add("div", "", timeline, "track");
        const bar = add("div", "", track, row.label === "Booked train" ? "bar rail" : "bar");
        bar.style.marginLeft = `${percent(Date.parse(row.start))}%`;
        bar.style.width = `${percent(Date.parse(row.end)) - percent(Date.parse(row.start))}%`;
        if (Date.now() >= start && Date.now() <= end) {
          const marker = add("div", "", track, "now");
          marker.style.left = `${percent(Date.now())}%`;
        }
      }
      const axis = add("div", "", timeline, "axis");
      add("span", format(new Date(start).toISOString()), axis);
      if (Date.now() >= start && Date.now() <= end) {
        add("span", `Now ${format(new Date().toISOString())}`, axis);
      }
      add("span", format(new Date(end).toISOString()), axis);
    } else add("p", "Travel timing is not available.", root, "notice");
    if (data.routing) {
      add("h2", "Station access");
      const routing = add("dl", "", root, "routing");
      const source = { waze_sensor: "Waze", google_routes: "Google", configured_fallback: "Worst-case constant" }[data.routing.source] || "Unknown";
      for (const [key, value] of [["Selected source", source], ["Travel mode", data.routing.mode], ["Provider estimate", data.routing.provider_minutes == null ? "Unavailable" : `${data.routing.provider_minutes} min`], ["Applied allowance", `${data.routing.applied_minutes} min`]]) {
        add("dt", key, routing); add("dd", value, routing);
      }
      if (data.routing.fallback_reason) add("p", data.routing.fallback_reason.replaceAll("_", " ").replaceAll(";", " / "), root, "secondary");
    }
    const details = add("details", ""); details.open = expanded;
    add("summary", "Expected notifications", details);
    add("p", data.planned_delivery === "announcement_engine" ? "Configured announcement engine; phone/watch receipt unconfirmed." : "HA persistent notifications; no phone/watch delivery route confirmed.", details, "secondary");
    const events = add("ul", "", details, "rows");
    for (const event of (data.notifications || []).slice(0, 8)) {
      const item = add("li", "", events);
      const time = add("time", format(event.due_at), item);
      if (validTime(event.due_at)) time.dateTime = event.due_at;
      const content = add("div", "", item);
      add("div", event.label, content);
      add("div", `${event.eligibility}${validTime(event.due_at) && Date.parse(event.due_at) <= Date.now() ? " / time passed; delivery unknown" : ""}`, content, "secondary");
      if (event.eligibility_reason) add("div", event.eligibility_reason, content, "secondary");
      if (event.kind === "wake_alarm") add("div", `Every ${event.repeat_seconds ?? "?"} seconds, up to ${event.maximum_minutes ?? "?"} minutes`, content, "secondary");
      add("div", event.condition, content, "secondary");
      if (event.message) add("p", event.message, content, "secondary");
    }
    const record = data.latest_notification_record;
    add("p", record ? `Latest HA record: ${record.kind.replaceAll("_", " ")} at ${format(record.recorded_at)}. Device receipt unconfirmed.` : "No delivery record available. Device receipt unconfirmed.", root, "evidence secondary");
    const checks = (Array.isArray(data.checks) ? data.checks : []).filter(check => validTime(check.due_at) && Date.parse(check.due_at) > Date.now()).slice(0, 2);
    if (checks.length) {
      add("h2", "Next scheduled checks");
      const list = add("ul", "", root, "rows");
      for (const check of checks) {
        const item = add("li", "", list);
        add("time", format(check.due_at), item);
        const content = add("div", "", item);
        add("div", check.label, content);
        add("div", "Data check, not a promised notification", content, "secondary");
      }
    }
    const bookings = (data.bookings || []).filter(leg => leg.booked_departure !== journey.booked_departure).slice(0, 3);
    if (bookings.length) {
      add("h2", "Other booked legs");
      const list = add("ul", "", root, "rows bookings");
      for (const leg of bookings) {
        const item = add("li", "", list);
        add("time", format(leg.booked_departure), item);
        const content = add("div", "", item);
        add("strong", `${leg.origin} to ${leg.destination}`, content);
        add("div", `${day(leg.booked_departure)} / booked arrival ${day(leg.booked_arrival)} ${format(leg.booked_arrival)} / ${data.bookings_source === "retained_calendar" ? "retained calendar" : "calendar only"}`, content, "secondary");
      }
    }
    if (data.bookings_truncated) add("p", "Additional bookings omitted.", root, "secondary");
  }
}

if (typeof customElements !== "undefined" && !customElements.get("journey-guardian-card")) {
  customElements.define("journey-guardian-card", JourneyGuardianCard);
}
