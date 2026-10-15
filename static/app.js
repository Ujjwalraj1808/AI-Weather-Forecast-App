"use strict";

const $ = (id) => document.getElementById(id);

const form = $("search");
const input = $("city");
const listbox = $("suggestions");
const statusEl = $("status");
const dashboard = $("dashboard");
const LAST_KEY = "weather:last";

let suggestions = [];
let activeIndex = -1;
let selected = null; // { q: "id:123", label: "Delhi, India" } when a suggestion was picked
let searchTimer = null;
let searchAbort = null;

// ---------- Helpers ----------

class ApiError extends Error {
  constructor(status, body) {
    super(typeof body.detail === "string" ? body.detail : "Request failed.");
    this.status = status;
    this.body = body;
  }
}

async function api(path, params, signal) {
  let res;
  try {
    res = await fetch(`${path}?${new URLSearchParams(params)}`, { signal });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError(0, { detail: "Can't reach the server. Check your connection and try again." });
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, body);
  return body;
}

function placeLabel(loc) {
  const parts = [loc.name];
  if (loc.region && loc.region !== loc.name) parts.push(loc.region);
  parts.push(loc.country);
  return parts.join(", ");
}

// WeatherAPI local times are "YYYY-MM-DD HH:MM" in the place's own time zone.
// Format them as UTC so the browser's time zone never shifts them.
function parseLocal(text) {
  const [d, t] = text.split(" ");
  const [y, m, day] = d.split("-").map(Number);
  const [h, min] = t.split(":").map(Number);
  return new Date(Date.UTC(y, m - 1, day, h, min));
}
const fmt = (opts) => new Intl.DateTimeFormat(undefined, { timeZone: "UTC", ...opts });
const fmtDateTime = fmt({ weekday: "long", day: "numeric", month: "long", hour: "numeric", minute: "2-digit" });
const fmtHour = fmt({ hour: "numeric" });
const fmtDay = fmt({ weekday: "short" });
const fmtDate = fmt({ weekday: "short", day: "numeric", month: "short" });

function setStatus(text, kind = "info") {
  statusEl.hidden = !text;
  statusEl.textContent = text || "";
  statusEl.classList.toggle("error", kind === "error");
}

