const $ = (selector) => document.querySelector(selector);
const list = $("#timer-list");
const message = $("#message");
const shoppingMessage = $("#shopping-message");
const announced = new Set();
const pageOpenedAt = Date.now() / 1000;
const accessMessage = $("#access-message");
let lastTimers = [];
let authenticated = false;
let authEpoch = 0;
let pollersStarted = false;
let csrfToken = null;
let haAuthorized = false;
let voiceHealthReady = false;
let voiceSessionId = null;
let voiceSequence = 0;
let voicePhase = "idle";

async function api(path, options = {}) {
  const requestEpoch = authEpoch;
  const headers = new Headers(options.headers || {});
  if (options.method?.toUpperCase() === "POST" && path !== "/api/login" && csrfToken) {
    headers.set("X-Alltron-CSRF", csrfToken);
  }
  const response = await fetch(path, {...options, headers, credentials: "same-origin"});
  if (response.status === 401 && path !== "/api/session" && path !== "/api/login") {
    lockWorkspace("Your session ended. Enter the owner password to continue.");
    throw new Error("Your session ended.");
  }
  if (requestEpoch !== authEpoch) throw new Error("The workspace is locked.");
  let body = {};
  try { body = await response.json(); } catch { /* Keep the message generic if the server did not return JSON. */ }
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

function clearPrivateDisplay() {
  list.replaceChildren();
  lastTimers = [];
  announced.clear();
  message.textContent = "";
  $("#shopping-list").replaceChildren();
  shoppingMessage.textContent = "";
  $("#command-message").replaceChildren();
  $("#command-result").replaceChildren();
  $("#command-text").value = "";
  $("#shopping-text").value = "";
  $("#timer-label").value = "";
  $("#timer-minutes").value = "";
  $("#voice-events").replaceChildren();
  $("#voice-message").textContent = "";
  $("#connections").replaceChildren();
  $("#ha-setup-status").textContent = "";
  $("#ha-setup-message").textContent = "";
  $("#ha-device-list").replaceChildren();
  $("#ha-selection-form").hidden = true;
  $("#ha-load-devices").hidden = true;
  $("#ha-authorize").hidden = true;
  $("#ha-revoke").hidden = true;
  haAuthorized = false;
  $("#voice-status").replaceChildren();
  $("#voice-verification").textContent = "";
  voiceSessionId = null;
  voiceSequence = 0;
  voicePhase = "idle";
  voiceHealthReady = false;
  commandRetry = null;
  updateVoiceControls();
}

function lockWorkspace(prompt = "Enter the owner password to open this local workspace.") {
  if (authenticated) authEpoch += 1;
  authenticated = false;
  csrfToken = null;
  $("#private-app").hidden = true;
  $("#owner-access").classList.remove("is-authenticated");
  $("#login-form").hidden = false;
  $("#logout-button").hidden = true;
  $("#login-button").disabled = false;
  accessMessage.textContent = prompt;
  clearPrivateDisplay();
}

function unlockWorkspace() {
  clearPrivateDisplay();
  authenticated = true;
  authEpoch += 1;
  $("#private-app").hidden = false;
  $("#owner-access").classList.add("is-authenticated");
  $("#login-form").hidden = true;
  $("#logout-button").hidden = false;
  accessMessage.textContent = "Workspace unlocked.";
  startAuthorizedApp();
}

async function checkSession() {
  try {
    const session = await api("/api/session");
    if (session.authenticated === true) {
      csrfToken = typeof session.csrf === "string" && session.csrf.length ? session.csrf : null;
      unlockWorkspace();
    }
    else lockWorkspace();
  } catch {
    lockWorkspace("Local sign-in is unavailable. Check the Alltron service and try again.");
  }
}

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#owner-password");
  const password = input.value;
  if (password.length > 256) {
    input.value = "";
    accessMessage.textContent = "Owner passwords must be 256 characters or fewer.";
    return;
  }
  $("#login-button").disabled = true;
  accessMessage.textContent = "Checking password…";
  try {
    const result = await api("/api/login", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({password}),
    });
    if (result.authenticated !== true) throw new Error("Password was not accepted.");
    const session = await api("/api/session");
    if (session.authenticated !== true) throw new Error("The owner session could not be confirmed.");
    csrfToken = typeof session.csrf === "string" && session.csrf.length ? session.csrf : null;
    unlockWorkspace();
  } catch (error) {
    accessMessage.textContent = error.message;
  } finally {
    input.value = "";
    $("#login-button").disabled = false;
  }
});

