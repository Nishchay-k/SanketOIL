// @ts-nocheck
import { api } from "../lib/api";

const state = {
  route: window.location.hash.replace("#", "") || "dashboard",
  wells: [],
  formations: [],
  activeWellCode: "A-101",
  activeWell: null,
  radius: 10,
  mapView: "surface",
  mapZoom: 1,
  trajectoryWells: [],
  trajectoryLoading: false,
  depth: 2840,
  formation: "F3",
  nearby: [],
  events: [],
  telemetry: null,
  risk: null,
  alerts: [],
  correlation: null,
  selectedOffset: null,
  loading: true,
  contextLoading: false,
  error: null,
  eventFilters: { q: "", event_type: "", severity: "", formation: "", depth_min: "", depth_max: "" },
  globalQuery: "",
  globalResults: [],
  globalSearchOpen: false,
  globalSearchBusy: false,
  documents: [],
  documentsLoaded: false,
  documentsLoading: false,
  documentsError: "",
  documentFormats: [],
  documentCapabilities: {},
  wellSearch: "",
  simulatorStep: 0
};

const appRoot = document.getElementById("app");
const dialogRoot = document.getElementById("dialog-root");
let refreshTimer = null;
let telemetryStream = null;
let globalSearchTimer = null;
let greetingTimer = null;
let globalSearchRequestId = 0;
const DEMO_CREDENTIALS = { id: "engineer@oilindia.demo", password: "NWIS-demo-26121" };

function esc(value) {
  return String(value === null || value === undefined ? "" : value).replace(/[&<>"']/g, function (char) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
  });
}

function number(value, digits) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString("en-US", { minimumFractionDigits: digits || 0, maximumFractionDigits: digits || 0 }) : "—";
}

function eventLabel(type) {
  const labels = {
    MUD_LOSS: "Mud loss",
    STUCK_PIPE: "Stuck pipe",
    KICK_PRESSURE: "Kick / pressure",
    OVERPRESSURE: "Formation pressure",
    TORQUE_DRAG: "Torque & drag",
    CEMENTING: "Cementing",
    FISHING: "Fishing",
    NPT: "NPT / non-productive time"
  };
  return labels[type] || String(type || "Unknown").replaceAll("_", " ").toLowerCase();
}

function severityClass(value) {
  return String(value || "unknown").toLowerCase();
}

function formatTime(value) {
  if (!value) return "No reading";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" }).format(date) + " IST";
}

function liveGreeting(date) {
  const hour = (date || new Date()).getHours();
  if (hour >= 5 && hour < 12) return "Good morning";
  if (hour >= 12 && hour < 17) return "Good afternoon";
  if (hour >= 17 && hour < 21) return "Good evening";
  return "Good night";
}

function scheduleGreetingUpdate() {
  window.clearTimeout(greetingTimer);
  greetingTimer = null;
  if (state.route !== "dashboard" || state.loading) return;
  const now = new Date();
  const candidates = [5, 12, 17, 21].map(function (hour) {
    const boundary = new Date(now);
    boundary.setHours(hour, 0, 0, 50);
    return boundary;
  }).filter(function (boundary) { return boundary > now; });
  let nextBoundary = candidates.sort(function (a, b) { return a - b; })[0];
  if (!nextBoundary) {
    nextBoundary = new Date(now);
    nextBoundary.setDate(nextBoundary.getDate() + 1);
    nextBoundary.setHours(5, 0, 0, 50);
  }
  greetingTimer = window.setTimeout(function () {
    const greeting = document.querySelector("[data-live-greeting]");
    if (greeting) greeting.textContent = liveGreeting() + ", engineer.";
    scheduleGreetingUpdate();
  }, Math.max(1000, nextBoundary.getTime() - now.getTime()));
}

function activeWell() {
  return state.activeWell || state.wells.find(function (well) { return well.well_code === state.activeWellCode; }) || null;
}

function nearbyCount() {
  return state.nearby.length;
}

function evidenceEvents() {
  return state.risk && state.risk.evidence ? state.risk.evidence : [];
}

function icon(name) {
  const paths = {
    overview: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5.5 9.5V21h13V9.5M9 21v-7h6v7"/>',
    wells: '<circle cx="10" cy="10" r="6.5"/><path d="m15 15 6 6M10 6v8M7 10h6"/>',
    events: '<path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5"/>',
    risk: '<path d="M12 3 2.8 20h18.4L12 3Z"/><path d="M12 9v4M12 16.4v.1"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="m19.4 15 .1.1 1.2 2.1-2.3 2.3-2.1-1.2-.2.1-.6 2.5h-3.2l-.6-2.5-.2-.1-2.1 1.2-2.3-2.3 1.2-2.1-.1-.2-2.5-.6v-3.2l2.5-.6.1-.2-1.2-2.1 2.3-2.3 2.1 1.2.2-.1.6-2.5h3.2l.6 2.5.2.1 2.1-1.2 2.3 2.3-1.2 2.1.1.2 2.5.6v3.2l-2.5.6-.1.2Z"/>',
    arrow: '<path d="M4 12h15M13 5l7 7-7 7"/>',
    chevron: '<path d="m8 10 4 4 4-4"/>',
    pin: '<path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',
    layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    search: '<circle cx="10.8" cy="10.8" r="6.7"/><path d="m16 16 4.5 4.5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    document: '<path d="M6 3h8l4 4v14H6zM14 3v5h5M9 13h6M9 17h6"/>',
    logout: '<path d="M10 17l5-5-5-5M15 12H3M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6"/>',
    zoomIn: '<circle cx="10.8" cy="10.8" r="6.7"/><path d="m16 16 4.5 4.5M10.8 7.8v6M7.8 10.8h6"/>',
    zoomOut: '<circle cx="10.8" cy="10.8" r="6.7"/><path d="m16 16 4.5 4.5M7.8 10.8h6"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    check: '<path d="m5 12 4 4L19 6"/>'
  };
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (paths[name] || paths.overview) + "</svg>";
}

function routeTitle() {
  const titles = { dashboard: "Operations overview", wells: "Well directory", events: "Evidence", risk: "Risk review" };
  return titles[state.route] || titles.dashboard;
}

function setLoading() {
  state.loading = true;
  appRoot.innerHTML = '<div class="boot-screen"><img class="brand-emblem boot-emblem" src="/branding/sanket-mark.png" alt="SANKET mark"><strong>SANKET</strong><span>Nearby Wells Intelligence System</span></div>';
}

function renderLogin() {
  if (telemetryStream) { telemetryStream.close(); telemetryStream = null; }
  const demoMode = api.authMode !== "supabase";
  appRoot.innerHTML = `<main class="login-screen"><div class="login-scene" role="presentation">
    <svg class="login-landscape" viewBox="0 0 960 760" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs><linearGradient id="login-sky" x2="0" y2="1"><stop stop-color="#132b38"/><stop offset=".54" stop-color="#466475"/><stop offset="1" stop-color="#dc9d72"/></linearGradient><linearGradient id="login-ground" x2="0" y2="1"><stop stop-color="#866a4d"/><stop offset="1" stop-color="#252f2d"/></linearGradient><radialGradient id="login-sun"><stop stop-color="#ffe3a9" stop-opacity=".8"/><stop offset="1" stop-color="#e8a273" stop-opacity="0"/></radialGradient></defs>
      <rect width="960" height="760" fill="url(#login-sky)"/><circle cx="716" cy="218" r="180" fill="url(#login-sun)"/><circle cx="716" cy="218" r="42" fill="#f0bc83" opacity=".9"/>
      <path d="M0 438Q150 365 320 430t335-11 305 19v322H0Z" fill="#30443c"/><path d="M0 509q210-97 421 0t539-16v267H0Z" fill="url(#login-ground)"/><path d="M0 590q205-64 408 13t552-33v190H0Z" fill="#252c2a"/>
      <g class="scene-clouds" fill="#d2d1c4" opacity=".22"><path d="M70 198q4-24 31-24 9-33 44-30 18-35 52-15 32 3 34 34 31 1 30 35H70Z"/><path d="M326 120q4-19 25-19 7-26 34-24 14-29 41-13 25 2 27 27 24 0 23 29H326Z"/></g>
      <g class="scene-rig"><path d="m474 520 68-309 70 309M495 425h93m-81-57h67m-55-58h43m-31-57h20M485 472h84m-77-29 91 29m-83-73 75 25m-66-71 62 20m-53-64 48 19m-39-61 39 16" fill="none" stroke="#e0c9a3" stroke-width="7" stroke-linecap="round"/><path d="M531 212h23m-14-48v48" stroke="#f1c98e" stroke-width="5"/><path d="M536 157h15l-7-25Z" fill="#f5cf8b"/><path d="M544 520v96" stroke="#c7a77a" stroke-width="3"/><path d="M440 523h138v12H440z" fill="#d3b389"/><rect x="505" y="488" width="77" height="31" rx="3" fill="#1e3032"/><rect x="514" y="493" width="18" height="12" fill="#e6a068" opacity=".8"/><circle cx="522" cy="520" r="7" fill="#1b2526"/><circle cx="566" cy="520" r="7" fill="#1b2526"/></g>
      <g class="scene-pump"><path d="M171 559h126m-90 0 21-69 24 69m-16-54 79-20m-79 20-41-22" fill="none" stroke="#c69a6b" stroke-width="7" stroke-linecap="round"/><path d="M269 485q36-7 51 7-17 10-38 8" fill="#d4ad7b"/><path d="M303 499v57" stroke="#d3b58a" stroke-width="3"/><circle cx="209" cy="548" r="13" fill="#242c29" stroke="#bd9768" stroke-width="4"/></g>
      <path d="M0 644q188-20 358 21t309-7 293 2v100H0Z" fill="#1b2625"/><g fill="#dec59d" opacity=".5"><circle cx="95" cy="581" r="2"/><circle cx="348" cy="616" r="2"/><circle cx="789" cy="589" r="2"/><circle cx="868" cy="640" r="2"/></g>
    </svg></div><section class="login-intro" aria-label="About SANKET"><span class="login-intro-label">NEARBY WELLS INTELLIGENCE</span><h1>Know what nearby wells encountered.</h1><p>Review offset-well history, drilling events, and source documents alongside the active well.</p><ul><li>Compare wells by depth and formation</li><li>Find events and reported mitigations</li><li>Review evidence before making a decision</li></ul></section><section class="login-card" aria-label="SANKET sign in"><div class="login-brand"><img class="brand-emblem login-emblem" src="/branding/sanket-mark.png" alt=""><span class="brand-name">SANKET<small>NEARBY WELLS INTELLIGENCE SYSTEM</small></span></div><div class="login-form-wrap"><div class="eyebrow">ENGINEER ACCESS</div><h2>Welcome back.</h2><p>Read the signals. Understand the well.</p><form id="login-form"><label class="form-label" for="login-id">Engineer ID</label><input id="login-id" name="login-id" autocomplete="username" value="${demoMode ? DEMO_CREDENTIALS.id : ""}" required><label class="form-label" for="login-password">Password</label><input id="login-password" name="login-password" type="password" autocomplete="current-password" value="${demoMode ? DEMO_CREDENTIALS.password : ""}" required><div class="login-hint">${demoMode ? "Demo credentials are prefilled for this prototype." : "Sign in with your SANKET account."}</div><div id="login-error" class="form-feedback" role="alert"></div><button class="login-submit" type="submit">Enter operations workspace ${icon("arrow")}</button></form><div class="login-footer"><span><i></i>${demoMode ? "Local demo environment" : "Secure account sign-in"}</span><span>${demoMode ? "Access is not an OIL account" : "SANKET access"}</span></div></div></section></main>`;
  document.getElementById("login-form").addEventListener("submit", async function (event) {
    event.preventDefault();
    const id = document.getElementById("login-id").value.trim();
    const password = document.getElementById("login-password").value;
    const submit = document.querySelector(".login-submit");
    const feedback = document.getElementById("login-error");
    feedback.textContent = "";
    submit.disabled = true;
    submit.textContent = "Opening workspace…";
    try {
      if (demoMode) {
        if (id !== DEMO_CREDENTIALS.id || password !== DEMO_CREDENTIALS.password) throw new Error("That ID or password does not match the demo credentials.");
        sessionStorage.setItem("nwis.demo-auth", "1");
      } else {
        await api.signIn(id, password);
      }
      loadData();
    } catch (error) {
      feedback.textContent = error.message || "Sign-in could not be completed.";
      submit.disabled = false;
      submit.innerHTML = "Enter operations workspace " + icon("arrow");
    }
  });
}

function globalSearchMarkup() {
  if (state.globalSearchError) return '<div class="search-state is-error">' + esc(state.globalSearchError) + '</div>';
  if (state.globalSearchBusy) return '<div class="search-state">Searching local well and evidence records…</div>';
  if (!state.globalResults.length) return '<div class="search-state">' + (state.globalQuery.length < 2 ? "Search wells, events, formations, symptoms, or uploaded document text." : "No local matches yet. Try a well code, depth, formation, or drilling symptom.") + '</div>';
  return '<div class="search-result-note">Ranked by well, depth, formation, event, and text match · source references stay attached</div>' + state.globalResults.map(function (item, index) {
    const citation = item.source_document ? '<small class="search-citation">Source: ' + esc(item.source_document) + (item.source_page ? ' · p. ' + number(item.source_page, 0) : "") + '</small>' : "";
    return '<button class="global-search-result" data-search-index="' + index + '"><span class="search-kind ' + esc(item.kind) + '">' + icon(item.kind === "document" ? "document" : item.kind === "event" ? "events" : "wells") + '</span><span class="search-result-copy"><strong>' + esc(item.title) + '</strong><small>' + esc(item.subtitle) + '</small><span>' + esc(item.snippet) + '</span>' + citation + '</span><span class="search-score">' + Math.round((item.score || 0) * 100) + '%</span></button>';
  }).join("");
}

