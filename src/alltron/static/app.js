const $ = (selector) => document.querySelector(selector);
const list = $("#timer-list");
const message = $("#message");
const shoppingMessage = $("#shopping-message");
const announced = new Set();
const pageOpenedAt = Date.now() / 1000;
let lastTimers = [];
let voiceHealthReady = false;
let voiceSessionId = null;
let voiceSequence = 0;
let voicePhase = "idle";

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

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
        } catch (error) { message.textContent = error.message; }
      });
      row.append(cancel);
    }
    text.append(title, detail);
    row.prepend(text);
    list.append(row);
  }
}

async function refreshTimers() {
  try {
    const body = await api("/api/timers");
    renderTimers(body.timers);
    $("#service-status").textContent = "Local service connected";
  } catch (error) {
    $("#service-status").textContent = "Service unavailable — check the terminal";
    message.textContent = error.message;
  }
}

async function loadHealth() {
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
      small.textContent = "Setup available in a later build";
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
  } catch (error) { message.textContent = error.message; }
}

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
  if (!voiceSessionId) return;
  const requestId = voiceSessionId;
  try {
    const {events} = await api(`/api/voice/events?after=${voiceSequence}`);
    for (const event of events) {
      if (Number.isInteger(event.sequence)) voiceSequence = Math.max(voiceSequence, event.sequence);
      if (event.request_id === requestId) renderVoiceEvent(event);
    }
  } catch (error) {
    $("#voice-message").textContent = error.message;
  }
  if (voiceSessionId === requestId) setTimeout(pollVoiceEvents, 700);
}

async function startVoice() {
  if (!voiceHealthReady || voicePhase !== "idle") return;
  $("#voice-message").textContent = "";
  $("#voice-events").replaceChildren();
  try {
    const {request_id: requestId} = await jsonPost("/api/voice/start", {});
    voiceSessionId = requestId;
    voicePhase = "capturing";
    updateVoiceControls();
    $("#voice-message").textContent = "Push-to-talk is active on the local service.";
    pollVoiceEvents();
  } catch (error) { $("#voice-message").textContent = error.message; }
}

async function stopVoice() {
  if (!voiceSessionId || voicePhase !== "capturing") return;
  voicePhase = "processing";
  updateVoiceControls();
  try {
    await jsonPost("/api/voice/stop", {request_id: voiceSessionId});
    $("#voice-message").textContent = "Capture stopped. The local service is processing the request.";
  } catch (error) {
    $("#voice-message").textContent = error.message;
    voicePhase = "capturing";
    updateVoiceControls();
  }
}

async function cancelVoice() {
  if (!voiceSessionId) return;
  try {
    await jsonPost("/api/voice/cancel", {request_id: voiceSessionId});
    $("#voice-message").textContent = "Voice request cancelled.";
    finishVoiceSession();
  } catch (error) { $("#voice-message").textContent = error.message; }
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
          } catch (error) { shoppingMessage.textContent = error.message; }
        });
        row.append(button);
      }
      list.append(row);
    }
  } catch (error) { shoppingMessage.textContent = error.message; }
}

$("#command-form").addEventListener("submit", async (event) => {
  event.preventDefault();
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
  const input = $("#shopping-text");
  try {
    await jsonPost("/api/lists/shopping", {text: input.value});
    input.value = "";
    shoppingMessage.textContent = "Item added.";
    await refreshShopping();
  } catch (error) { shoppingMessage.textContent = error.message; }
});

$("#timer-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const minutes = Number($("#timer-minutes").value);
  if (!Number.isInteger(minutes) || minutes < 1 || minutes > 1440) {
    message.textContent = "Choose 1 to 1440 whole minutes.";
    return;
  }
  try {
    await api("/api/timers", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({seconds: minutes * 60, label: $("#timer-label").value})});
    message.textContent = "Timer started.";
    await refreshTimers();
  } catch (error) { message.textContent = error.message; }
});

loadHealth();
refreshTimers();
refreshShopping();
setInterval(refreshTimers, 1000);
setInterval(loadHealth, 5000);