$("#logout-button").addEventListener("click", async () => {
  $("#logout-button").disabled = true;
  try {
    const result = await api("/api/logout", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({}),
    });
    if (result.authenticated !== false) throw new Error("The service did not confirm logout.");
    lockWorkspace("You are logged out. Enter the owner password to continue.");
  } catch (error) {
    accessMessage.textContent = error.message;
  } finally {
    $("#logout-button").disabled = false;
  }
});

function chime() {
  try {
    const context = new AudioContext();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.type = "sine";
    oscillator.frequency.value = 740;
    oscillator.connect(gain);
    gain.connect(context.destination);
    gain.gain.setValueAtTime(0.0001, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.15, context.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.5);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.5);
    oscillator.onended = () => context.close();
  } catch { /* Audio can be unavailable or blocked by browser settings. */ }
}

function renderTimers(timers) {
  lastTimers = timers;
  list.replaceChildren();
  if (timers.length === 0) {
    const empty = document.createElement("li");
    empty.textContent = "No timers yet.";
    list.append(empty);
    return;
  }
  const now = Date.now() / 1000;
  for (const timer of timers) {
    const row = document.createElement("li");
    const text = document.createElement("div");
    const title = document.createElement("span");
    title.className = "timer-title";
    title.textContent = timer.label;
    const detail = document.createElement("span");
    detail.className = "timer-detail";
    if (timer.state === "done") {
      detail.textContent = "Finished";
      if (!announced.has(timer.id)) {
        announced.add(timer.id);
        if (timer.due_at >= pageOpenedAt) {
          message.textContent = `${timer.label} finished.`;
          chime();
        }
      }
    } else {
      const seconds = Math.max(0, Math.ceil(timer.due_at - now));
      detail.textContent = `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s remaining`;
      const cancel = document.createElement("button");
      cancel.className = "secondary";
      cancel.textContent = "Cancel";
      cancel.addEventListener("click", async () => {
        try {
          await api("/api/timers/cancel", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id: timer.id})});
          await refreshTimers();
        } catch (error) { if (authenticated) message.textContent = error.message; }
      });
      row.append(cancel);
    }
    text.append(title, detail);
    row.prepend(text);
    list.append(row);
  }
}

async function refreshTimers() {
  if (!authenticated) return;
  try {
    const body = await api("/api/timers");
    renderTimers(body.timers);
    $("#service-status").textContent = "Local service connected";
  } catch (error) {
    if (!authenticated) return;
    $("#service-status").textContent = "Service unavailable — check the terminal";
    message.textContent = error.message;
  }
}

async function loadHealth() {
  if (!authenticated) return;
  try {
    const health = await api("/api/health");
    const connections = $("#connections");
    connections.replaceChildren();
    for (const [label, key] of [["Home Assistant", "home_assistant"], ["Codex answers", "codex"]]) {
      const row = document.createElement("div");
      row.className = "connection";
      const name = document.createElement("div");
      const strong = document.createElement("strong");
      strong.textContent = label;
      const small = document.createElement("small");
      small.textContent = key === "home_assistant"
        ? "Local owner setup is available below; connection status comes from the service."
        : "Codex answers remain disabled pending isolation acceptance.";
      name.append(strong, small);
      const state = document.createElement("span");
      state.textContent = health[key].replaceAll("-", " ");
      row.append(name, state);
      connections.append(row);
    }
    const voice = $("#voice-status");
    voice.replaceChildren();
    for (const [label, key] of [["Wake word", "wake"], ["Capture", "capture"], ["Speech recognition", "stt"], ["Speech output", "tts"]]) {
      const row = document.createElement("div");
      row.className = "connection";
      const name = document.createElement("strong");
      name.textContent = label;
      const state = document.createElement("span");
      state.textContent = health.voice?.[key]?.status || "unknown";
      row.append(name, state);
      voice.append(row);
    }
    voiceHealthReady = health.voice?.capture?.status === "ready" && health.voice?.stt?.status === "ready";
    updateVoiceControls();
    const needsTest = health.voice?.capture?.verified === false || health.voice?.stt?.verified === false;
    $("#voice-verification").textContent = needsTest
      ? "Capture and speech recognition report ready, but verified:false means spoken setup still needs a test."
      : "Service readiness does not by itself confirm a successful spoken setup test.";
  } catch (error) { if (authenticated) message.textContent = error.message; }
}