function updateGlobalSearchResults() {
  const panel = document.getElementById("global-search-results");
  if (!panel) return;
  panel.hidden = !state.globalSearchOpen;
  panel.innerHTML = state.globalSearchOpen ? globalSearchMarkup() : "";
  panel.querySelectorAll("[data-search-index]").forEach(function (button) {
    button.addEventListener("click", function () {
      const item = state.globalResults[Number(button.dataset.searchIndex)];
      state.globalSearchOpen = false;
      updateGlobalSearchResults();
      if (item) openSearchResult(item);
    });
  });
}

function bindGlobalSearch() {
  const input = document.getElementById("global-search-input");
  if (!input) return;
  input.addEventListener("focus", function () {
    state.globalSearchOpen = true;
    updateGlobalSearchResults();
  });
  input.addEventListener("input", function () {
    const requestId = ++globalSearchRequestId;
    state.globalQuery = this.value;
    state.globalSearchOpen = true;
    state.globalResults = [];
    state.globalSearchError = "";
    state.globalSearchBusy = state.globalQuery.trim().length >= 2;
    updateGlobalSearchResults();
    window.clearTimeout(globalSearchTimer);
    const query = state.globalQuery.trim();
    if (query.length < 2) { state.globalSearchBusy = false; updateGlobalSearchResults(); return; }
    globalSearchTimer = window.setTimeout(function () {
      api.search(query, 12).then(function (result) {
        if (requestId !== globalSearchRequestId) return;
        state.globalResults = result.results || [];
        state.globalSearchBusy = false;
        updateGlobalSearchResults();
      }).catch(function (error) {
        if (requestId !== globalSearchRequestId) return;
        state.globalResults = [];
        state.globalSearchBusy = false;
        state.globalSearchError = error.message;
        updateGlobalSearchResults();
      });
    }, 220);
  });
  input.addEventListener("keydown", function (event) {
    if (event.key === "Escape") { state.globalSearchOpen = false; updateGlobalSearchResults(); input.blur(); }
    if (event.key === "Enter" && state.globalResults[0]) {
      const first = state.globalResults[0];
      state.globalSearchOpen = false;
      updateGlobalSearchResults();
      openSearchResult(first);
    }
  });
  updateGlobalSearchResults();
}

function openSearchResult(item) {
  if (item.kind === "well") showWellDialog(item.well_code || item.id);
  else if (item.kind === "event" && item.extracted) showDocumentDialog(item.document_id);
  else if (item.kind === "event") showEventDialog(item.id);
  else if (item.kind === "document") showDocumentDialog(item.id);
}

function logout() {
  sessionStorage.removeItem("nwis.demo-auth");
  state.wells = [];
  state.activeWell = null;
  state.risk = null;
  state.telemetry = null;
  state.nearby = [];
  state.events = [];
  state.alerts = [];
  state.correlation = null;
  api.signOut().catch(function (error) { console.error("Could not close the sign-in session", error); }).finally(renderLogin);
}

async function loadData() {
  state.error = null;
  try {
    const bootstrap = await api.bootstrap();
    state.wells = bootstrap.wells || [];
    state.formations = bootstrap.formations || [];
    state.health = bootstrap.health || null;
    state.activeWell = state.wells.find(function (well) { return well.well_code === state.activeWellCode; }) || state.wells[0] || null;
    if (!state.activeWell) throw new Error("No wells are available in the development dataset.");
    state.activeWellCode = state.activeWell.well_code;
    if (!state.depth || state.depth === 2840 && state.activeWell.well_code !== "A-101") state.depth = state.activeWell.current_depth || state.activeWell.total_depth;
    state.formation = state.activeWell.formation || "F3";
    state.loading = false;
    state.contextLoading = true;
    render();
    connectTelemetry(state.activeWellCode);
    loadContext().then(async function () {
      state.contextLoading = false;
      if (state.mapView === "profile") await loadTrajectories();
      render();
    }).catch(function (error) {
      state.contextLoading = false;
      state.error = error.message;
      render();
    });
  } catch (error) {
    state.error = error.message;
    state.loading = false;
    render();
  }
}

async function loadContext() {
  const well = activeWell();
  if (!well) return;
  const [nearby, events, telemetry, risk, correlationResult] = await Promise.all([
    api.nearby(state.activeWellCode, state.radius, state.depth, state.formation),
    api.events({}),
    api.telemetry(state.activeWellCode),
    api.predictRisk({
      well_id: state.activeWellCode,
      depth: Number(state.depth),
      formation: state.formation,
      radius_km: state.radius
    }),
    api.correlation(state.activeWellCode, state.radius, Number(state.depth), state.formation)
  ]);
  state.nearby = nearby.wells || [];
  state.events = events.events || [];
  state.telemetry = telemetry.readings && telemetry.readings[0] ? telemetry.readings[0] : null;
  state.risk = risk.prediction || null;
  state.correlation = correlationResult.correlation || null;
  const alertResult = await api.alerts(state.activeWellCode);
  state.alerts = alertResult.alerts || [];
  if (!state.selectedOffset || !state.nearby.some(function (item) { return item.well_code === state.selectedOffset; })) {
    state.selectedOffset = (evidenceEvents()[0] && evidenceEvents()[0].well_code) || (state.nearby[0] && state.nearby[0].well_code) || null;
  }
}

function refreshContext() {
  window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(async function () {
    try {
      await loadContext();
      render();
    } catch (error) {
      state.error = error.message;
      render();
    }
  }, 160);
}

function renderShell(content) {
  const current = activeWell();
  const navItems = [
    ["dashboard", "Operations", "overview"],
    ["risk", "Risk", "risk"],
    ["wells", "Wells", "wells"],
    ["events", "Evidence", "events"]
  ];
  const nav = navItems.map(function (item) {
    const selected = state.route === item[0];
    return '<a class="nav-link ' + (selected ? "active" : "") + '" href="#' + item[0] + '" ' + (selected ? 'aria-current="page"' : "") + ">" +
      '<span class="nav-icon">' + icon(item[2]) + "</span><span>" + item[1] + "</span>" +
      (item[0] === "risk" && state.alerts.some(function (alert) { return alert.status === "NEW"; }) ? '<span class="nav-alert-dot" aria-label="New review alert"></span>' : "") + "</a>";
  }).join("");
  const options = state.wells.map(function (well) {
    return '<option value="' + esc(well.well_code) + '" ' + (well.well_code === state.activeWellCode ? "selected" : "") + ">" + esc(well.well_code) + " · " + esc(well.field) + "</option>";
  }).join("");
  const errorNotice = state.error
    ? '<div class="global-error" role="alert"><span>' + esc(state.error) + '</span><button class="text-button" data-action="retry">Try again</button></div>'
    : "";
  appRoot.innerHTML =
    '<div class="app-frame' + (state.route === "risk" ? " app-frame-risk" : "") + '">' +
      '<aside class="sidebar">' +
        '<a class="brand-lockup" href="#dashboard" aria-label="SANKET operations overview">' +
          '<img class="brand-emblem" src="/branding/sanket-mark.png" alt="">' +
          '<span class="brand-name">SANKET<small>NEARBY WELLS INTELLIGENCE SYSTEM</small></span>' +
        "</a>" +
        '<div class="sidebar-label">WORKSPACE</div><nav class="primary-nav" aria-label="Main navigation">' + nav + "</nav>" +
        '<div class="sidebar-bottom">' +
          '<div class="connection-card"><span class="connection-light"></span><span>Local system</span><span class="connection-state">Ready</span></div>' +
          '<div class="active-well-mini"><div class="mini-label">ACTIVE WELL</div><div class="mini-code">' + esc(current ? current.well_code : "—") + '<span class="status-pip"></span></div><div class="mini-meta">' + esc(current ? current.field : "") + " · " + esc(state.formation) + "</div></div>" +
          '<div class="profile-line"><div class="profile-avatar">DE</div><div><strong>Drilling engineer</strong><small>Operations workspace</small></div></div>' +
        "</div>" +
      "</aside>" +
      '<main class="main-shell">' +
        '<header class="topbar"><div class="breadcrumbs"><span>SANKET</span><span class="crumb-slash">/</span><strong>' + esc(routeTitle()) + "</strong></div>" +
          '<div class="global-search-wrap"><label class="global-search-box"><span>' + icon("search") + '</span><input id="global-search-input" autocomplete="off" value="' + esc(state.globalQuery) + '" placeholder="Search wells, events, evidence…" aria-label="Search wells, events, and evidence"><kbd>⌘ K</kbd></label><div id="global-search-results" class="global-search-results" hidden></div></div>' +
          '<div class="topbar-right"><span class="system-status"><span class="connection-light"></span>System ready</span><span class="topbar-divider"></span><span class="dataset-pill" title="All included records are synthetic development data"><span class="dataset-spark"></span>Development dataset</span><button class="logout-button" data-action="logout" title="Leave the demo workspace" aria-label="Log out">' + icon("logout") + '</button></div>' +
        "</header>" +
        '<section class="workspace workspace-' + esc(state.route) + '">' + errorNotice + content + "</section>" +
      "</main>" +
    "</div>";
  bindShell();
}

function bindShell() {
  bindGlobalSearch();
  const logoutButton = document.querySelector('[data-action="logout"]');
  if (logoutButton) logoutButton.addEventListener("click", logout);
  const wellSelect = document.getElementById("active-well-select");
  if (wellSelect) wellSelect.addEventListener("change", function () { selectWell(this.value); });
  const depthInput = document.getElementById("depth-input");
  if (depthInput) depthInput.addEventListener("change", function () {
    const value = Number(this.value);
    if (Number.isFinite(value) && value >= 0 && value <= 8000) {
      state.depth = value;
      refreshContext();
    } else {
      this.value = state.depth;
    }
  });
  const radiusSelect = document.getElementById("radius-select");
  if (radiusSelect) radiusSelect.addEventListener("change", function () {
    state.radius = Number(this.value);
    refreshContext();
  });
  const formationSelect = document.getElementById("formation-select");
  if (formationSelect) formationSelect.addEventListener("change", function () {
    state.formation = this.value;
    refreshContext();
  });
  const retry = document.querySelector('[data-action="retry"]');
  if (retry) retry.addEventListener("click", loadData);
}

async function selectWell(wellCode) {
  const well = state.wells.find(function (item) { return item.well_code === wellCode; });
  if (!well) return;
  state.activeWellCode = wellCode;
  state.activeWell = well;
  state.formation = well.formation;
  state.depth = well.current_depth || well.total_depth;
  state.selectedOffset = null;
  state.trajectoryKey = null;
  state.trajectoryWells = [];
  state.nearby = [];
  state.events = [];
  state.risk = null;
  state.telemetry = null;
  state.contextLoading = true;
  connectTelemetry(wellCode);
  render();
  try {
    await loadContext();
    state.contextLoading = false;
    if (state.mapView === "profile") await loadTrajectories();
    else render();
  } catch (error) {
    state.contextLoading = false;
    state.error = error.message;
    render();
  }
}

function connectTelemetry(wellCode) {
  if (telemetryStream) {
    telemetryStream.close();
    telemetryStream = null;
  }
  telemetryStream = api.streamTelemetry(wellCode, function (packet) {
    const reading = packet.reading;
    if (!reading || packet.well_code !== state.activeWellCode) return;
    if (state.telemetry && state.telemetry.timestamp === reading.timestamp) return;
    state.telemetry = reading;
    state.depth = reading.depth;
    state.formation = reading.formation || state.formation;
    state.activeWell = Object.assign({}, activeWell(), {
      current_depth: reading.depth,
      formation: state.formation
    });
    refreshContext();
  }, function (update) {
    if (!update || update.well_code !== state.activeWellCode) return;
    state.alerts = [update].concat(state.alerts.filter(function (item) { return item.id !== update.id; }));
    render();
  });
}

function contextControls() {
  const options = state.wells.map(function (well) {
    return '<option value="' + esc(well.well_code) + '" ' + (well.well_code === state.activeWellCode ? "selected" : "") + ">" + esc(well.well_code) + " · " + esc(well.field) + "</option>";
  }).join("");
  const formationOptions = state.formations.map(function (formation) {
    return '<option value="' + esc(formation.name) + '" ' + (formation.name === state.formation ? "selected" : "") + ">" + esc(formation.name) + " · " + number(formation.top_depth, 0) + "–" + number(formation.bottom_depth, 0) + " m</option>";
  }).join("");
  return '<div class="context-controls"><label class="context-field well-context"><span>ACTIVE WELL</span><select id="active-well-select" aria-label="Select active well">' + options + "</select>" + icon("chevron") + "</label>" +
    '<label class="context-field depth-context"><span>CURRENT DEPTH</span><span class="input-with-unit"><input id="depth-input" aria-label="Current measured depth in metres" type="number" min="0" max="8000" step="10" value="' + esc(state.depth) + '"><b>m</b></span></label>' +
    '<label class="context-field formation-context"><span>FORMATION</span><select id="formation-select" aria-label="Formation">' + formationOptions + "</select>" + icon("chevron") + "</label></div>";
}

