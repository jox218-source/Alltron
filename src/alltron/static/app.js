const $ = (selector) => document.querySelector(selector);
const list = $("#timer-list");
const message = $("#message");
const announced = new Set();
const pageOpenedAt = Date.now() / 1000;
let lastTimers = [];

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
    for (const [label, key] of [["Home Assistant", "home_assistant"], ["Codex answers", "codex"], ["Microphone and voice", "voice"]]) {
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
  } catch (error) { message.textContent = error.message; }
}

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
setInterval(refreshTimers, 1000);