function homeAssistantState(setup) {
  const value = setup?.home_assistant;
  return typeof value === "string" ? value : (typeof value?.status === "string" ? value.status : "unknown");
}

async function loadSetupStatus() {
  if (!authenticated) return;
  try {
    const setup = await api("/api/setup");
    const state = homeAssistantState(setup);
    haAuthorized = state === "authorized" || state === "selected";
    const labels = {
      "needs-authorization": "Home Assistant authorization is needed.",
      authorized: "Home Assistant is authorized. Choose which devices Alltron may control.",
      selected: "Home Assistant is authorized and device selection is saved.",
    };
    $("#ha-setup-status").textContent = labels[state] || "Home Assistant setup status is unavailable.";
    $("#ha-authorize").hidden = haAuthorized;
    $("#ha-load-devices").hidden = !haAuthorized;
    $("#ha-revoke").hidden = !haAuthorized;
  } catch (error) {
    if (authenticated) $("#ha-setup-message").textContent = error.message;
  }
}

async function beginHomeAssistantAuthorization() {
  if (!authenticated) return;
  const button = $("#ha-authorize");
  button.disabled = true;
  $("#ha-setup-message").textContent = "Preparing verified Home Assistant authorization…";
  try {
    const response = await jsonPost("/api/setup/ha/start", {});
    const target = new URL(response.url);
    if (target.protocol !== "https:" || target.hostname !== "127.0.0.1" || target.username || target.password) {
      throw new Error("The local authorization address did not pass its HTTPS identity check.");
    }
    $("#ha-setup-message").textContent = "Continue on the verified Home Assistant page. Alltron will return here afterward.";
    window.location.assign(target.href);
  } catch (error) {
    if (authenticated) $("#ha-setup-message").textContent = error.message;
    button.disabled = false;
  }
}