function pageHeading(eyebrow, title, subtitle, showControls) {
  return '<div class="page-heading"><div><div class="eyebrow">' + esc(eyebrow) + '</div><h1>' + title + '</h1><p>' + subtitle + "</p></div>" + (showControls ? contextControls() : "") + "</div>";
}

function metricCard(label, value, detail, iconName, accent) {
  return '<article class="metric-card"><div class="metric-top"><span>' + esc(label) + '</span><span class="metric-icon ' + accent + '">' + icon(iconName) + '</span></div><div class="metric-value">' + value + '</div><div class="metric-detail">' + detail + "</div></article>";
}

function riskBadge(severity, text) {
  return '<span class="risk-badge ' + severityClass(severity) + '"><i></i>' + esc(text || severity || "UNKNOWN") + "</span>";
}

function mapSvg() {
  const well = activeWell();
  if (!well) return '<div class="empty-inline">Select a well to view nearby offsets.</div>';
  return state.mapView === "profile" ? mapProfileSvg(well) : mapSurfaceSvg(well);
}

function mapTooltipMarkup(x, y, wellCode, distanceText, relevance) {
  const left = Number(x) > 432 ? Number(x) - 158 : Number(x) + 10;
  const top = Number(y) < 62 ? Number(y) + 12 : Number(y) - 52;
  return '<g class="map-tooltip" transform="translate(' + left + ' ' + top + ')"><rect width="148" height="43" rx="5"/><text class="map-tooltip-heading" x="8" y="14">' + esc(wellCode) + ' · ' + esc(distanceText) + '</text><text class="map-tooltip-label" x="8" y="33">RELEVANCE</text><text class="map-tooltip-percent" x="140" y="34" text-anchor="end">' + number(relevance, 0) + '%</text></g>';
}

function mapSurfaceSvg(well) {
  const centerX = 300;
  const centerY = 174;
  const pixelsPerKm = Math.min(12.4, 150 / Number(state.radius)) * state.mapZoom;
  const ringRadius = Number(state.radius) * pixelsPerKm;
  const eventWellCodes = new Set(evidenceEvents().map(function (event) { return event.well_code; }));
  const points = state.nearby.map(function (offset) {
    const x = centerX + (offset.longitude - well.longitude) * 111.32 * Math.cos(well.latitude * Math.PI / 180) * pixelsPerKm;
    const y = centerY - (offset.latitude - well.latitude) * 111.32 * pixelsPerKm;
    const selected = state.selectedOffset === offset.well_code;
    const hasEvidence = eventWellCodes.has(offset.well_code);
    const relevance = Math.round(offset.similarity * 100);
    return '<g class="map-well ' + (selected ? "selected " : "") + (hasEvidence ? "has-evidence" : "") + '" data-well="' + esc(offset.well_code) + '" data-distance="' + number(offset.distance_km, 1) + ' km" data-relevance="' + relevance + '" role="button" tabindex="0" aria-label="' + esc(offset.well_code) + ", " + number(offset.distance_km, 1) + ' kilometres away, relevance ' + relevance + ' percent">' +
      (hasEvidence ? '<circle class="map-pulse" cx="' + x + '" cy="' + y + '" r="11"/>' : "") +
      '<circle class="map-dot" cx="' + x + '" cy="' + y + '" r="' + (selected ? 7 : 5) + '"/><text x="' + (x + 9) + '" y="' + (y - 8) + '">' + esc(offset.well_code) + '</text></g>';
  }).join("");
  return '<svg class="well-map satellite-map" viewBox="0 0 600 340" role="img" aria-label="Satellite-style local map centered on ' + esc(well.well_code) + '">' +
    '<defs><linearGradient id="terrain-base" x2=".2" y2="1"><stop stop-color="#657b63"/><stop offset=".48" stop-color="#758166"/><stop offset="1" stop-color="#596c58"/></linearGradient><pattern id="field-lines" width="112" height="82" patternUnits="userSpaceOnUse" patternTransform="rotate(-17)"><path d="M0 12h112M0 24h112M0 36h112M0 48h112M0 60h112M0 72h112" stroke="#dfd2a4" stroke-opacity=".11" stroke-width="1"/><path d="M0 2h112M0 42h112" stroke="#253e36" stroke-opacity=".16" stroke-width="3"/></pattern><linearGradient id="river" x2="0" y2="1"><stop stop-color="#748c87"/><stop offset="1" stop-color="#4c6c70"/></linearGradient></defs>' +
    '<rect width="600" height="340" fill="url(#terrain-base)"/><path d="M-30 90Q96 25 193 89t183-9 232-12v56q-144 43-246 8T166 158-20 146Z" fill="#9a966c" opacity=".42"/><path d="M-24 270q110-58 223-18t194-7 250 22v93H-24Z" fill="#3c5747" opacity=".61"/><path d="M390-20q-41 84 12 135t-9 97 36 147h84q-40-91 2-151t-21-105 31-123Z" fill="url(#river)" opacity=".64"/><rect width="600" height="340" fill="url(#field-lines)"/>' +
    '<g class="terrain-texture"><path d="M20 36q88 53 158 8t138 13 153-8 140 17M-8 204q89-46 176-13t159-4 130 23 158-9M31 313q83-39 146-16t117 7 164-11 153 20"/><path d="M88 0q-35 58 5 100t-1 102 42 138M282-10q-40 77 0 127t-9 96 17 137M501-5q-43 79-8 130t-13 101 26 118"/></g>' +
    '<g class="map-roads"><path d="M-10 186Q126 175 239 202t188-8 185 2M242-10q-5 76 24 135t-14 111 19 118M-10 72q141 28 267 4t169 16 187-4"/></g>' +
    '<g class="map-site-labels"><text x="33" y="53">OIL FIELD · LOCAL BASEMAP</text></g>' +
    '<circle class="map-radius" cx="' + centerX + '" cy="' + centerY + '" r="' + ringRadius + '"/><text class="map-radius-label" x="' + (centerX + Math.min(ringRadius, 227) + 5) + '" y="' + (centerY - 7) + '">' + number(state.radius, 0) + ' km radius</text>' + points +
    '<g class="map-active" data-well="' + esc(well.well_code) + '" data-distance="Active well" data-relevance="100" role="button" tabindex="0" aria-label="Active well ' + esc(well.well_code) + ', relevance 100 percent"><circle cx="' + centerX + '" cy="' + centerY + '" r="14"/><circle cx="' + centerX + '" cy="' + centerY + '" r="5.5"/><text x="' + (centerX + 13) + '" y="' + (centerY - 13) + '">' + esc(well.well_code) + '</text></g>' +
    '<g class="map-compass"><path d="m559 25 5 14-5-3-5 3 5-14Z"/><text x="555" y="51">N</text></g></svg>';
}

function trajectoryPoints(surveys, baseX, top, plotHeight, maxTvd) {
  let x = baseX;
  let previous = null;
  return (surveys || []).map(function (point) {
    const md = Number(point.measured_depth || 0);
    const tvd = Number(point.tvd || md);
    if (previous) {
      const dmd = Math.max(0, md - previous.md);
      const inclination = (Number(point.inclination || 0) + Number(previous.inclination || 0)) / 2 * Math.PI / 180;
      const azimuth = (Number(point.azimuth || 0) + Number(previous.azimuth || 0)) / 2 * Math.PI / 180;
      x += dmd * Math.sin(inclination) * Math.sin(azimuth) / 1000 * 18;
    }
    previous = { md: md, inclination: Number(point.inclination || 0), azimuth: Number(point.azimuth || 0) };
    return { md: md, tvd: tvd, x: x, y: top + Math.max(0, tvd) / maxTvd * plotHeight };
  });
}

function interpolateTrajectory(points, depth, axis) {
  if (!points.length) return axis === "y" ? depth : 300;
  if (depth <= points[0].md) return points[0][axis];
  for (let index = 1; index < points.length; index += 1) {
    if (depth <= points[index].md) {
      const before = points[index - 1];
      const after = points[index];
      const portion = (depth - before.md) / Math.max(1, after.md - before.md);
      return before[axis] + (after[axis] - before[axis]) * portion;
    }
  }
  return points[points.length - 1][axis];
}

function mapProfileSvg(well) {
  if (state.trajectoryLoading) return '<div class="profile-loading"><span class="loader-dots"></span><strong>Loading nearby survey stations…</strong><small>Drawing each well path and placing recorded events by true vertical depth.</small></div>';
  if (!state.trajectoryWells.length) return '<div class="profile-loading"><strong>Build the depth comparison</strong><small>Load local survey trajectories for this well and the nearest offsets.</small><button class="secondary-button" data-action="load-trajectories">Load depth view</button></div>';
  const left = 52;
  const top = 52;
  const plotHeight = 218;
  const maxTvd = Math.max(1000, ...state.trajectoryWells.flatMap(function (item) { return (item.surveys || []).map(function (point) { return Number(point.tvd || 0); }); })) * 1.06;
  const colors = ["#4285f4", "#ea4335", "#34a853", "#fbbc05", "#8e63ce", "#11a8a1"];
  const activeOffset = state.trajectoryWells.find(function (item) { return item.well_code === well.well_code; });
  const activeLongitude = activeOffset ? activeOffset.longitude : well.longitude;
  const wellLines = state.trajectoryWells.map(function (item, index) {
    const eastKm = (item.longitude - activeLongitude) * 111.32 * Math.cos(well.latitude * Math.PI / 180);
    const baseX = 300 + eastKm * 18;
    const points = trajectoryPoints(item.surveys || [], baseX, top, plotHeight, maxTvd);
    if (!points.length) return "";
    const coords = points.map(function (point) { return point.x + "," + point.y; }).join(" ");
    const color = colors[index % colors.length];
    const labelY = Math.max(28, top - 14 - index * 2);
    const events = (item.events || []).map(function (event, eventIndex) {
      const depthStart = Number(event.depth_start);
      const depthEnd = Number(event.depth_end);
      const depth = (depthStart + depthEnd) / 2;
      const eventOffset = (eventIndex % 3 - 1) * 4;
      const startX = interpolateTrajectory(points, depthStart, "x") + eventOffset;
      const endX = interpolateTrajectory(points, depthEnd, "x") + eventOffset;
      const startY = interpolateTrajectory(points, depthStart, "y");
      const endY = interpolateTrajectory(points, depthEnd, "y");
      const eventX = interpolateTrajectory(points, depth, "x") + eventOffset;
      const eventY = interpolateTrajectory(points, depth, "y");
      const colorEvent = event.severity === "HIGH" ? "#ea4335" : event.severity === "MEDIUM" ? "#fbbc05" : "#34a853";
      return '<g class="profile-event" data-action="open-event" data-event="' + esc(event.id) + '" tabindex="0" role="button" aria-label="' + esc(eventLabel(event.event_type)) + ' at measured depth ' + number(depthStart, 0) + ' to ' + number(depthEnd, 0) + ' metres"><line x1="' + startX + '" x2="' + endX + '" y1="' + startY + '" y2="' + endY + '" stroke="' + colorEvent + '" stroke-opacity=".82" stroke-width="6" stroke-linecap="round"/><circle cx="' + eventX + '" cy="' + eventY + '" r="4.5" fill="' + colorEvent + '" stroke="#fff" stroke-width="1.5"/><title>' + esc(eventLabel(event.event_type)) + ' · ' + esc(item.well_code) + ' · MD ' + number(depthStart, 0) + '–' + number(depthEnd, 0) + ' m · ' + esc(event.source_document) + ' p.' + number(event.source_page, 0) + '</title></g>';
    }).join("");
    const offset = state.nearby.find(function (nearby) { return nearby.well_code === item.well_code; });
    const relevance = offset ? Math.round(offset.similarity * 100) : 100;
    const distanceText = offset ? number(offset.distance_km, 1) + ' km' : 'Active well';
    return '<g class="profile-well" data-well="' + esc(item.well_code) + '" role="button" tabindex="0" aria-label="' + esc(item.well_code) + ', relevance ' + relevance + ' percent"><polyline points="' + coords + '" fill="none" stroke="' + color + '" stroke-width="' + (item.well_code === well.well_code ? 3.5 : 2.2) + '" stroke-linecap="round" stroke-linejoin="round"/><circle cx="' + points[0].x + '" cy="' + points[0].y + '" r="3.4" fill="' + color + '"/><text class="profile-well-label" x="' + Math.max(40, Math.min(points[0].x + 6, 508)) + '" y="' + labelY + '" fill="' + color + '">' + esc(item.well_code) + (item.well_code === well.well_code ? ' · ACTIVE' : "") + '</text>' + events + mapTooltipMarkup(points[0].x, points[0].y, item.well_code, distanceText, relevance) + '</g>';
  }).join("");
  const grid = [];
  const step = maxTvd > 5000 ? 1000 : 500;
  for (let depth = 0; depth <= maxTvd; depth += step) {
    const y = top + depth / maxTvd * plotHeight;
    grid.push('<line x1="' + left + '" x2="574" y1="' + y + '" y2="' + y + '" class="profile-grid-line"/><text class="profile-depth-label" x="6" y="' + (y + 3) + '">' + number(depth, 0) + '</text>');
  }
  const wellLegend = state.trajectoryWells.map(function (item, index) { return '<span><i style="--well-color:' + colors[index % colors.length] + '"></i>' + esc(item.well_code) + '</span>'; }).join("");
  return '<div class="profile-map-wrap"><svg class="well-map depth-profile" viewBox="0 0 600 310" role="img" aria-label="Survey trajectories and historical events compared by true vertical depth">' +
    '<rect width="600" height="310" fill="#fbfcfa"/><path d="M52 52H574V105C486 96 401 114 318 106S146 96 52 108Z" fill="#f4efe2" opacity=".72"/><path d="M52 108C144 96 231 118 318 106S486 96 574 105V177C486 168 401 185 318 177S146 167 52 180Z" fill="#edf1e7" opacity=".72"/><path d="M52 180C144 167 231 190 318 177S486 168 574 177V270H52Z" fill="#eaf0ef" opacity=".68"/><text class="profile-axis-title" x="8" y="20">TRUE VERTICAL DEPTH · METRES</text><text class="profile-axis-title" x="405" y="20">EASTING + WELLBORE DEVIATION</text>' + grid.join("") + '<line x1="300" x2="300" y1="' + top + '" y2="' + (top + plotHeight) + '" class="profile-center-line"/><line x1="' + left + '" x2="574" y1="' + top + '" y2="' + top + '" class="profile-surface-line"/>' + wellLines + '</svg><div class="profile-well-legend">' + wellLegend + '</div><div class="profile-event-key"><span><i class="high"></i>High event</span><span><i class="medium"></i>Medium event</span><span><i class="low"></i>Low event</span><small>Select an event dot for its record and source.</small></div></div>';
}