function setBusy(busy) {
  form.querySelector("button").disabled = busy;
  $("locate").disabled = busy;
  dashboard.setAttribute("aria-busy", String(busy));
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function icon(src, size) {
  const img = el("img");
  img.src = src;
  img.alt = "";
  img.width = size;
  img.height = size;
  img.loading = "lazy";
  img.decoding = "async";
  img.addEventListener("error", () => img.classList.add("failed"), { once: true });
  return img;
}

// ---------- Sky ----------

let photoToken = 0;

function applyScene(scene, photoUrl) {
  document.body.dataset.scene = scene;
  const photo = document.querySelector(".sky-photo");
  const token = ++photoToken;
  photo.classList.remove("on");
  if (!photoUrl) return;
  const img = new Image();
  img.onload = () => {
    if (token !== photoToken) return;
    photo.style.backgroundImage = `url("${photoUrl}")`;
    photo.classList.add("on");
  };
  // On error the gradient scene simply stays in place.
  img.src = photoUrl;
}

// ---------- Rendering ----------

function renderCurrent(w) {
  $("place").textContent = w.location;
  $("place-sub").textContent = [w.region !== w.location ? w.region : null, w.country].filter(Boolean).join(", ");
  $("localtime").textContent = `${fmtDateTime.format(parseLocal(w.localtime))} local time`;
  $("temp").textContent = Math.round(w.temp_c);
  $("icon").classList.remove("failed");
  $("icon").src = w.icon;
  $("condition").textContent = w.condition;
  $("feels").textContent = `Feels like ${Math.round(w.feelslike_c)}°C`;
  $("humidity").textContent = `${w.humidity}%`;
  $("wind").textContent = `${w.wind_kph} km/h`;
  $("rain-today").textContent = `${w.chance_of_rain_today}%`;
  $("sunrise").textContent = w.sunrise;
  $("sunset").textContent = w.sunset;

  let summary = w.advice;
  if (w.chance_of_rain_today >= 50) {
    summary += ` Rain is likely today (${w.chance_of_rain_today}% chance).`;
  }
  $("summary").textContent = summary;

  $("map").href = `https://www.google.com/maps/search/?api=1&query=${w.lat},${w.lon}`;
  applyScene(w.scene, w.scene_image);
  document.title = `${Math.round(w.temp_c)}°C ${w.location} · Weather Forecast`;
}

function renderHourly(hours) {
  const list = $("hours");
  list.replaceChildren();
  hours.forEach((h, i) => {
    const li = el("li");
    li.append(
      el("span", "h-time", i === 0 ? "Now" : fmtHour.format(parseLocal(h.time))),
      icon(h.icon, 40),
      el("span", "h-temp", `${Math.round(h.temp_c)}°`),
      el("span", "h-rain", h.chance_of_rain > 0 ? `${h.chance_of_rain}%` : ""),
    );
    li.setAttribute("aria-label", `${i === 0 ? "Now" : fmtHour.format(parseLocal(h.time))}: ${Math.round(h.temp_c)}°C, ${h.condition}, ${h.chance_of_rain}% chance of rain`);
    list.append(li);
  });
}

function renderDays(days) {
  $("days-title").textContent = `${days.length}-day forecast`;
  const lo = Math.min(...days.map((d) => d.mintemp_c));
  const hi = Math.max(...days.map((d) => d.maxtemp_c));
  const span = Math.max(hi - lo, 1);
  const list = $("days");
  list.replaceChildren();
  days.forEach((d, i) => {
    const date = parseLocal(`${d.date} 00:00`);
    const li = el("li");
    li.setAttribute("aria-label", `${i === 0 ? "Today" : fmtDate.format(date)}: ${d.condition}, high ${Math.round(d.maxtemp_c)}°C, low ${Math.round(d.mintemp_c)}°C, ${d.chance_of_rain}% chance of rain`);
    const bar = el("div", "range");
    const fill = el("span");
    fill.style.left = `${((d.mintemp_c - lo) / span) * 100}%`;
    fill.style.right = `${((hi - d.maxtemp_c) / span) * 100}%`;
    bar.append(fill);
    const name = el("span", "d-name", i === 0 ? "Today" : fmtDay.format(date));
    name.title = fmtDate.format(date);
    li.append(
      name,
      icon(d.icon, 36),
      el("span", "d-rain", d.chance_of_rain > 0 ? `${d.chance_of_rain}%` : ""),
      el("span", "d-min", `${Math.round(d.mintemp_c)}°`),
      bar,
      el("span", "d-max", `${Math.round(d.maxtemp_c)}°`),
    );
    list.append(li);
  });
}

function renderPrediction(p) {
  const percent = Math.round(p.probability * 100);
  $("prediction").textContent = p.rain_expected
    ? `Rain likely tomorrow (${percent}%)`
    : `Rain unlikely tomorrow (${percent}%)`;
}

const pct = (x) => `${Math.round(x * 100)}%`;

async function loadModelInfo() {
  try {
    const info = await api("/model", {});
    const m = info.metrics;
    $("ml-note").textContent =
      `Random forest trained on ${info.train_samples.toLocaleString()} hourly observations ` +
      `from ${info.cities.length} cities (Open-Meteo, ${info.data_from} to ${info.data_to}). ` +
      `On the most recent ${info.test_samples.toLocaleString()} held-out hours it scored ` +
      `${pct(m.accuracy)} accuracy, ROC AUC ${m.roc_auc.toFixed(2)}, and caught ${pct(m.recall)} of rainy days ` +
      `(${pct(m.precision)} of its rain calls were right). ` +
      `It is a separate estimate; use the chance of rain from WeatherAPI for planning.`;
  } catch {
    /* keep the static note */
  }
}

// ---------- Loading a place ----------

async function load(q, label) {
  closeSuggestions();
  $("choices").hidden = true;
  setBusy(true);
  setStatus(`Loading weather for ${label}…`);
  try {
    const data = await api("/dashboard", { city: q, days: 10 });
    const weather = data.current;
    renderCurrent(weather);
    renderHourly(data.hourly);
    renderDays(data.days);
    renderPrediction(data.prediction);
    $("empty").hidden = true;
    dashboard.hidden = false;
    setStatus("");
    const shown = placeLabel({ name: weather.location, region: weather.region, country: weather.country });
    input.value = shown;
    selected = { q, label: shown };
    try { localStorage.setItem(LAST_KEY, JSON.stringify(selected)); } catch { /* storage unavailable */ }
  } catch (err) {
    showError(err);
  } finally {
    setBusy(false);
  }
}

function showError(err) {
  if (err.status === 409 && err.body.candidates) {
    showChoices(err.body.detail, err.body.candidates);
    setStatus("");
    return;
  }
  const hints = {
    404: `${err.message} Check the spelling, or add the country, e.g. "Delhi, India".`,
  };
  setStatus(hints[err.status] || err.message, "error");
}

function showChoices(title, candidates) {
  $("choices-title").textContent = `${title}. Choose one:`;
  const list = $("choice-list");
  list.replaceChildren();
  for (const c of candidates) {
    const li = el("li");
    const btn = el("button", "btn", placeLabel(c));
    btn.type = "button";
    btn.addEventListener("click", () => load(`id:${c.id}`, placeLabel(c)));
    li.append(btn);
    list.append(li);
  }
  $("choices").hidden = false;
  list.querySelector("button")?.focus();
}

async function submitQuery() {
  const text = input.value.trim();
  if (!text) {
    setStatus("Type a city name to search.", "error");
    input.focus();
    return;
  }
  if (selected && selected.label === text) {
    load(selected.q, selected.label);
    return;
  }
  // Free text: let the server pick one exact place (or ask which one).
  setBusy(true);
  setStatus(`Looking up ${text}…`);
  try {
    const loc = await api("/resolve", { q: text });
    await load(`id:${loc.id}`, placeLabel(loc));
  } catch (err) {
    setBusy(false);
    showError(err);
  }
}

// ---------- Autocomplete ----------

function closeSuggestions() {
  listbox.hidden = true;
  listbox.replaceChildren();
  input.setAttribute("aria-expanded", "false");
  input.removeAttribute("aria-activedescendant");
  suggestions = [];
  activeIndex = -1;
}

function setActive(index) {
  activeIndex = index;
  [...listbox.children].forEach((li, i) => li.setAttribute("aria-selected", String(i === index)));
  if (index >= 0) {
    input.setAttribute("aria-activedescendant", `opt-${index}`);
    listbox.children[index].scrollIntoView({ block: "nearest" });
  } else {
    input.removeAttribute("aria-activedescendant");
  }
}

function pickSuggestion(index) {
  const loc = suggestions[index];
  const label = placeLabel(loc);
  selected = { q: `id:${loc.id}`, label };
  input.value = label;
  load(selected.q, label);
}

function showSuggestions(items) {
  suggestions = items;
  listbox.replaceChildren();
  if (!items.length) {
    closeSuggestions();
    return;
  }
  items.forEach((loc, i) => {
    const li = el("li");
    li.id = `opt-${i}`;
    li.setAttribute("role", "option");
    li.setAttribute("aria-selected", "false");
    li.append(el("span", "name", loc.name), el("span", "where", [loc.region, loc.country].filter(Boolean).join(", ")));
    li.addEventListener("mousedown", (e) => e.preventDefault()); // keep focus in the input
    li.addEventListener("click", () => pickSuggestion(i));
    listbox.append(li);
  });
  listbox.hidden = false;
  input.setAttribute("aria-expanded", "true");
  activeIndex = -1;
}

input.addEventListener("input", () => {
  selected = null;
  clearTimeout(searchTimer);
  const text = input.value.trim();
  if (text.length < 2 || /^-?\d/.test(text)) {
    closeSuggestions();
    return;
  }
  searchTimer = setTimeout(async () => {
    searchAbort?.abort();
    searchAbort = new AbortController();
    try {
      // Search on the name part; the full text (with any ", country") goes to /resolve on submit.
      const items = await api("/search", { q: text.split(",")[0].trim() || text }, searchAbort.signal);
      if (input.value.trim() === text) showSuggestions(items);
    } catch (err) {
      if (err.name !== "AbortError") closeSuggestions();
    }
  }, 250);
});

input.addEventListener("keydown", (e) => {
  if (listbox.hidden) return;
  if (e.key === "ArrowDown") {
    e.preventDefault();
    setActive((activeIndex + 1) % suggestions.length);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    setActive(activeIndex <= 0 ? suggestions.length - 1 : activeIndex - 1);
  } else if (e.key === "Enter" && activeIndex >= 0) {
    e.preventDefault();
    pickSuggestion(activeIndex);
  } else if (e.key === "Escape") {
    closeSuggestions();
  }
});

input.addEventListener("blur", () => setTimeout(closeSuggestions, 120));

form.addEventListener("submit", (e) => {
  e.preventDefault();
  clearTimeout(searchTimer);
  searchAbort?.abort();
  submitQuery();
});

// ---------- Use my location ----------

$("locate").addEventListener("click", () => {
  if (!navigator.geolocation) {
    setStatus("This browser can't share its location. Search for a city instead.", "error");
    return;
  }
  setStatus("Finding your location…");
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const q = `${pos.coords.latitude.toFixed(4)},${pos.coords.longitude.toFixed(4)}`;
      load(q, "your location");
    },
    (err) => {
      const msg = err.code === err.PERMISSION_DENIED
        ? "Location access was blocked. Allow it in your browser, or search for a city."
        : "Couldn't get your location. Search for a city instead.";
      setStatus(msg, "error");
    },
    { timeout: 10000 },
  );
});

$("icon").addEventListener("error", () => $("icon").classList.add("failed"));

// ---------- Start ----------

loadModelInfo();

try {
  const last = JSON.parse(localStorage.getItem(LAST_KEY) || "null");
  if (last && last.q && last.label) {
    input.value = last.label;
    load(last.q, last.label);
  }
} catch { /* storage unavailable */ }