async function loadHomeAssistantDevices() {
  if (!authenticated || !haAuthorized) return;
  const button = $("#ha-load-devices");
  button.disabled = true;
  $("#ha-setup-message").textContent = "Loading available Home Assistant devices…";
  try {
    const response = await api("/api/setup/ha/devices");
    const devices = Array.isArray(response.devices) ? response.devices : [];
    const list = $("#ha-device-list");
    list.replaceChildren();
    if (devices.length === 0) {
      $("#ha-setup-message").textContent = "No eligible devices were returned. Check Home Assistant availability and try again.";
      $("#ha-selection-form").hidden = true;
      return;
    }
    for (const [index, device] of devices.entries()) {
      if (!device || typeof device.entity_id !== "string" || typeof device.name !== "string") continue;
      const row = document.createElement("div");
      row.className = "ha-device";
      const check = document.createElement("input");
      check.type = "checkbox";
      check.id = `ha-device-${index}`;
      check.dataset.entityId = device.entity_id;
      const identity = document.createElement("div");
      const name = document.createElement("label");
      name.htmlFor = check.id;
      name.textContent = device.name;
      const entity = document.createElement("small");
      entity.textContent = device.entity_id;
      identity.append(name, entity);
      const aliasLabel = document.createElement("label");
      aliasLabel.htmlFor = `ha-alias-${index}`;
      aliasLabel.textContent = "Spoken name";
      const alias = document.createElement("input");
      alias.id = `ha-alias-${index}`;
      alias.type = "text";
      alias.maxLength = 80;
      alias.autocomplete = "off";
      alias.placeholder = "For example, desk lamp";
      alias.dataset.deviceIndex = String(index);
      row.append(check, identity, aliasLabel, alias);
      list.append(row);
    }
    $("#ha-selection-form").hidden = list.children.length === 0;
    $("#ha-setup-message").textContent = list.children.length
      ? "Select only the devices Alltron may control and assign a unique spoken name to each."
      : "No eligible devices were returned. Check Home Assistant availability and try again.";
  } catch (error) {
    if (authenticated) $("#ha-setup-message").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function saveHomeAssistantSelection(event) {
  event.preventDefault();
  if (!authenticated || !haAuthorized) return;
  const aliases = Object.create(null);
  const seen = new Set();
  for (const check of $("#ha-device-list").querySelectorAll('input[type="checkbox"]:checked')) {
    const aliasInput = $("#ha-device-list").querySelector(`input[data-device-index="${check.id.slice("ha-device-".length)}"]`);
    const alias = aliasInput?.value.trim();
    const key = alias?.toLocaleLowerCase();
    if (!alias || alias.length > 80 || seen.has(key)) {
      $("#ha-setup-message").textContent = "Give each selected device a unique spoken name of 1 to 80 characters.";
      aliasInput?.focus();
      return;
    }
    seen.add(key);
    aliases[alias] = check.dataset.entityId;
  }
  if (Object.keys(aliases).length === 0) {
    $("#ha-setup-message").textContent = "Choose at least one device before saving.";
    return;
  }
  const submit = $("#ha-selection-form").querySelector('button[type="submit"]');
  submit.disabled = true;
  $("#ha-setup-message").textContent = "Saving selected devices…";
  try {
    await jsonPost("/api/setup/ha/select", {aliases});
    $("#ha-setup-message").textContent = "Selected devices saved.";
    await loadSetupStatus();
  } catch (error) {
    if (authenticated) $("#ha-setup-message").textContent = error.message;
  } finally {
    submit.disabled = false;
  }
}

async function revokeHomeAssistantAccess() {
  if (!authenticated || !haAuthorized) return;
  const button = $("#ha-revoke");
  button.disabled = true;
  $("#ha-setup-message").textContent = "Revoking Home Assistant access…";
  try {
    await jsonPost("/api/setup/ha/revoke", {});
    $("#ha-device-list").replaceChildren();
    $("#ha-selection-form").hidden = true;
    $("#ha-setup-message").textContent = "Home Assistant access was revoked.";
    await loadSetupStatus();
  } catch (error) {
    if (authenticated) $("#ha-setup-message").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

$("#ha-authorize").addEventListener("click", beginHomeAssistantAuthorization);
$("#ha-load-devices").addEventListener("click", loadHomeAssistantDevices);
$("#ha-selection-form").addEventListener("submit", saveHomeAssistantSelection);
$("#ha-revoke").addEventListener("click", revokeHomeAssistantAccess);

function updateVoiceControls() {
  const toggle = $("#voice-toggle");
  const cancel = $("#voice-cancel");
  if (voicePhase === "idle") {
    toggle.textContent = "Start push to talk";
    toggle.disabled = !voiceHealthReady;
    cancel.disabled = true;
  } else if (voicePhase === "capturing") {
    toggle.textContent = "Stop and process";
    toggle.disabled = false;
    cancel.disabled = false;
  } else {
    toggle.textContent = "Processing voice…";
    toggle.disabled = true;
    cancel.disabled = false;
  }
}

function finishVoiceSession() {
  voicePhase = "idle";
  voiceSessionId = null;
  updateVoiceControls();
}

function renderVoiceEvent(event) {
  const line = document.createElement("li");
  const parts = [event.type, event.status, event.command_kind, event.text].filter((part) => typeof part === "string" && part.length);
  line.textContent = parts.join(" · ") || "Voice event";
  const events = $("#voice-events");
  events.append(line);
  while (events.children.length > 50) events.firstElementChild.remove();
  const end = `${event.type || ""} ${event.status || ""}`.toLowerCase();
  if (/cancel|complete|finish|failed|error|stopped|done/.test(end)) finishVoiceSession();
}

async function pollVoiceEvents() {
  if (!authenticated || !voiceSessionId) return;
  const requestId = voiceSessionId;
  try {
    const {events} = await api(`/api/voice/events?after=${voiceSequence}`);
    for (const event of events) {
      if (Number.isInteger(event.sequence)) voiceSequence = Math.max(voiceSequence, event.sequence);
      if (event.request_id === requestId) renderVoiceEvent(event);
    }
  } catch (error) {
    if (authenticated) $("#voice-message").textContent = error.message;
  }
  if (voiceSessionId === requestId) setTimeout(pollVoiceEvents, 700);
}

async function startVoice() {
  if (!authenticated || !voiceHealthReady || voicePhase !== "idle") return;
  $("#voice-message").textContent = "";
  $("#voice-events").replaceChildren();
  try {
    const {request_id: requestId} = await jsonPost("/api/voice/start", {});
    voiceSessionId = requestId;
    voicePhase = "capturing";
    updateVoiceControls();
    $("#voice-message").textContent = "Push-to-talk is active on the local service.";
    pollVoiceEvents();
  } catch (error) { if (authenticated) $("#voice-message").textContent = error.message; }
}

async function stopVoice() {
  if (!authenticated || !voiceSessionId || voicePhase !== "capturing") return;
  voicePhase = "processing";
  updateVoiceControls();
  try {
    await jsonPost("/api/voice/stop", {request_id: voiceSessionId});
    $("#voice-message").textContent = "Capture stopped. The local service is processing the request.";
  } catch (error) {
    if (authenticated) $("#voice-message").textContent = error.message;
    voicePhase = "capturing";
    updateVoiceControls();
  }
}

async function cancelVoice() {
  if (!authenticated || !voiceSessionId) return;
  try {
    await jsonPost("/api/voice/cancel", {request_id: voiceSessionId});
    $("#voice-message").textContent = "Voice request cancelled.";
    finishVoiceSession();
  } catch (error) { if (authenticated) $("#voice-message").textContent = error.message; }
}

function jsonPost(path, data) {
  return api(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
}

function newRequestId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    return Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("");
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (digit) => {
    const random = Math.floor(Math.random() * 16);
    return (digit === "x" ? random : (random & 3) | 8).toString(16);
  });
}

let commandRetry = null;

async function sendCommand(request) {
  if (!authenticated) return;
  const status = $("#command-message");
  const result = $("#command-result");
  const retry = document.createElement("button");
  status.replaceChildren();
  result.replaceChildren();
  try {
    const answer = await jsonPost("/api/commands", request);
    commandRetry = null;
    for (const key of ["kind", "status", "text"]) {
      const term = document.createElement("dt");
      term.textContent = key;
      const value = document.createElement("dd");
      value.textContent = answer[key] ?? "";
      result.append(term, value);
    }
  } catch (error) {
    if (!authenticated) return;
    commandRetry = request;
    status.append(document.createTextNode(error.message + " "));
    retry.type = "button";
    retry.className = "secondary";
    retry.textContent = "Retry command";
    retry.addEventListener("click", () => sendCommand(commandRetry));
    status.append(retry);
  }
}

async function refreshShopping() {
  if (!authenticated) return;
  try {
    const {items} = await api("/api/lists/shopping");
    const list = $("#shopping-list");
    list.replaceChildren();
    if (!items.length) {
      const empty = document.createElement("li");
      empty.textContent = "Your list is empty.";
      list.append(empty);
    }
    for (const item of items) {
      const row = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = item.text;
      if (item.done) label.className = "done";
      row.append(label);
      if (!item.done) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "secondary";
        button.textContent = "Complete";
        button.setAttribute("aria-label", `Mark ${item.text} complete`);
        button.addEventListener("click", async () => {
          try {
            await jsonPost("/api/lists/shopping/complete", {id: item.id});
            await refreshShopping();
          } catch (error) { if (authenticated) shoppingMessage.textContent = error.message; }
        });
        row.append(button);
      }
      list.append(row);
    }
  } catch (error) { if (authenticated) shoppingMessage.textContent = error.message; }
}

$("#command-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!authenticated) return;
  const status = $("#command-message");
  const text = $("#command-text").value;
  if (text.length > 500) {
    status.textContent = "Commands must be 500 characters or fewer.";
    return;
  }
  commandRetry = null;
  await sendCommand({text, request_id: newRequestId()});
});

$("#voice-toggle").addEventListener("click", () => {
  if (voicePhase === "idle") startVoice();
  else if (voicePhase === "capturing") stopVoice();
});
$("#voice-cancel").addEventListener("click", cancelVoice);

$("#shopping-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!authenticated) return;
  const input = $("#shopping-text");
  try {
    await jsonPost("/api/lists/shopping", {text: input.value});
    input.value = "";
    shoppingMessage.textContent = "Item added.";
    await refreshShopping();
  } catch (error) { if (authenticated) shoppingMessage.textContent = error.message; }
});

$("#timer-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!authenticated) return;
  const minutes = Number($("#timer-minutes").value);
  if (!Number.isInteger(minutes) || minutes < 1 || minutes > 1440) {
    message.textContent = "Choose 1 to 1440 whole minutes.";
    return;
  }
  try {
    await api("/api/timers", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({seconds: minutes * 60, label: $("#timer-label").value})});
    message.textContent = "Timer started.";
    await refreshTimers();
  } catch (error) { if (authenticated) message.textContent = error.message; }
});

function startAuthorizedApp() {
  if (!authenticated) return;
  loadHealth();
  loadSetupStatus();
  refreshTimers();
  refreshShopping();
  if (pollersStarted) return;
  pollersStarted = true;
  setInterval(refreshTimers, 1000);
  setInterval(loadHealth, 5000);
}

checkSession();