async function loadTrajectories() {
  const active = activeWell();
  if (!active) return;
  const targets = [active].concat(state.nearby.slice(0, 5).map(function (item) { return state.wells.find(function (well) { return well.well_code === item.well_code; }); }).filter(Boolean));
  const key = targets.map(function (item) { return item.well_code; }).join("|");
  if (state.trajectoryKey === key && state.trajectoryWells.length) { render(); return; }
  state.trajectoryLoading = true;
  render();
  const results = await Promise.allSettled(targets.map(function (target) {
    return api.well(target.well_code).then(function (result) { return result.well; });
  }));
  state.trajectoryWells = results.filter(function (result) { return result.status === "fulfilled"; }).map(function (result) { return result.value; });
  state.trajectoryKey = key;
  state.trajectoryLoading = false;
  render();
}

function riskCard() {
  const risk = state.risk;
  if (!risk) return '<section class="panel risk-card"><div class="panel-heading"><div><div class="eyebrow">EVIDENCE FIRST</div><h2>Nearby well risk brief</h2></div></div><div class="empty-state compact">' + (state.contextLoading ? "Loading risk evidence…" : "Risk evidence is unavailable. Check the API connection and retry.") + "</div></section>";
  const noSignal = risk.severity === "UNKNOWN";
  const score = Math.round((risk.risk_score || 0) * 100);
  const evidenceCount = risk.evidence_count || 0;
  return '<section class="panel risk-card">' +
    '<div class="panel-heading"><div><div class="eyebrow">EVIDENCE FIRST</div><h2>Nearby well risk brief</h2></div><button class="text-button" data-route="risk">Full brief ' + icon("arrow") + "</button></div>" +
    '<div class="risk-main-row"><div class="risk-dial ' + severityClass(risk.severity) + '" style="--score:' + score + '%"><div><strong>' + (noSignal ? "—" : score) + '</strong><small>' + (noSignal ? "NO SIGNAL" : "RISK SCORE") + "</small></div></div>" +
      '<div class="risk-summary"><div class="risk-title-line"><h3>' + esc(noSignal ? "No significant signal" : "Potential " + risk.risk_label.toLowerCase()) + "</h3>" + riskBadge(risk.severity, noSignal ? "Limited evidence" : risk.severity) + "</div>" +
      '<p>' + esc(risk.explanation) + "</p>" +
      '<div class="risk-summary-meta"><span><b>' + number(evidenceCount, 0) + "</b> matching event" + (evidenceCount === 1 ? "" : "s") + '</span><span class="meta-separator">·</span><span><b>' + (noSignal ? "—" : Math.round((risk.confidence || 0) * 100) + "%") + "</b> confidence</span></div></div></div>" +
    '<div class="risk-evidence-preview">' + (evidenceCount
      ? risk.evidence.slice(0, 3).map(function (item) {
          return '<button class="evidence-chip" data-action="open-event" data-event="' + esc(item.id || item.event_id) + '"><span class="evidence-dot"></span><span><strong>' + esc(item.well_code) + "</strong><small>" + number(item.depth_start, 0) + "–" + number(item.depth_end, 0) + " m · " + esc(item.source_document) + "</small></span><span class=\"chip-distance\">" + number(item.distance_km, 1) + " km</span></button>";
        }).join("")
      : '<div class="no-evidence-line"><span>' + icon("check") + "</span><div><strong>No matching offset events</strong><small>Continue monitoring the available indicators at this depth.</small></div></div>") +
    "</div>" +
    '<div class="recommendation-line"><span class="recommendation-icon">' + icon("layers") + '</span><div><small>RECOMMENDED REVIEW</small><p>' + esc(risk.recommended_review) + "</p></div></div>" +
    alertSummaryMarkup() +
    "</section>";
}

function alertSummaryMarkup() {
  const alert = state.alerts.find(function (item) { return item.status === "NEW"; }) || state.alerts.find(function (item) { return item.status === "ACKNOWLEDGED"; });
  if (!alert) return "";
  const evidence = alert.supporting_evidence && alert.supporting_evidence[0];
  return '<div class="alert-inline"><span class="alert-state-tag ' + esc(alert.status.toLowerCase()) + '">' + esc(alert.status) + '</span><div class="alert-inline-copy"><strong>Review ' + esc(eventLabel(alert.risk_type).toLowerCase()) + ' alert</strong><small>' + esc(alert.trigger_reason) + (evidence && evidence.source_document ? ' · ' + esc(evidence.source_document) + (evidence.source_page ? ' p.' + number(evidence.source_page, 0) : "") : "") + '</small></div><button class="text-button" data-route="risk">Evidence</button>' + (alert.status === "NEW" ? '<button class="quiet-button alert-review-button" data-action="alert-status" data-alert="' + esc(alert.id) + '" data-status="acknowledge">Mark reviewed</button>' : "") + '</div>';
}

function alertsPanel() {
  if (!state.alerts.length) return "";
  return '<section class="panel alerts-panel"><div class="panel-heading"><div><div class="eyebrow">CURRENT WELL · ' + esc(state.activeWellCode) + '</div><h2>Review alerts <span class="inline-count">' + state.alerts.length + '</span></h2><p class="panel-subtitle">Threshold-triggered decision-support items with source evidence.</p></div></div><div class="alert-list">' + state.alerts.slice(0, 6).map(function (alert) {
    const first = alert.supporting_evidence && alert.supporting_evidence[0];
    const statusAction = alert.status === "NEW" ? "acknowledge" : alert.status === "ACKNOWLEDGED" ? "resolve" : "";
    return '<article class="alert-row"><span class="alert-state-tag ' + esc(alert.status.toLowerCase()) + '">' + esc(alert.status) + '</span><div class="alert-row-copy"><strong>' + esc(eventLabel(alert.risk_type)) + ' · ' + esc(alert.severity) + '</strong><small>' + esc(alert.trigger_reason) + '</small><small>' + (first ? esc(first.well_code || "Offset") + ' · ' + (first.depth_start === null ? 'depth not extracted' : number(first.depth_start, 0) + '–' + number(first.depth_end, 0) + ' m') + ' · ' + esc(first.source_document || "Source pending") + (first.source_page ? ' p.' + number(first.source_page, 0) : "") : 'No event citation attached') + '</small></div>' + (statusAction ? '<button class="quiet-button alert-review-button" data-action="alert-status" data-alert="' + esc(alert.id) + '" data-status="' + statusAction + '">' + (statusAction === "acknowledge" ? "Mark reviewed" : "Resolve") + '</button>' : "") + '</article>';
  }).join("") + "</div></section>";
}

function correlationPanel() {
  const context = state.correlation;
  if (!context) return "";
  const active = context.active_context || {};
  const reservoir = active.reservoir_properties && active.reservoir_properties[0];
  const mud = active.mud_programs && active.mud_programs[0];
  const casing = active.casing_programs || [];
  const contextItems = [];
  if (reservoir) {
    contextItems.push('<div><small>LITHOLOGY</small><strong>' + esc(reservoir.lithology) + '</strong></div>');
    if (reservoir.porosity_percent !== null) contextItems.push('<div><small>POROSITY</small><strong>' + number(reservoir.porosity_percent, 1) + '%</strong></div>');
    if (reservoir.permeability_md !== null) contextItems.push('<div><small>PERMEABILITY</small><strong>' + number(reservoir.permeability_md, 0) + ' mD</strong></div>');
  }
  if (mud) contextItems.push('<div><small>MUD PROGRAM</small><strong>' + esc(mud.fluid_type) + ' · ' + number(mud.mud_weight_min, 2) + '–' + number(mud.mud_weight_max, 2) + ' sg</strong></div>');
  if (casing.length) contextItems.push('<div><small>CASING SET</small><strong>' + casing.map(function (item) { return esc(item.casing_size) + ' at ' + number(item.setting_depth, 0) + ' m'; }).join(' · ') + '</strong></div>');
  const pressure = state.risk && state.risk.pressure_context;
  const offsets = (context.offsets || []).slice(0, 4).map(function (offset) {
    const event = offset.events && offset.events[0];
    const comparison = offset.parameter_comparison && offset.parameter_comparison.similarity;
    return '<button class="correlation-offset" data-action="open-well" data-well="' + esc(offset.well_code) + '"><strong>' + esc(offset.well_code) + '</strong><span>' + number(offset.distance_km, 1) + ' km · ' + (event ? esc(eventLabel(event.event_type)) + ' · ' + number(event.depth_start, 0) + '–' + number(event.depth_end, 0) + ' m' : 'program / reservoir context') + '</span><small>' + (comparison === null || comparison === undefined ? 'Parameter comparison unavailable' : 'Parameter similarity ' + Math.round(comparison * 100) + '% · local normalized deltas') + '</small></button>';
  }).join("");
  return '<section class="panel correlation-panel"><div class="panel-heading"><div><div class="eyebrow">FORMATION / DEPTH CORRELATION</div><h2>Geology and program context</h2><p class="panel-subtitle">Database records for ' + esc(state.formation) + ' around ' + number(state.depth, 0) + ' m · ' + esc(context.correlation_method) + '</p></div></div>' +
    (contextItems.length ? '<div class="correlation-facts">' + contextItems.join("") + '</div>' : '<div class="empty-state compact">No structured reservoir, mud, or casing record is available for the active interval.</div>') +
    '<div class="correlation-bottom"><div><small class="correlation-section-label">COMPARABLE OFFSETS</small>' + (offsets || '<div class="empty-inline">No matching offset context is available in the selected radius.</div>') + '</div>' +
    (pressure ? '<div class="pressure-indicator"><small class="correlation-section-label">FORMATION PRESSURE INDICATOR · ' + esc(pressure.label) + '</small><strong class="pressure-level ' + esc(pressure.level.toLowerCase()) + '">' + esc(pressure.level.replaceAll("_", " ")) + '</strong><span>' + number(pressure.pressure_event_count, 0) + ' nearby pressure-related event(s) · ' + (pressure.current_mud_weight === null ? 'mud weight unavailable' : 'current mud weight ' + number(pressure.current_mud_weight, 2) + ' sg') + '</span><small>' + esc(pressure.note) + '</small></div>' : "") +
    '</div></section>';
}

function eventRows(events, limit) {
  if (!events.length) return '<tr><td colspan="6"><div class="empty-table">No historical events match this interval.</div></td></tr>';
  return events.slice(0, limit || events.length).map(function (event) {
    return '<tr class="clickable-row" data-action="open-event" data-event="' + esc(event.id) + '" tabindex="0">' +
      '<td><strong>' + esc(event.well_code) + '</strong><small>' + esc(event.field) + "</small></td>" +
      "<td>" + number(event.depth_start, 0) + "–" + number(event.depth_end, 0) + " m</td><td>" + esc(event.formation) + "</td>" +
      '<td><span class="event-type"><i class="event-icon ' + severityClass(event.severity) + '"></i>' + esc(eventLabel(event.event_type)) + "</span></td>" +
      "<td>" + riskBadge(event.severity, event.severity) + "</td>" +
      '<td><span class="source-ref">' + esc(event.source_document) + " · p." + number(event.source_page, 0) + "</span></td></tr>";
  }).join("");
}

function telemetryStrip() {
  const reading = state.telemetry;
  if (!reading) return '<div class="empty-inline">' + (state.contextLoading ? "Loading telemetry…" : "No telemetry readings are available for this well.") + "</div>";
  const metrics = [
    ["ROP", number(reading.rop, 1), "m/hr"],
    ["WOB", number(reading.wob, 1), "klbf"],
    ["RPM", number(reading.rpm, 0), "rpm"],
    ["TORQUE", number(reading.torque, 1), "kN·m"],
    ["SPP", number(reading.standpipe_pressure, 0), "bar"],
    ["MUD WEIGHT", number(reading.mud_weight, 2), "sg"],
    ["FLOW", number(reading.flow_rate, 2), "m³/min"],
    ["PIT VOLUME", number(reading.pit_volume, 1), "m³"]
  ];
  return '<div class="telemetry-strip">' + metrics.map(function (item, index) {
    return '<div class="telemetry-cell"><div class="telemetry-label"><span>' + item[0] + "</span>" + (index === 0 ? '<i class="live-pulse"></i>' : "") + "</div><strong>" + item[1] + '<small>' + item[2] + "</small></strong></div>";
  }).join("") + "</div>";
}

function dashboardPage() {
  const well = activeWell();
  const risk = state.risk;
  const relevant = evidenceEvents();
  const countInRadius = nearbyCount();
  const latestTime = formatTime(state.telemetry && state.telemetry.timestamp);
  const exactEvents = relevant.filter(function (event) { return event.formation === state.formation; });
  const hello = liveGreeting();
  const eventSubset = state.events.filter(function (event) {
    return Math.abs(event.depth_start - state.depth) <= 160 || (event.depth_start <= state.depth && event.depth_end >= state.depth);
  }).sort(function (a, b) { return Math.abs(a.depth_start - state.depth) - Math.abs(b.depth_start - state.depth); });
  return pageHeading("OPERATIONS / " + (well ? well.field.toUpperCase() : "FIELD"), '<span data-live-greeting>' + hello + ", engineer.</span>", "A clear view of the well context, nearby history, and current evidence.", true) +
    '<div class="metric-grid">' +
      metricCard("Current depth", number(state.depth, 0) + '<small class="metric-unit">m</small>', '<span class="metric-subtle">' + esc(state.formation) + " formation · measured depth</span>", "layers", "coral") +
      metricCard("Nearby offsets", number(countInRadius, 0), '<span class="metric-subtle">within ' + number(state.radius, 0) + " km · " + number(state.health ? state.health.wells : 0, 0) + " wells indexed</span>", "pin", "blue") +
      metricCard("Matching events", number(exactEvents.length, 0), '<span class="metric-subtle">same formation · within 150 m</span>', "events", "gold") +
      metricCard("Latest telemetry", '<span class="metric-live">' + esc(latestTime) + "</span>", '<span class="metric-subtle">' + esc(state.activeWellCode) + " drilling parameters</span>", "clock", "green") +
    "</div>" +
    '<div class="dashboard-main-grid">' +
      '<section class="panel map-panel"><div class="panel-heading"><div><div class="eyebrow">GEOSPATIAL CONTEXT</div><h2>Offset well map</h2><p class="panel-subtitle">' + esc(well ? well.field : "") + " · centered on " + esc(state.activeWellCode) + " · local development coordinates</p></div><button class=\"quiet-button map-explore-button\" data-route=\"wells\">Explore wells " + icon("arrow") + "</button></div>" +
        '<div class="map-panel-toolbar"><div class="map-view-controls"><div class="map-view-switch" role="tablist" aria-label="Map view"><button role="tab" aria-selected="' + (state.mapView === "surface") + '" class="' + (state.mapView === "surface" ? "active" : "") + '" data-action="map-view" data-view="surface">Surface</button><button role="tab" aria-selected="' + (state.mapView === "profile") + '" class="' + (state.mapView === "profile" ? "active" : "") + '" data-action="map-view" data-view="profile">2.5D depth</button></div><label class="radius-map-control"><span>OFFSET RADIUS</span><select id="radius-select" aria-label="Map offset radius"><option value="5" ' + (state.radius === 5 ? "selected" : "") + '>5 km</option><option value="10" ' + (state.radius === 10 ? "selected" : "") + '>10 km</option><option value="25" ' + (state.radius === 25 ? "selected" : "") + '>25 km</option></select></label></div><div class="map-record-actions"><button class="quiet-button" data-action="add-well">' + icon("plus") + ' Add well</button><button class="quiet-button" data-action="documents">' + icon("document") + ' Documents</button></div></div>' +
        '<div class="map-legend">' + (state.mapView === "surface" ? '<span><i class="legend-active"></i>Active well</span><span><i class="legend-offset"></i>Offset well</span><span><i class="legend-evidence"></i>Matching events</span><span class="map-result-count">' + countInRadius + ' offsets in radius</span>' : '<span><i class="legend-active"></i>Survey trajectory</span><span><i class="legend-evidence"></i>Historical event at TVD</span><span class="map-result-count">Depth axis uses survey TVD · event intervals use measured depth</span>') + '</div>' +
        '<div class="map-canvas ' + (state.mapView === "profile" ? "profile-canvas" : "") + '">' + mapSvg() + (state.mapView === "surface" ? '<div class="map-hover-card" id="map-hover-card" hidden aria-hidden="true"><strong class="map-hover-heading"></strong><span class="map-hover-relevance"><small>RELEVANCE</small><b class="map-hover-percent"></b></span></div>' : '') + (state.mapView === "surface" ? '<div class="map-zoom-controls" aria-label="Map zoom"><button data-action="map-zoom" data-delta="1" aria-label="Zoom in">' + icon("zoomIn") + '</button><button data-action="map-zoom" data-delta="-1" aria-label="Zoom out">' + icon("zoomOut") + '</button></div><div class="map-scale"><span style="width:' + number(2 * Math.min(12.4, 150 / Number(state.radius)) * state.mapZoom, 1) + 'px"></span> 2 km</div>' : '') + '</div>' + (state.mapView === "profile" ? '<div class="profile-source-note">Trajectory survey stations and event reports are shown from local records. Event source citations remain available from each marker.</div>' : '') +
      "</section>" +
      riskCard() +
    "</div>" +
    '<div class="dashboard-lower-grid">' +
      '<section class="panel telemetry-panel"><div class="panel-heading"><div><div class="eyebrow">CURRENT WELL · ' + esc(state.activeWellCode) + '</div><h2>Drilling parameters</h2></div><div class="reading-time"><i class="live-pulse"></i>Updated ' + esc(latestTime) + "</div></div>" +
        telemetryStrip() + '<div class="telemetry-footer"><span>Development telemetry · simulated readings</span><button class="text-button" data-action="simulate">' + icon("clock") + "Advance demo reading</button></div>" +
      "</section>" +
      '<section class="panel nearby-events-panel"><div class="panel-heading"><div><div class="eyebrow">DEPTH PROXIMITY</div><h2>Events near this interval</h2></div><button class="text-button" data-route="events">All events ' + icon("arrow") + "</button></div>" +
        (eventSubset.length ? '<div class="compact-event-list">' + eventSubset.slice(0, 4).map(function (event) {
          const gap = Math.max(0, Math.max(event.depth_start - state.depth, state.depth - event.depth_end));
          return '<button class="compact-event" data-action="open-event" data-event="' + esc(event.id) + '"><span class="compact-event-mark ' + severityClass(event.severity) + '">' + icon("events") + "</span><span class=\"compact-event-copy\"><strong>" + esc(eventLabel(event.event_type)) + " <small>" + esc(event.well_code) + "</small></strong><span>" + esc(event.formation) + " · " + number(event.depth_start, 0) + "–" + number(event.depth_end, 0) + " m</span></span><span class=\"event-gap\">" + (gap ? number(gap, 0) + " m away" : "at depth") + "</span></button>";
        }).join("") + "</div>" : '<div class="empty-state compact">No historical events match this interval.</div>') +
      "</section>" +
    "</div>";
}

function wellDirectoryPage() {
  const query = state.wellSearch.toLowerCase();
  const visible = state.wells.filter(function (well) {
    return !query || [well.well_code, well.name, well.field, well.formation].join(" ").toLowerCase().includes(query);
  });
  const rows = visible.map(function (well) {
    const distance = well.well_code === state.activeWellCode ? 0 : state.nearby.find(function (item) { return item.well_code === well.well_code; });
    const distanceText = well.well_code === state.activeWellCode ? "Active" : distance ? number(distance.distance_km, 1) + " km" : "—";
    const eventCount = state.events.filter(function (event) { return event.well_code === well.well_code; }).length;
    return '<tr class="clickable-row" data-action="view-well" data-well="' + esc(well.well_code) + '" tabindex="0"><td><div class="well-code-cell"><span class="well-table-mark ' + (well.well_code === state.activeWellCode ? "is-active" : "") + '">' + icon("pin") + "</span><span><strong>" + esc(well.well_code) + "</strong><small>" + esc(well.name) + "</small></span></div></td><td>" + esc(well.field) + '</td><td><span class="formation-pill">' + esc(well.formation) + "</span></td><td>" + number(well.total_depth, 0) + " m</td><td>" + (well.current_depth ? number(well.current_depth, 0) + " m" : '<span class="muted">—</span>') + "</td><td>" + riskBadge(well.status === "drilling" ? "medium" : "low", well.status) + "</td><td>" + distanceText + '</td><td><span class="event-count">' + eventCount + "</span></td></tr>";
  }).join("");
  return pageHeading("WELL INVENTORY", "Well directory", "Explore development wells, compare offset context, and open a well record.", true) +
    '<div class="directory-summary"><div><strong>' + state.wells.length + '</strong><span>wells indexed</span></div><div class="summary-divider"></div><div><strong>' + new Set(state.wells.map(function (well) { return well.field; })).size + '</strong><span>field clusters</span></div><div class="summary-divider"></div><div><strong>' + state.events.length + '</strong><span>historical events</span></div><div class="directory-search"><span>' + icon("wells") + '</span><input id="well-search" value="' + esc(state.wellSearch) + '" placeholder="Search well, field, formation" aria-label="Search wells"><kbd>⌘ K</kbd></div></div>' +
    '<section class="panel table-panel"><div class="table-heading-row"><div><h2>All wells</h2><p>Distances are measured from ' + esc(state.activeWellCode) + ".</p></div><span class=\"data-disclosure\">Synthetic development records</span></div>" +
    '<div class="table-scroll"><table><thead><tr><th>WELL</th><th>FIELD</th><th>FORMATION</th><th>TOTAL DEPTH</th><th>CURRENT DEPTH</th><th>STATUS</th><th>FROM ACTIVE</th><th>EVENTS</th></tr></thead><tbody>' + (rows || '<tr><td colspan="8"><div class="empty-table">No wells match this search.</div></td></tr>') + "</tbody></table></div></section>";
}

function evidenceDocumentsSection() {
  const rows = state.documents.slice(0, 3).map(function (document) {
    const status = document.extraction_status === "ready" ? "Indexed" : document.extraction_status === "needs_ocr" ? "OCR required" : "No text extracted";
    return '<button class="evidence-document-row" data-action="document-detail" data-document="' + esc(document.id) + '"><span class="document-type-mark">' + icon("document") + '</span><span class="evidence-document-name"><strong>' + esc(document.original_name) + '</strong><small>' + esc(document.well_code || "Well not identified") + ' · ' + esc(document.extension.toUpperCase().replace(".", "")) + '</small></span><span class="evidence-document-counts">' + number(document.extracted_event_count, 0) + ' event candidates · ' + number(document.entity_count, 0) + ' entities</span><span class="document-status ' + (document.extraction_status === "ready" ? "ready" : "pending") + '">' + status + '</span></button>';
  }).join("");
  const more = state.documents.length > 3 ? '<div class="evidence-documents-more">' + (state.documents.length - 3) + ' more in the document library</div>' : "";
  return '<section class="panel evidence-documents-panel"><div class="panel-heading"><div><div class="eyebrow">DOCUMENTS / EXTRACTED KNOWLEDGE</div><h2>Reports and extracted events <span class="inline-count">' + state.documents.length + '</span></h2><p class="panel-subtitle">Extracted event candidates retain their source and await engineering review.</p></div><button class="quiet-button" data-action="documents">Upload report ' + icon("plus") + '</button></div>' +
    (state.documentsLoading ? '<div class="empty-inline">Loading the local document index…</div>' : state.documentsError ? '<div class="empty-inline">Document index unavailable: ' + esc(state.documentsError) + '</div>' : rows ? '<div class="evidence-document-list">' + rows + '</div>' + more : '<div class="empty-state compact">No reports are indexed yet. Upload a WCR, DDR, or other supported file to extract searchable evidence.</div>') + '</section>';
}

function ensureEvidenceDocuments() {
  if (state.documentsLoaded || state.documentsLoading) return;
  state.documentsLoading = true;
  state.documentsError = "";
  api.documents().then(function (result) {
    state.documents = result.documents || [];
    state.documentFormats = result.supported_extensions || [];
    state.documentCapabilities = result.capabilities || {};
    state.documentsLoaded = true;
    state.documentsLoading = false;
    if (state.route === "events") render();
  }).catch(function (error) {
    state.documentsLoading = false;
    state.documentsError = error.message;
    if (state.route === "events") render();
  });
}

function eventSearchPage() {
  const filters = state.eventFilters;
  const visible = state.events.filter(function (event) {
    const search = (filters.q || "").toLowerCase();
    const matchesSearch = !search || [event.well_code, event.description, event.source_document, event.cause].join(" ").toLowerCase().includes(search);
    const matchesType = !filters.event_type || event.event_type === filters.event_type;
    const matchesSeverity = !filters.severity || event.severity === filters.severity;
    const matchesFormation = !filters.formation || event.formation === filters.formation;
    const min = Number(filters.depth_min);
    const max = Number(filters.depth_max);
    const matchesDepth = (!filters.depth_min || event.depth_end >= min) && (!filters.depth_max || event.depth_start <= max);
    return matchesSearch && matchesType && matchesSeverity && matchesFormation && matchesDepth;
  });
  return pageHeading("HISTORICAL KNOWLEDGE", "Evidence", "Search reported events, uploaded documents, and extracted knowledge by well, formation, depth, or event class.", true) +
    '<div class="event-filter-bar"><label class="search-field"><span>' + icon("events") + '</span><input id="event-search" value="' + esc(filters.q) + '" placeholder="Search event, well, source" aria-label="Search events"></label>' +
    '<label><span class="sr-only">Event type</span><select id="event-type-filter"><option value="">All event types</option>' + eventTypeOptions(filters.event_type) + "</select></label>" +
    '<label><span class="sr-only">Severity</span><select id="event-severity-filter"><option value="">All severities</option>' + selectOptions(["HIGH", "MEDIUM", "LOW"], filters.severity) + "</select></label>" +
    '<label><span class="sr-only">Formation</span><select id="event-formation-filter"><option value="">All formations</option>' + selectOptions(["F1", "F2", "F3", "F4"], filters.formation) + "</select></label>" +
    '<div class="depth-filter"><input id="event-depth-min" value="' + esc(filters.depth_min) + '" placeholder="From m" aria-label="Minimum depth"><span>–</span><input id="event-depth-max" value="' + esc(filters.depth_max) + '" placeholder="To m" aria-label="Maximum depth"></div>' +
    '<button class="filter-reset" data-action="reset-events">Reset</button></div>' +
    '<section class="panel table-panel event-results"><div class="table-heading-row"><div><h2>Historical events <span class="inline-count">' + visible.length + "</span></h2><p>Each confirmed record includes its source reference and recorded mitigation.</p></div><span class=\"data-disclosure\">Development dataset</span></div>" +
    '<div class="table-scroll"><table><thead><tr><th>WELL</th><th>DEPTH INTERVAL</th><th>FORMATION</th><th>EVENT</th><th>SEVERITY</th><th>SOURCE</th></tr></thead><tbody>' + eventRows(visible) + "</tbody></table></div></section>" + evidenceDocumentsSection();
}

function eventTypeOptions(selected) {
  return ["MUD_LOSS", "STUCK_PIPE", "KICK_PRESSURE", "OVERPRESSURE", "TORQUE_DRAG", "CEMENTING", "FISHING", "NPT"].map(function (type) {
    return '<option value="' + type + '" ' + (selected === type ? "selected" : "") + ">" + esc(eventLabel(type)) + "</option>";
  }).join("");
}

function selectOptions(options, selected) {
  return options.map(function (value) { return '<option value="' + esc(value) + '" ' + (value === selected ? "selected" : "") + ">" + esc(value) + "</option>"; }).join("");
}

function signalRows(risk) {
  return (risk.signals || []).map(function (signal) {
    const width = Math.round((signal.score || 0) * 100);
    return '<div class="signal-row"><div class="signal-row-label"><span><i class="signal-dot ' + severityClass(signal.severity) + '"></i>' + esc(signal.label) + "</span><span>" + (signal.evidence_count ? signal.evidence_count + " events" : signal.telemetry_signal ? "telemetry" : "no evidence") + "</span></div><div class=\"signal-bar\"><i class=\"" + severityClass(signal.severity) + '" style="width:' + width + '%"></i></div></div>';
  }).join("");
}

function riskPage() {
  const risk = state.risk;
  if (!risk) return pageHeading("DECISION SUPPORT", "Risk intelligence", "Evidence linked to the current well and depth.", true) + '<div class="empty-state">Risk analysis is unavailable. Check the backend connection.</div>';
  const primaryEvidence = risk.evidence || [];
  const isUnknown = risk.severity === "UNKNOWN";
  return pageHeading("DECISION SUPPORT / RULES + OFFSETS", "Risk intelligence", "Interpretation is tied to comparable offset events and current telemetry.", true) +
    '<div class="risk-page-grid"><section class="panel risk-detail-panel"><div class="panel-heading"><div><div class="eyebrow">CURRENT INTERPRETATION</div><h2>' + esc(isUnknown ? "No significant signal" : "Potential " + risk.risk_label.toLowerCase()) + '</h2></div>' + riskBadge(risk.severity, isUnknown ? "Limited evidence" : risk.severity) + "</div>" +
      '<div class="risk-detail-score"><div class="risk-dial large ' + severityClass(risk.severity) + '" style="--score:' + Math.round(risk.risk_score * 100) + '%"><div><strong>' + (isUnknown ? "—" : Math.round(risk.risk_score * 100)) + '</strong><small>SCORE</small></div></div><div><div class="confidence-caption">CONFIDENCE</div><strong class="confidence-value">' + (isUnknown ? "—" : Math.round(risk.confidence * 100) + "%") + '</strong><p>' + esc(risk.explanation) + "</p></div></div>" +
      '<div class="interpretation-box"><div class="interpretation-heading"><span class="interpretation-icon">' + icon("layers") + '</span><div><strong>Recommended review</strong><small>Decision support only · engineer review required</small></div></div><p>' + esc(risk.recommended_review) + "</p></div>" +
      '<div class="risk-provenance"><span>MODEL <b>' + esc(risk.model_version) + '</b></span><span>RADIUS <b>' + number(risk.radius_km, 0) + ' km</b></span><span>DEPTH WINDOW <b>±150 m</b></span><span>FORMATION <b>' + esc(risk.formation) + "</b></span></div>" +
    "</section>" +
    '<section class="panel signal-panel"><div class="panel-heading"><div><div class="eyebrow">RULE + OFFSET SIGNALS</div><h2>Risk categories</h2></div></div><p class="panel-subtitle">Scores use matching depth, same formation, offset distance, and telemetry indicators.</p><div class="signal-list">' + signalRows(risk) + "</div><div class=\"signal-weights\"><strong>Risk score components</strong><p>With offset evidence: 0.30 base + 0.10 per event (capped at 4) + 0.11 × depth fit + 0.08 formation match + 0.05 × geographic fit. A configured telemetry indicator adds 0.10; telemetry-only signals use lower confidence.</p></div></section></div>" +
    correlationPanel() + alertsPanel() +
    '<section class="panel evidence-panel"><div class="panel-heading"><div><div class="eyebrow">TRACEABLE SOURCE RECORDS</div><h2>Evidence <span class="inline-count">' + primaryEvidence.length + "</span></h2><p class=\"panel-subtitle\">Interpretation stays separate from the reported event facts.</p></div><button class=\"quiet-button\" data-route=\"events\">Search all evidence " + icon("arrow") + "</button></div>" +
      (primaryEvidence.length ? '<div class="evidence-list">' + primaryEvidence.map(function (item, index) {
        return '<article class="evidence-row"><div class="evidence-index">' + String(index + 1).padStart(2, "0") + '</div><div class="evidence-well"><strong>' + esc(item.well_code) + "</strong><small>" + number(item.distance_km, 1) + " km offset</small></div><div class=\"evidence-facts\"><div><small>DEPTH</small><strong>" + number(item.depth_start, 0) + "–" + number(item.depth_end, 0) + " m</strong></div><div><small>FORMATION</small><strong>" + esc(item.formation) + "</strong></div><div><small>EVENT</small><strong>" + esc(eventLabel(item.event_type)) + " · " + esc(item.severity) + "</strong></div></div><div class=\"evidence-source\"><small>SOURCE RECORD</small><button data-action=\"open-event\" data-event=\"" + esc(item.id || item.event_id) + "\">" + esc(item.source_document) + " · page " + number(item.source_page, 0) + " " + icon("arrow") + "</button></div></article>";
      }).join("") + "</div>" : '<div class="empty-state compact">No same-formation event was found within the selected depth window.</div>') +
    "</section>";
}

function render() {
  if (state.loading) return setLoading();
  if (state.error && !state.wells.length) {
    appRoot.innerHTML = '<div class="failure-screen"><div class="failure-mark">!</div><div class="eyebrow">CONNECTION ISSUE</div><h1>Drilling data is unavailable.</h1><p>' + esc(state.error) + '</p><button class="primary-button" data-action="retry">Retry connection</button></div>';
    const retry = document.querySelector('[data-action="retry"]');
    if (retry) retry.addEventListener("click", loadData);
    return;
  }
  let content = dashboardPage();
  if (state.route === "wells") content = wellDirectoryPage();
  if (state.route === "events") content = eventSearchPage();
  if (state.route === "risk") content = riskPage();
  renderShell(content);
  bindPage();
  scheduleGreetingUpdate();
  if (state.route === "events") ensureEvidenceDocuments();
}

function bindPage() {
  document.querySelectorAll("[data-route]").forEach(function (element) {
    element.addEventListener("click", function (event) {
      const route = element.dataset.route;
      if (!route) return;
      event.preventDefault();
      window.location.hash = route;
    });
  });
  const hoverCard = document.getElementById("map-hover-card");
  if (hoverCard) {
    const mapCanvas = hoverCard.parentElement;
    const heading = hoverCard.querySelector(".map-hover-heading");
    const percentage = hoverCard.querySelector(".map-hover-percent");
    const hideHoverCard = function () {
      hoverCard.hidden = true;
      hoverCard.setAttribute("aria-hidden", "true");
    };
    document.querySelectorAll(".satellite-map .map-well, .satellite-map .map-active").forEach(function (marker) {
      const showHoverCard = function () {
        heading.textContent = marker.dataset.well + " · " + marker.dataset.distance;
        percentage.textContent = marker.dataset.relevance + "%";
        hoverCard.hidden = false;
        hoverCard.setAttribute("aria-hidden", "false");
        const canvasBounds = mapCanvas.getBoundingClientRect();
        const markerBounds = marker.getBoundingClientRect();
        let left = markerBounds.right - canvasBounds.left + 9;
        let top = markerBounds.top - canvasBounds.top + (markerBounds.height - hoverCard.offsetHeight) / 2;
        if (left + hoverCard.offsetWidth > canvasBounds.width - 8) left = markerBounds.left - canvasBounds.left - hoverCard.offsetWidth - 9;
        left = Math.max(8, Math.min(left, Math.max(8, canvasBounds.width - hoverCard.offsetWidth - 8)));
        top = Math.max(8, Math.min(top, Math.max(8, canvasBounds.height - hoverCard.offsetHeight - 8)));
        hoverCard.style.left = left + "px";
        hoverCard.style.top = top + "px";
      };
      marker.addEventListener("mouseenter", showHoverCard);
      marker.addEventListener("mouseleave", hideHoverCard);
      marker.addEventListener("focus", showHoverCard);
      marker.addEventListener("blur", hideHoverCard);
    });
  }
  document.querySelectorAll(".map-well, .map-active, .profile-well").forEach(function (element) {
    const choose = function () {
      state.selectedOffset = element.dataset.well;
      document.querySelectorAll(".map-well").forEach(function (marker) {
        marker.classList.toggle("selected", marker.dataset.well === state.selectedOffset);
      });
      showWellDialog(element.dataset.well, false);
    };
    element.addEventListener("click", choose);
    element.addEventListener("keydown", function (event) {
      if (event.target.closest && event.target.closest(".profile-event")) return;
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); choose(); }
    });
  });
  document.querySelectorAll('[data-action="open-well"]').forEach(function (element) {
    element.addEventListener("click", function () { showWellDialog(element.dataset.well); });
  });
  document.querySelectorAll('[data-action="view-well"]').forEach(function (element) {
    element.addEventListener("click", function () { showWellDialog(element.dataset.well); });
    element.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); showWellDialog(element.dataset.well); }
    });
  });
  document.querySelectorAll('[data-action="open-event"]').forEach(function (element) {
    element.addEventListener("click", function (event) {
      event.stopPropagation();
      showEventDialog(element.dataset.event);
    });
    if (element.tagName === "TR") {
      element.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); showEventDialog(element.dataset.event); }
      });
    } else if (element.classList.contains("profile-event")) {
      element.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); showEventDialog(element.dataset.event); }
      });
    }
  });
  document.querySelectorAll('[data-action="map-view"]').forEach(function (element) {
    element.addEventListener("click", function () {
      state.mapView = element.dataset.view;
      render();
      if (state.mapView === "profile") loadTrajectories();
    });
  });
  document.querySelectorAll('[data-action="map-zoom"]').forEach(function (element) {
    element.addEventListener("click", function () {
      state.mapZoom = Math.max(0.7, Math.min(2, state.mapZoom + Number(element.dataset.delta) * 0.25));
      render();
    });
  });
  document.querySelectorAll('[data-action="load-trajectories"]').forEach(function (element) {
    element.addEventListener("click", loadTrajectories);
  });
  document.querySelectorAll('[data-action="add-well"]').forEach(function (element) {
    element.addEventListener("click", showAddWellDialog);
  });
  document.querySelectorAll('[data-action="documents"]').forEach(function (element) {
    element.addEventListener("click", showDocumentsDialog);
  });
  document.querySelectorAll('[data-action="document-detail"]').forEach(function (element) {
    element.addEventListener("click", function () { showDocumentDialog(element.dataset.document); });
  });
  document.querySelectorAll('[data-action="alert-status"]').forEach(function (element) {
    element.addEventListener("click", async function () {
      element.disabled = true;
      try {
        const response = await api.updateAlert(element.dataset.alert, element.dataset.status);
        state.alerts = state.alerts.map(function (item) { return item.id === response.alert.id ? response.alert : item; });
        render();
      } catch (error) {
        state.error = error.message;
        render();
      }
    });
  });
  const simulator = document.querySelector('[data-action="simulate"]');
  if (simulator) simulator.addEventListener("click", simulateTelemetry);
  const resetEvents = document.querySelector('[data-action="reset-events"]');
  if (resetEvents) resetEvents.addEventListener("click", function () {
    state.eventFilters = { q: "", event_type: "", severity: "", formation: "", depth_min: "", depth_max: "" };
    render();
  });
  bindEventFilters();
  bindWellSearch();
}

function bindEventFilters() {
  const fields = {
    "event-search": "q",
    "event-type-filter": "event_type",
    "event-severity-filter": "severity",
    "event-formation-filter": "formation",
    "event-depth-min": "depth_min",
    "event-depth-max": "depth_max"
  };
  Object.keys(fields).forEach(function (id) {
    const element = document.getElementById(id);
    if (!element) return;
    element.addEventListener(id === "event-search" ? "input" : "change", function () {
      state.eventFilters[fields[id]] = this.value;
      const cursor = this.selectionStart;
      render();
      const replacement = document.getElementById(id);
      if (replacement && id === "event-search") {
        replacement.focus();
        replacement.setSelectionRange(cursor, cursor);
      }
    });
  });
}

function bindWellSearch() {
  const search = document.getElementById("well-search");
  if (!search) return;
  search.addEventListener("input", function () {
    state.wellSearch = this.value;
    const cursor = this.selectionStart;
    render();
    const replacement = document.getElementById("well-search");
    if (replacement) { replacement.focus(); replacement.setSelectionRange(cursor, cursor); }
  });
}

async function simulateTelemetry() {
  const button = document.querySelector('[data-action="simulate"]');
  if (button) { button.disabled = true; button.textContent = "Advancing reading…"; }
  const current = state.telemetry || {};
  state.simulatorStep += 1;
  const baseline = state.simulatorStep % 2 === 1;
  const nextDepth = Math.min(8000, Number(state.depth) + 10);
  const reading = {
    well_id: state.activeWellCode,
    depth: nextDepth,
    formation: state.formation,
    rop: baseline ? 17.6 : 15.2,
    wob: 13.8,
    rpm: 112,
    torque: 13.1,
    standpipe_pressure: baseline ? 177 : 179,
    mud_weight: Number(current.mud_weight || 1.16),
    flow_rate: baseline ? 1.78 : 1.48,
    pit_volume: baseline ? Number(current.pit_volume || 38.3) : Math.max(0, Number(current.pit_volume || 38.3) - 0.9)
  };
  try {
    const result = await api.sendTelemetry(reading);
    state.depth = nextDepth;
    state.activeWell = Object.assign({}, activeWell(), { current_depth: nextDepth });
    state.telemetry = result.reading;
    await loadContext();
    render();
  } catch (error) {
    state.error = error.message;
    render();
  }
}

function showAddWellDialog() {
  const formationOptions = state.formations.map(function (formation) {
    return '<option value="' + esc(formation.name) + '" ' + (formation.name === state.formation ? "selected" : "") + '>' + esc(formation.name) + ' · ' + number(formation.top_depth, 0) + '–' + number(formation.bottom_depth, 0) + ' m</option>';
  }).join("");
  dialogRoot.innerHTML = '<div class="dialog-backdrop" data-action="close-dialog"><section class="detail-dialog form-dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><button class="dialog-close" data-action="close-dialog" aria-label="Close">' + icon("close") + '</button><div class="dialog-kicker">WELL INVENTORY / NEW RECORD</div><h2 id="dialog-title">Add a well</h2><p class="form-intro">Enter a location and basic well details. The record is saved to this local workspace.</p><form id="add-well-form" class="data-form"><div class="form-grid"><label><span>Well code</span><input name="well_code" placeholder="e.g. DUL-101" maxlength="24" required></label><label><span>Well name</span><input name="name" placeholder="Well name" maxlength="120" required></label><label><span>Field</span><input name="field" placeholder="Field or block" maxlength="80" required></label><label><span>Formation</span><select name="formation" required>' + formationOptions + '</select></label><label><span>Latitude</span><input name="latitude" type="number" min="-90" max="90" step="any" placeholder="27.2000" required></label><label><span>Longitude</span><input name="longitude" type="number" min="-180" max="180" step="any" placeholder="95.3000" required></label><label><span>Total depth (m)</span><input name="total_depth" type="number" min="1" max="8000" step="1" placeholder="3200" required></label><label><span>Current depth (m)</span><input name="current_depth" type="number" min="0" max="8000" step="1" placeholder="Optional"></label><label><span>Status</span><select name="status"><option value="planned">Planned</option><option value="drilling">Drilling</option><option value="paused">Paused</option><option value="completed">Completed</option></select></label><label><span>Spud date</span><input name="spud_date" type="date"></label></div><div id="well-form-feedback" class="form-feedback" role="alert"></div><div class="dialog-actions"><button class="secondary-button" type="button" data-action="close-dialog">Cancel</button><button class="primary-button" type="submit">Save well</button></div></form></section></div>';
  bindDialog();
  document.getElementById("add-well-form").addEventListener("submit", async function (event) {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = form.querySelector('[type="submit"]');
    const feedback = document.getElementById("well-form-feedback");
    submit.disabled = true;
    submit.textContent = "Saving well…";
    feedback.textContent = "";
    const values = Object.fromEntries(new FormData(form).entries());
    values.well_code = values.well_code.trim().toUpperCase();
    ["latitude", "longitude", "total_depth"].forEach(function (key) { values[key] = Number(values[key]); });
    values.current_depth = values.current_depth === "" ? null : Number(values.current_depth);
    try {
      const result = await api.addWell(values);
      const list = await api.wells();
      state.wells = list.wells || [];
      if (state.health) state.health.wells = state.wells.length;
      const added = state.wells.find(function (item) { return item.well_code === result.well.well_code; }) || result.well;
      state.activeWellCode = added.well_code;
      state.activeWell = added;
      state.depth = added.current_depth === null || added.current_depth === undefined ? 0 : Number(added.current_depth);
      state.formation = added.formation;
      state.selectedOffset = null;
      state.trajectoryKey = null;
      state.trajectoryWells = [];
      state.nearby = [];
      state.events = [];
      state.risk = null;
      state.telemetry = null;
      state.contextLoading = true;
      dialogRoot.innerHTML = "";
      connectTelemetry(added.well_code);
      render();
      loadContext().then(async function () {
        state.contextLoading = false;
        if (state.mapView === "profile") await loadTrajectories();
        render();
      }).catch(function (error) {
        state.contextLoading = false;
        state.error = error.message;
        render();
      });
    } catch (error) {
      feedback.textContent = error.message;
      submit.disabled = false;
      submit.textContent = "Save well";
    }
  });
}

function showDocumentsDialog() {
  dialogRoot.innerHTML = '<div class="dialog-backdrop" data-action="close-dialog"><section class="detail-dialog documents-dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><button class="dialog-close" data-action="close-dialog" aria-label="Close">' + icon("close") + '</button><div class="dialog-kicker">LOCAL DOCUMENT LIBRARY</div><h2 id="dialog-title">Evidence documents</h2><p class="form-intro">Upload reports for local text extraction and evidence search. Files stay on this machine.</p><div class="documents-loading"><span class="loader-dots"></span>Reading document library…</div></section></div>';
  bindDialog();
  api.documents().then(function (result) {
    state.documents = result.documents || [];
    state.documentFormats = result.supported_extensions || [];
    state.documentCapabilities = result.capabilities || {};
    state.documentsLoaded = true;
    renderDocumentsDialog("", false, result.max_upload_bytes || 12 * 1024 * 1024);
  }).catch(function (error) { showErrorDialog(error.message); });
}

function renderDocumentsDialog(message, isError, maxBytes) {
  const formats = state.documentFormats.length ? state.documentFormats.join(", ") : ".pdf, .docx, .txt, .md, .csv, .json, .log, .png, .jpg, .tif";
  const capabilities = state.documentCapabilities;
  const ocrNote = capabilities.tesseract_ocr
    ? (capabilities.scanned_pdf_renderer ? "Local Tesseract OCR is available for images and scanned PDFs." : "Local image OCR is available; scanned PDFs also need PyMuPDF.")
    : "OCR is not installed here. Text-based files still work; images and scanned PDFs will be marked OCR required and will not be indexed.";
  const list = state.documents.length ? state.documents.map(function (document) {
    const status = document.extraction_status === "ready" ? "Indexed" : document.extraction_status === "needs_ocr" ? "OCR required" : "No text found";
    return '<button class="document-row" data-action="document-detail" data-document="' + esc(document.id) + '"><span class="document-type-mark">' + icon("document") + '</span><span class="document-row-copy"><strong>' + esc(document.original_name) + '</strong><small>' + esc(document.well_code || "Well not identified") + ' · ' + esc(document.extension.toUpperCase().replace(".", "")) + ' · ' + number(document.size_bytes / 1024, 0) + ' KB · ' + esc(status) + ' · ' + number(document.extracted_event_count, 0) + ' event candidates</small></span><span class="document-row-arrow">' + icon("arrow") + '</span></button>';
  }).join("") : '<div class="empty-state compact">No reports uploaded yet. Add a document to make its text searchable.</div>';
  const sizeNote = maxBytes ? number(maxBytes / (1024 * 1024), 0) + ' MB maximum per file.' : '12 MB maximum per file.';
  dialogRoot.innerHTML = '<div class="dialog-backdrop" data-action="close-dialog"><section class="detail-dialog documents-dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><button class="dialog-close" data-action="close-dialog" aria-label="Close">' + icon("close") + '</button><div class="dialog-kicker">LOCAL DOCUMENT LIBRARY</div><h2 id="dialog-title">Evidence documents <span class="inline-count">' + state.documents.length + '</span></h2><p class="form-intro">Upload reports for local text extraction and evidence search. Files stay on this machine.</p><form id="document-upload-form" class="upload-form"><label class="upload-drop"><span class="upload-icon">' + icon("document") + '</span><strong>Choose a report or image</strong><small id="upload-file-name">PDF, DOCX, text, CSV, JSON, or image · ' + sizeNote + '</small><input id="document-file" type="file" accept="' + esc(formats) + '" required></label><button class="primary-button" type="submit">Upload and index</button></form><div class="supported-formats">Supported: ' + esc(formats.toUpperCase()) + ' · ' + esc(ocrNote) + '</div><div id="document-form-feedback" class="form-feedback ' + (isError ? "is-error" : "") + '" role="status">' + esc(message || "") + '</div><div class="documents-list-heading"><strong>Recent uploads</strong><span>' + state.documents.length + ' files</span></div><div class="documents-list">' + list + '</div></section></div>';
  bindDialog();
  const fileInput = document.getElementById("document-file");
  fileInput.addEventListener("change", function () {
    const label = document.getElementById("upload-file-name");
    label.textContent = fileInput.files[0] ? fileInput.files[0].name + ' · ' + number(fileInput.files[0].size / 1024, 0) + ' KB' : "Choose a supported report or image.";
  });
  dialogRoot.querySelectorAll('[data-action="document-detail"]').forEach(function (button) {
    button.addEventListener("click", function () { showDocumentDialog(button.dataset.document); });
  });
  document.getElementById("document-upload-form").addEventListener("submit", async function (event) {
    event.preventDefault();
    const file = fileInput.files[0];
    if (!file) return;
    const submit = event.currentTarget.querySelector('[type="submit"]');
    submit.disabled = true;
    submit.textContent = "Extracting text…";
    const feedback = document.getElementById("document-form-feedback");
    feedback.classList.remove("is-error");
    feedback.textContent = "Processing this file locally…";
    try {
      const response = await api.uploadDocument(file);
      const uploaded = response.document;
      const library = await api.documents();
      state.documents = library.documents || [];
      state.documentCapabilities = library.capabilities || {};
      state.documentsLoaded = true;
      renderDocumentsDialog(uploaded.extraction_note, uploaded.extraction_status !== "ready", library.max_upload_bytes);
    } catch (error) {
      submit.disabled = false;
      submit.textContent = "Upload and index";
      feedback.classList.add("is-error");
      feedback.textContent = error.message;
    }
  });
}

function showDocumentDialog(documentId) {
  dialogRoot.innerHTML = '<div class="dialog-backdrop" data-action="close-dialog"><section class="detail-dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><div class="documents-loading"><span class="loader-dots"></span>Opening document record…</div></section></div>';
  bindDialog();
  api.document(documentId).then(function (result) {
    const document = result.document;
    const entities = document.entities || {};
    const extractedEvents = document.extractions && document.extractions.events ? document.extractions.events : [];
    const chips = Object.keys(entities).filter(function (key) { return entities[key] && entities[key].length; }).map(function (key) {
      const values = entities[key].map(function (value) { return '<span class="entity-chip">' + esc(value) + '</span>'; }).join("");
      return '<div class="entity-group"><small>' + esc(key.replaceAll("_", " ")) + '</small><div>' + values + '</div></div>';
    }).join("");
    const extracted = String(document.extracted_text || "").trim();
    const eventRows = extractedEvents.map(function (item) {
      const depth = item.depth_start === null || item.depth_start === undefined ? "Depth not extracted" : number(item.depth_start, 0) + "–" + number(item.depth_end, 0) + " m";
      return '<article class="extracted-event-card"><div class="extracted-event-heading"><strong>' + esc(eventLabel(item.event_type)) + '</strong><span>' + esc(item.review_status) + ' · ' + esc(item.severity) + '</span></div><p>' + esc(item.description) + '</p><small>' + esc(item.linked_well_code || item.well_code || "Well not identified") + ' · ' + esc(item.formation || "Formation not extracted") + ' · ' + depth + ' · ' + (item.source_page ? 'page ' + number(item.source_page, 0) : 'page unavailable') + '</small>' + (item.cause ? '<small>Cause/context: ' + esc(item.cause) + '</small>' : "") + (item.mitigation ? '<small>Recorded action: ' + esc(item.mitigation) + '</small>' : "") + '<small>Rule match score: ' + Math.round(item.extraction_confidence * 100) + '% · ' + esc(item.extraction_method) + '</small></article>';
    }).join("");
    dialogRoot.innerHTML = '<div class="dialog-backdrop" data-action="close-dialog"><section class="detail-dialog document-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><button class="dialog-close" data-action="close-dialog" aria-label="Close">' + icon("close") + '</button><div class="dialog-kicker">DOCUMENT / ' + esc(document.id) + '</div><div class="document-detail-heading"><span class="document-type-mark">' + icon("document") + '</span><div><h2 id="dialog-title">' + esc(document.original_name) + '</h2><p>' + esc(document.extension.toUpperCase().replace(".", "")) + ' · ' + number(document.size_bytes / 1024, 0) + ' KB · ' + esc(document.extraction_status) + (document.well_code ? ' · ' + esc(document.well_code) : "") + '</p></div></div><div class="document-extraction-note">' + icon("check") + '<span>' + esc(document.extraction_note) + '</span></div><div class="dialog-section"><div class="dialog-section-title"><h3>Extracted entities</h3><span>Rule-based extraction</span></div>' + (chips || '<div class="empty-state compact">No well, formation, depth, event, or severity tags were found.</div>') + '</div><div class="dialog-section"><div class="dialog-section-title"><h3>Extracted event candidates</h3><span>' + extractedEvents.length + ' · pending engineering review</span></div>' + (eventRows || '<div class="empty-state compact">No operational event candidate was extracted from this document.</div>') + '</div><div class="dialog-section"><div class="dialog-section-title"><h3>Extracted text preview</h3><span>' + number(extracted.length, 0) + ' characters</span></div><pre class="document-text-preview">' + esc(extracted.slice(0, 1800) || "No text was extracted from this file.") + (extracted.length > 1800 ? '…' : '') + '</pre></div><div class="dialog-actions"><button class="secondary-button" data-action="close-dialog">Close</button><button class="primary-button" data-action="return-documents">Document library</button></div></section></div>';
    bindDialog();
    const returnButton = dialogRoot.querySelector('[data-action="return-documents"]');
    if (returnButton) returnButton.addEventListener("click", showDocumentsDialog);
  }).catch(function (error) { showErrorDialog(error.message); });
}

function wellContextMarkup(well) {
  const rows = [];
  (well.reservoir_properties || []).forEach(function (item) {
    rows.push('<div><small>RESERVOIR · ' + esc(item.formation) + ' · ' + number(item.depth_start, 0) + '–' + number(item.depth_end, 0) + ' m</small><strong>' + esc(item.lithology) + (item.porosity_percent === null ? "" : ' · ' + number(item.porosity_percent, 1) + '% porosity') + (item.permeability_md === null ? "" : ' · ' + number(item.permeability_md, 0) + ' mD') + '</strong><span>' + esc(item.source_document || "Development context") + (item.source_page ? ' · page ' + number(item.source_page, 0) : "") + '</span></div>');
  });
  (well.mud_programs || []).forEach(function (item) {
    rows.push('<div><small>MUD PROGRAM · ' + esc(item.formation) + ' · ' + number(item.depth_start, 0) + '–' + number(item.depth_end, 0) + ' m</small><strong>' + esc(item.fluid_type) + ' · ' + number(item.mud_weight_min, 2) + '–' + number(item.mud_weight_max, 2) + ' sg</strong><span>' + esc(item.source_document || "Development context") + (item.source_page ? ' · page ' + number(item.source_page, 0) : "") + '</span></div>');
  });
  (well.casing_programs || []).forEach(function (item) {
    rows.push('<div><small>CASING PROGRAM</small><strong>' + esc(item.casing_size) + ' · ' + esc(item.casing_type) + ' · set at ' + number(item.setting_depth, 0) + ' m</strong><span>' + esc(item.source_document || "Development context") + (item.source_page ? ' · page ' + number(item.source_page, 0) : "") + '</span></div>');
  });
  (well.cementing_records || []).forEach(function (item) {
    rows.push('<div><small>CEMENTING · ' + esc(item.formation || "Formation not recorded") + '</small><strong>' + esc(item.summary) + '</strong><span>' + esc(item.mitigation || "No mitigation recorded") + ' · ' + esc(item.source_document || "Source unavailable") + (item.source_page ? ' · page ' + number(item.source_page, 0) : "") + '</span></div>');
  });
  return '<div class="dialog-section"><div class="dialog-section-title"><h3>Geology and drilling programs</h3><span>Synthetic development context</span></div>' + (rows.length ? '<div class="well-context-list">' + rows.join("") + '</div>' : '<div class="empty-state compact">No reservoir, mud, casing, or cementing context is recorded for this well.</div>') + '</div>';
}

function showWellDialog(wellCode, focusCloseButton) {
  api.well(wellCode).then(function (result) {
    const well = result.well;
    const distance = state.nearby.find(function (item) { return item.well_code === wellCode; });
    const events = well.events || [];
    const survey = well.surveys || [];
    dialogRoot.innerHTML = '<div class="dialog-backdrop" data-action="close-dialog"><section class="detail-dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">' +
      '<button class="dialog-close" data-action="close-dialog" aria-label="Close">' + icon("close") + "</button>" +
      '<div class="dialog-kicker">' + esc(well.field.toUpperCase()) + " / WELL RECORD</div><div class=\"dialog-title-row\"><div><h2 id=\"dialog-title\">" + esc(well.well_code) + '</h2><p>' + esc(well.name) + "</p></div>" + riskBadge(well.status === "drilling" ? "medium" : "low", well.status) + "</div>" +
      '<div class="well-detail-stats"><div><small>LOCATION</small><strong>' + number(well.latitude, 4) + ", " + number(well.longitude, 4) + '</strong></div><div><small>FORMATION</small><strong>' + esc(well.formation) + '</strong></div><div><small>TOTAL DEPTH</small><strong>' + number(well.total_depth, 0) + " m</strong></div><div><small>FROM ACTIVE</small><strong>" + (distance ? number(distance.distance_km, 1) + " km" : well.well_code === state.activeWellCode ? "Active well" : "Outside current radius") + "</strong></div></div>" +
      wellContextMarkup(well) +
      '<div class="dialog-section"><div class="dialog-section-title"><h3>Survey trajectory</h3><span>' + survey.length + " stations</span></div>" + '<div class="survey-track">' + survey.map(function (point) {
        return '<div><span class="survey-depth">' + number(point.measured_depth, 0) + " m</span><span class=\"survey-line\"></span><span class=\"survey-tvd\">TVD " + number(point.tvd, 0) + " · " + number(point.inclination, 1) + "°</span></div>";
      }).join("") + "</div></div>" +
      '<div class="dialog-section"><div class="dialog-section-title"><h3>Historical events</h3><span>' + events.length + " records</span></div>" +
      (events.length ? '<div class="dialog-event-list">' + events.map(function (event) {
        return '<button class="dialog-event" data-action="dialog-event" data-event="' + esc(event.id) + '"><span class="dialog-event-type">' + esc(eventLabel(event.event_type)) + "</span><span>" + number(event.depth_start, 0) + "–" + number(event.depth_end, 0) + " m · " + esc(event.formation) + "</span><span>" + esc(event.source_document) + " · p." + number(event.source_page, 0) + "</span>" + riskBadge(event.severity, event.severity) + "</button>";
      }).join("") + "</div>" : '<div class="empty-state compact">No historical events are recorded for this well.</div>') + "</div>" +
      '<div class="dialog-actions"><button class="secondary-button" data-action="close-dialog">Close</button><button class="primary-button" data-action="set-active" data-well="' + esc(wellCode) + '">' + (wellCode === state.activeWellCode ? "Active well" : "Use as active well") + "</button></div>" +
      "</section></div>";
    bindDialog(focusCloseButton);
  }).catch(function (error) {
    showErrorDialog(error.message, focusCloseButton);
  });
}

function showEventDialog(eventId) {
  api.events({}).then(function (result) {
    const event = result.events.find(function (item) { return item.id === eventId; });
    if (!event) throw new Error("Event " + eventId + " was not found.");
    const offset = state.nearby.find(function (item) { return item.well_code === event.well_code; });
    dialogRoot.innerHTML = '<div class="dialog-backdrop" data-action="close-dialog"><section class="detail-dialog event-dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">' +
      '<button class="dialog-close" data-action="close-dialog" aria-label="Close">' + icon("close") + "</button>" +
      '<div class="dialog-kicker">HISTORICAL EVENT / ' + esc(event.id) + '</div><div class="event-dialog-heading"><span class="large-event-mark ' + severityClass(event.severity) + '">' + icon("events") + "</span><div><h2 id=\"dialog-title\">" + esc(eventLabel(event.event_type)) + "</h2><p>" + esc(event.well_code) + " · " + esc(event.field) + "</p></div>" + riskBadge(event.severity, event.severity) + "</div>" +
      '<div class="event-depth-banner"><span><small>MEASURED DEPTH</small><strong>' + number(event.depth_start, 0) + "–" + number(event.depth_end, 0) + ' m</strong></span><span><small>FORMATION</small><strong>' + esc(event.formation) + '</strong></span><span><small>OFFSET</small><strong>' + (offset ? number(offset.distance_km, 1) + " km" : "—") + "</strong></span></div>" +
      '<div class="event-detail-copy"><div><small>EVENT DESCRIPTION</small><p>' + esc(event.description) + '</p></div><div><small>RECORDED CAUSE / CONTEXT</small><p>' + esc(event.cause) + '</p></div><div><small>RECORDED MITIGATION</small><p>' + esc(event.mitigation) + "</p></div></div>" +
      '<div class="source-card"><span class="source-card-icon">' + icon("events") + '</span><span><small>SOURCE DOCUMENT</small><strong>' + esc(event.source_document) + '</strong></span><span class="source-page">Page ' + number(event.source_page, 0) + "</span></div>" +
      '<div class="data-note">' + icon("check") + " Synthetic development record for demonstration; not an OIL operational document.</div>" +
      '<div class="dialog-actions"><button class="secondary-button" data-action="close-dialog">Close</button><button class="primary-button" data-action="set-active" data-well="' + esc(event.well_code) + '">View this well</button></div>' +
      "</section></div>";
    bindDialog();
  }).catch(function (error) {
    showErrorDialog(error.message);
  });
}

function showErrorDialog(message, focusCloseButton) {
  dialogRoot.innerHTML = '<div class="dialog-backdrop" data-action="close-dialog"><section class="detail-dialog error-dialog" role="alertdialog"><button class="dialog-close" data-action="close-dialog" aria-label="Close">' + icon("close") + '</button><div class="eyebrow">REQUEST ISSUE</div><h2>We could not open this record.</h2><p>' + esc(message) + '</p><div class="dialog-actions"><button class="primary-button" data-action="close-dialog">Close</button></div></section></div>';
  bindDialog(focusCloseButton);
}

function bindDialog(focusCloseButton) {
  const closeButton = dialogRoot.querySelector(".dialog-close");
  if (closeButton && focusCloseButton !== false) closeButton.focus();
  dialogRoot.querySelectorAll('[data-action="close-dialog"]').forEach(function (element) {
    element.addEventListener("click", function (event) {
      if (event.target === element || element.classList.contains("dialog-close") || element.classList.contains("secondary-button") || element.classList.contains("primary-button")) dialogRoot.innerHTML = "";
    });
  });
  dialogRoot.querySelectorAll('[data-action="dialog-event"]').forEach(function (element) {
    element.addEventListener("click", function () { showEventDialog(element.dataset.event); });
  });
  dialogRoot.querySelectorAll('[data-action="set-active"]').forEach(function (element) {
    element.addEventListener("click", function () {
      const code = element.dataset.well;
      dialogRoot.innerHTML = "";
      selectWell(code);
    });
  });
  const backdrop = dialogRoot.querySelector(".dialog-backdrop");
  if (backdrop) backdrop.addEventListener("click", function (event) { if (event.target === backdrop) dialogRoot.innerHTML = ""; });
}

async function handleNavigation() {
  const authenticated = api.authMode === "supabase"
    ? Boolean(await api.getSession())
    : sessionStorage.getItem("nwis.demo-auth") === "1";
  if (!authenticated) { renderLogin(); return; }
  const next = window.location.hash.replace("#", "") || "dashboard";
  state.route = ["dashboard", "wells", "events", "risk"].includes(next) ? next : "dashboard";
  render();
}

window.addEventListener("hashchange", function () { handleNavigation(); });
window.addEventListener("keydown", function (event) {
  if (event.key === "Escape") {
    dialogRoot.innerHTML = "";
    if (state.globalSearchOpen) { state.globalSearchOpen = false; updateGlobalSearchResults(); }
  }
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    const search = document.getElementById("global-search-input") || document.getElementById(state.route === "events" ? "event-search" : "well-search");
    if (search && search.id === "global-search-input") { state.globalSearchOpen = true; updateGlobalSearchResults(); }
    if (search) search.focus();
  }
});

document.addEventListener("click", function (event) {
  if (state.globalSearchOpen && !event.target.closest(".global-search-wrap")) {
    state.globalSearchOpen = false;
    updateGlobalSearchResults();
  }
});

if (api.authMode === "supabase") {
  api.getSession().then(function (session) {
    if (session) loadData();
    else renderLogin();
  }).catch(function () { renderLogin(); });
} else if (sessionStorage.getItem("nwis.demo-auth") === "1") loadData();
else renderLogin();

