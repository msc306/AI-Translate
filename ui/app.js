"use strict";

const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;
const $ = (id) => document.getElementById(id);

const state = {
  nextId: 1,
  translateId: null,
  busy: false,
  output: "",
  lastRequest: null,
  lastDone: null,
  info: null,
  config: null,
  layout: null,
  phrases: [],
  autoTimer: null,
  pendingPack: null,
};

const STAGES = {
  start: "Starte …",
  vram_check: "Prüfe freien Grafikspeicher …",
  loading: "Lade Modell …",
  translating: "Übersetze …",
  retry: "Ergebnis auffällig – versuche es noch einmal …",
  unloading: "Gebe Grafikspeicher frei …",
};
const SIZE_LABELS = { small: "Klein", medium: "Mittel", large: "Groß" };
const PROVIDERS = ["claude_sub", "claude_api", "chatgpt_sub", "openai_api"];
const MATCH_LABELS = { whole: "ganzer Text", exact: "fester Eintrag", similar: "ähnlich" };

function send(message) {
  const id = state.nextId++;
  invoke("sidecar_send", { msg: { id, ...message } }).catch((err) => showError(String(err)));
  return id;
}

function setStatus(text, busy = false) {
  $("status").textContent = text || "";
  $("status").classList.toggle("busy", busy);
}

function setBusy(busy) {
  state.busy = busy;
  $("btn-cancel").hidden = !busy;
}

function showError(text) {
  setBusy(false);
  setStatus("");
  $("output").classList.add("error");
  $("output").textContent = text;
}

function el(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

function languageLabel(code) {
  return state.info?.languages.catalog.find((l) => l.code === code)?.label || code.toUpperCase();
}

// ---------- Übersetzen ----------

function clearResult() {
  state.output = "";
  state.lastDone = null;
  $("output").classList.remove("error");
  $("output").textContent = "";
  $("meta").textContent = "";
  $("warnings").hidden = true;
  $("used").hidden = true;
}

function translate() {
  const text = $("input").value;
  clearTimeout(state.autoTimer);
  clearResult();
  if (!text.trim()) {
    setStatus("");
    return;
  }
  const engine = $("engine").value || "local";
  setBusy(true);
  setStatus(STAGES.start, true);
  state.lastRequest = { text };
  state.translateId = send({
    cmd: "translate",
    text,
    source: $("source").value || "auto",
    target: $("target").value || "auto",
    engine,
    size: $("size").value,
    style: $("style").value || "neutral",
  });
}

function scheduleAuto(delay) {
  clearTimeout(state.autoTimer);
  if (!$("auto").checked) return;
  state.autoTimer = setTimeout(() => {
    if (state.lastRequest?.text !== $("input").value) translate();
  }, delay);
}

function onDone(e) {
  setBusy(false);
  setStatus("");
  state.lastDone = e;
  const parts = [];
  if (e.source && e.target) parts.push(`${languageLabel(e.source)} → ${languageLabel(e.target)}`);
  if (e.engine === "phrasebook") parts.push("Phrasenbuch");
  else if (e.engine === "local") {
    parts.push(`lokal · ${e.model}`);
    if (e.seconds != null) parts.push(`${e.seconds} s (davon Laden ${e.load_seconds ?? 0} s)`);
    parts.push(e.unloaded ? `Grafikspeicher freigegeben (${e.vram_free_after_mb} MB frei)` : "Modell noch geladen");
  } else if (e.engine && e.engine !== "none") {
    const label = state.info?.engines.find((x) => x.id === e.engine)?.label || e.engine;
    parts.push(e.model ? `${label} · ${e.model}` : label);
    if (e.seconds != null) parts.push(`${e.seconds} s`);
    if (e.usage) {
      let usage = `${e.usage.input_tokens} + ${e.usage.output_tokens} Token`;
      if (e.usage.cost_usd != null) usage += ` ≈ ${e.usage.cost_usd.toFixed(4)} $`;
      parts.push(usage);
    }
  }
  $("meta").textContent = parts.join(" · ");

  const warnings = e.warnings || [];
  $("warnings").hidden = !warnings.length;
  $("warnings").textContent = warnings.map((w) => "⚠ " + w.message).join("\n");

  const used = e.used || [];
  $("used").hidden = !used.length;
  if (used.length) {
    $("used").querySelector("summary").textContent =
      used.length === 1 ? "1 Eintrag aus dem Phrasengedächtnis verwendet" : `${used.length} Einträge aus dem Phrasengedächtnis verwendet`;
    $("used-list").replaceChildren(...used.map((u) => {
      let tag = MATCH_LABELS[u.match] || u.match;
      if (u.similarity != null) tag += ` ${Math.round(u.similarity * 100)} %`;
      return el("div", { className: "used-row" },
        el("span", { className: "tag", textContent: tag }),
        el("span", { textContent: `${u.source} → ${u.target}` }));
    }));
  }
}

function onError(e) {
  if (e.code === "cancelled") {
    setBusy(false);
    setStatus("Abgebrochen.");
    return;
  }
  if (e.code === "pack_failed") {
    $("pack-status").textContent = e.message;
    return;
  }
  if (e.code === "phrase_invalid") {
    setStatus(e.message);
    return;
  }
  let text = e.message || "Unbekannter Fehler.";
  if (e.code === "vram_insufficient") {
    text = `Nicht genug freier Grafikspeicher: ${e.free_mb} MB frei, benötigt ${e.need_mb} MB plus ${e.reserve_mb} MB Reserve. ` +
      "Es wurde nichts geladen. Wähle ein kleineres Modell oder versuche es später erneut.";
  }
  showError(text);
}

// ---------- Sidecar-Ereignisse ----------

function onSidecar(e) {
  switch (e.event) {
    case "ready":
      send({ cmd: "status" });
      break;
    case "status_info":
      applyStatusInfo(e);
      break;
    case "config":
      send({ cmd: "status" });
      break;
    case "phrases":
      state.phrases = e.phrases || [];
      renderPhrases();
      break;
    case "pack_installed":
      $("pack-status").textContent = `Sprachpaket „${e.pack}“ installiert.`;
      $("pack-url").value = "";
      send({ cmd: "status" });
      break;
    case "pack_removed":
      $("pack-status").textContent = `Sprachpaket „${e.pack}“ entfernt.`;
      send({ cmd: "status" });
      break;
    case "provider_models":
      $("openai-models").replaceChildren(...(e.models || []).map((m) => new Option(m, m)));
      $("p-openai_api-state").textContent = `${(e.models || []).length} Modelle gefunden – im Feld „Modell“ auswählbar.`;
      break;
    case "sidecar_exit":
      showError("Der Übersetzungsdienst wurde beendet. Bitte die App neu starten.");
      break;
    case "error":
      if (e.id !== state.translateId || ["pack_failed", "phrase_invalid"].includes(e.code)) {
        if (e.code === "pack_failed" || e.code === "phrase_invalid") onError(e);
        else if (!$("view-settings").hidden) setSettingsNote(e.message);
        return;
      }
      onError(e);
      break;
    default:
      if (e.id !== state.translateId) return;
      if (e.event === "status") setStatus(STAGES[e.stage] || e.stage, true);
      else if (e.event === "progress") setStatus(`Übersetze … Abschnitt ${e.chunk} von ${e.chunks}`, true);
      else if (e.event === "delta" || e.event === "replace") {
        const box = $("output");
        const atEnd = box.scrollHeight - box.scrollTop - box.clientHeight < 30;
        state.output = e.event === "replace" ? e.text : state.output + e.text;
        box.textContent = state.output;
        if (atEnd) box.scrollTop = box.scrollHeight;
      } else if (e.event === "done") onDone(e);
      else if (e.event === "cancelled") { setBusy(false); setStatus("Abgebrochen."); }
  }
}

function setSettingsNote(text) {
  $("p-openai_api-state").textContent = text;
}

/** Fill a select and keep the current (or the wanted) value if it still exists. */
function fillSelect(select, options, wanted) {
  const previous = wanted ?? select.value;
  select.replaceChildren(...options.map(([value, label, disabled]) => {
    const option = new Option(label, value);
    option.disabled = !!disabled;
    return option;
  }));
  const keep = [...select.options].find((o) => o.value === previous && !o.disabled)
    || [...select.options].find((o) => !o.disabled);
  if (keep) select.value = keep.value;
}

function applyStatusInfo(info) {
  const first = !state.info;
  state.info = info;
  state.config = info.config;
  const config = info.config;
  const enabled = info.languages.enabled;
  const langs = enabled.map((code) => [code, languageLabel(code)]);

  fillSelect($("source"), [["auto", "Automatisch erkennen"], ...langs], first ? localStorage.getItem("source") : undefined);
  fillSelect($("target"), [["auto", "Automatisch"], ...langs], first ? localStorage.getItem("target") : undefined);
  fillSelect($("style"), info.styles.map((s) => [s.id, s.label]), first ? (localStorage.getItem("style") || config.style) : undefined);

  const engines = info.engines.filter((e) => e.id === "local" || e.enabled)
    .map((e) => [e.id, e.ready ? e.label : `${e.label} – ${e.reason}`, !e.ready]);
  fillSelect($("engine"), engines, first ? config.engine.default : undefined);
  $("engine").hidden = engines.length < 2;

  for (const option of $("size").options) {
    const preset = info.presets?.[option.value];
    option.disabled = !preset || preset.missing;
    const label = option.textContent.replace(/ – .*/, "");
    option.textContent = option.disabled ? `${label} – nicht installiert` : label;
  }
  if (first) {
    const wanted = localStorage.getItem("size") || config.engine.model;
    const option = [...$("size").options].find((o) => o.value === wanted && !o.disabled)
      || [...$("size").options].find((o) => !o.disabled);
    if (option) $("size").value = option.value;
  }
  $("size").hidden = $("engine").value !== "local";

  renderSettings(info);
  if (first) requestPhrases();
}

// ---------- Einstellungen ----------

function setConfig(config) {
  send({ cmd: "set_config", config });
}

function renderModelRows(info) {
  const rows = [];
  for (const size of Object.keys(SIZE_LABELS)) {
    const preset = info.presets?.[size] || {};
    const configured = info.config.engine.models[size] || "auto";
    const select = el("select");
    const autoLabel = preset.auto && !preset.missing ? `Automatisch (${preset.name})` : "Automatisch";
    select.add(new Option(autoLabel, "auto"));
    for (const model of info.models) {
      select.add(new Option(`${model.name} · ${(model.size_mb / 1024).toFixed(1)} GB · braucht ca. ${model.need_mb} MB VRAM`, model.path));
    }
    if (configured !== "auto" && ![...select.options].some((o) => o.value === configured)) {
      select.add(new Option(`${configured} (Datei fehlt)`, configured));
    }
    select.value = configured;
    select.onchange = () => setConfig({ engine: { models: { [size]: select.value } } });
    const browse = el("button", { textContent: "Durchsuchen …" });
    browse.onclick = async () => {
      const path = await invoke("pick_file", { kind: "model" });
      if (path) setConfig({ engine: { models: { [size]: path } } });
    };
    rows.push(el("label", {}, SIZE_LABELS[size], el("span", { className: "row nowrap" }, select, browse)));
  }
  $("set-model-rows").replaceChildren(...rows);

  const lines = [];
  if (info.vram) lines.push(`Grafikspeicher: ${info.vram.free} von ${info.vram.total} MB frei`);
  if (!info.runtime) lines.push("llama-server wurde nicht gefunden.");
  $("set-models").textContent = lines.join("\n");
}

function renderProviders(info) {
  for (const id of PROVIDERS) {
    const cfg = info.config.providers[id];
    const engine = info.engines.find((e) => e.id === id);
    $(`p-${id}-on`).checked = !!cfg.enabled;
    $(`p-${id}-state`).textContent = engine?.ready ? "Bereit." : (engine?.reason || "");
    if (document.activeElement !== $(`p-${id}-model`)) $(`p-${id}-model`).value = cfg.model || "";
    const key = $(`p-${id}-key`);
    if (key) {
      key.value = "";
      key.placeholder = cfg.key_set ? "gespeichert (neuen Schlüssel eingeben zum Ersetzen)"
        : cfg.key_from_env ? `leer = Umgebungsvariable ${cfg.key_env}` : "Schlüssel eingeben";
    }
  }
  if (document.activeElement !== $("p-openai_api-base_url")) {
    $("p-openai_api-base_url").value = info.config.providers.openai_api.base_url || "";
  }
}

function renderLanguages(info) {
  const enabled = new Set(info.languages.enabled);
  $("set-languages").replaceChildren(...info.languages.catalog.map((lang) => {
    const box = el("input", { type: "checkbox", checked: enabled.has(lang.code) });
    box.onchange = () => {
      const next = info.languages.catalog.map((l) => l.code)
        .filter((code) => (code === lang.code ? box.checked : enabled.has(code)));
      if (next.length < 2) {
        box.checked = true;
        $("pack-status").textContent = "Mindestens zwei Sprachen müssen aktiv bleiben.";
        return;
      }
      setConfig({ languages: { enabled: next } });
    };
    const count = lang.phrases ? ` (${lang.phrases})` : "";
    return el("label", { className: "check", title: lang.phrases ? `${lang.phrases} Redewendungen im Phrasenbuch` : "" },
      box, lang.label + count);
  }));

  $("set-packs").replaceChildren(...info.packs.map((pack) => {
    const texts = el("div", { className: "texts" },
      el("div", { textContent: pack.name || pack.id }),
      el("div", { className: "en", textContent: `${pack.phrases ?? 0} Einträge · ${pack.origin === "user" ? "selbst installiert" : "mitgeliefert"}` }));
    const row = el("div", { className: "ph" }, texts);
    if (pack.origin === "user") {
      const remove = el("button", { textContent: "✕", title: "Sprachpaket entfernen" });
      remove.onclick = () => send({ cmd: "pack_remove", pack: pack.id });
      row.append(remove);
    }
    return row;
  }));
}

function renderSettings(info) {
  const config = info.config;
  renderModelRows(info);
  renderProviders(info);
  renderLanguages(info);
  $("set-reserve").value = config.engine.vram_reserve_mb;
  $("set-keep").value = config.engine.keep_loaded_seconds;
  $("set-vector").checked = !!config.memory.vector;
  $("set-checks").checked = !!config.checks.enabled;
  const memory = info.memory || {};
  $("set-memory").textContent = {
    off: "Aus – es werden nur wörtlich passende Einträge verwendet.",
    loading: "Wird vorbereitet … (beim ersten Mal wird ein Sprachmodell für die Suche geladen, ca. 120 MB)",
    ready: `Bereit – ${memory.count} Texte durchsuchbar.`,
    unavailable: `Nicht verfügbar: ${memory.error || "ChromaDB ist nicht installiert."} Wörtliche Einträge funktionieren weiter.`,
  }[memory.state] || "";
  clearTimeout(state.memoryTimer);
  if (memory.state === "loading") state.memoryTimer = setTimeout(() => send({ cmd: "status" }), 3000);

  const langs = info.languages.enabled.map((code) => [code, languageLabel(code)]);
  const before = [$("ph-source").value, $("ph-target").value];
  fillSelect($("ph-source"), langs);
  fillSelect($("ph-target"), langs, $("ph-target").value || langs[1]?.[0]);
  if ($("ph-source").value === $("ph-target").value) {
    $("ph-target").value = langs.find(([code]) => code !== $("ph-source").value)?.[0] || "";
  }
  if (before[0] !== $("ph-source").value || before[1] !== $("ph-target").value) requestPhrases();
}

// ---------- Phrasenbuch ----------

function requestPhrases() {
  if (!$("ph-source").value || !$("ph-target").value) return;
  send({ cmd: "phrases", source: $("ph-source").value, target: $("ph-target").value });
}

function renderPhrases() {
  const filter = $("ph-filter").value.trim().toLowerCase();
  const list = $("ph-list");
  list.replaceChildren();
  for (const entry of state.phrases) {
    const a = [].concat(entry.source || []).join(" / ");
    const b = entry.target || "";
    if (filter && !(a + " " + b).toLowerCase().includes(filter)) continue;
    const remove = el("button", { textContent: "✕", title: "Eintrag löschen" });
    remove.onclick = () => send({
      cmd: "phrase_delete", entry_id: entry.id, source: $("ph-source").value, target: $("ph-target").value,
    });
    list.append(el("div", { className: "ph" },
      el("div", { className: "texts" },
        el("div", { textContent: a + (entry.origin === "user" ? " ★" : "") }),
        el("div", { className: "en", textContent: b })),
      remove));
  }
}

function savePhrase(source, target, sourceText, targetText) {
  sourceText = sourceText.trim();
  targetText = targetText.trim();
  if (!sourceText || !targetText || !source || !target || source === target) return false;
  send({ cmd: "phrase_save", source, target, source_text: sourceText, target_text: targetText });
  return true;
}

// ---------- Fenster ----------

function applyLayout(layout) {
  state.layout = layout;
  const docked = layout.mode === "docked";
  document.body.classList.toggle("floating", !docked);
  document.body.classList.toggle("edge-left", layout.edge === "left");
  $("btn-dock").textContent = docked ? "⇱" : "⇲";
  $("btn-dock").title = docked ? "Als normales Fenster lösen" : "Am Bildschirmrand andocken";
  $("set-edge").value = layout.edge;
  $("set-width").value = Math.round(layout.width_percent);
  $("set-ontop").checked = layout.floating_on_top;
  $("set-hk-toggle").value = layout.hotkey_toggle;
  $("set-hk-clip").value = layout.hotkey_clipboard;
}

async function setLayout(patch) {
  try {
    applyLayout(await invoke("set_layout", { patch }));
  } catch (err) {
    setStatus(String(err));
  }
}

async function openSettings() {
  $("view-main").hidden = true;
  $("view-settings").hidden = false;
  const monitors = await invoke("list_monitors");
  const select = $("set-monitor");
  select.replaceChildren();
  monitors.forEach((m, index) => {
    const label = `${index + 1}: ${m.name.replace(/^\\\\\.\\/, "")} – ${m.width}×${m.height} bei (${m.x}, ${m.y})${m.primary ? " · Hauptbildschirm" : ""}`;
    select.add(new Option(label, m.name));
  });
  if (!monitors.some((m) => m.name === state.layout.monitor)) {
    select.add(new Option(`${state.layout.monitor} (nicht angeschlossen)`, state.layout.monitor));
  }
  select.value = state.layout.monitor;
  $("set-autostart").checked = await invoke("get_autostart");
  send({ cmd: "status" });
}

function initResizer() {
  const handle = $("resizer");
  let lastX = null;
  let pending = 0;
  let running = false;
  const flush = async () => {
    if (running || !pending) return;
    running = true;
    const delta = pending;
    pending = 0;
    try {
      state.layout = await invoke("resize_dock", { deltaPx: delta });
    } finally {
      running = false;
      flush();
    }
  };
  handle.addEventListener("pointerdown", (e) => {
    handle.setPointerCapture(e.pointerId);
    handle.classList.add("active");
    lastX = e.screenX;
  });
  handle.addEventListener("pointermove", (e) => {
    if (lastX === null) return;
    const dx = Math.round((e.screenX - lastX) * window.devicePixelRatio);
    if (!dx) return;
    lastX = e.screenX;
    pending += state.layout.edge === "left" ? dx : -dx;
    flush();
  });
  const end = () => {
    lastX = null;
    handle.classList.remove("active");
    if (state.layout) $("set-width").value = Math.round(state.layout.width_percent);
  };
  handle.addEventListener("pointerup", end);
  handle.addEventListener("pointercancel", end);
}

// ---------- Start ----------

function initProviders() {
  for (const id of PROVIDERS) {
    const patch = (values) => setConfig({ providers: { [id]: values } });
    $(`p-${id}-on`).onchange = () => patch({ enabled: $(`p-${id}-on`).checked });
    $(`p-${id}-model`).onchange = () => patch({ model: $(`p-${id}-model`).value.trim() });
    const key = $(`p-${id}-key`);
    if (key) {
      // The stored key never comes back from the sidecar, so only a typed key is sent.
      key.onchange = () => { if (key.value.trim()) patch({ key: key.value.trim() }); };
      $(`p-${id}-clear`).onclick = () => patch({ key: "" });
    }
  }
  $("p-openai_api-base_url").onchange = () =>
    setConfig({ providers: { openai_api: { base_url: $("p-openai_api-base_url").value.trim() || "https://api.openai.com/v1" } } });
  $("p-openai_api-list").onclick = () => {
    $("p-openai_api-state").textContent = "Lade Modellliste …";
    send({ cmd: "provider_models" });
  };
}

async function init() {
  await listen("sidecar", (e) => onSidecar(e.payload));
  await listen("layout", (e) => applyLayout(e.payload));
  await listen("shown", () => $("input").focus());
  await listen("translate-clipboard", pasteAndTranslate);

  applyLayout(await invoke("get_layout"));
  initResizer();
  initProviders();

  $("auto").checked = localStorage.getItem("auto") !== "0";
  $("auto").onchange = () => localStorage.setItem("auto", $("auto").checked ? "1" : "0");
  const retranslate = () => { if ($("input").value.trim()) translate(); };
  for (const id of ["source", "target", "style", "size"]) {
    $(id).onchange = () => { localStorage.setItem(id, $(id).value); retranslate(); };
  }
  $("engine").onchange = () => {
    $("size").hidden = $("engine").value !== "local";
    setConfig({ engine: { default: $("engine").value } });
    retranslate();
  };
  $("btn-swap").onclick = () => {
    const done = state.lastDone;
    const source = $("source").value === "auto" ? done?.source : $("source").value;
    const target = $("target").value === "auto" ? done?.target : $("target").value;
    if (!source || !target) return;
    $("source").value = target;
    $("target").value = source;
    localStorage.setItem("source", target);
    localStorage.setItem("target", source);
    if (done && $("output").textContent.trim() && !$("output").classList.contains("error")) {
      $("input").value = $("output").textContent;
    }
    retranslate();
  };

  $("input").addEventListener("input", () => scheduleAuto(1200));
  $("input").addEventListener("paste", () => scheduleAuto(150));
  $("input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.ctrlKey) { e.preventDefault(); translate(); }
  });

  $("btn-translate").onclick = () => translate();
  $("btn-cancel").onclick = () => send({ cmd: "cancel" });
  $("btn-paste").onclick = pasteAndTranslate;
  $("btn-clear").onclick = () => {
    send({ cmd: "cancel" });
    $("input").value = "";
    state.lastRequest = null;
    translate();
    $("input").focus();
  };
  $("btn-copy").onclick = async () => {
    await invoke("write_clipboard", { text: $("output").textContent });
    setStatus("Kopiert.");
  };
  $("btn-save-phrase").onclick = () => {
    const done = state.lastDone;
    if (state.busy || !done || $("output").classList.contains("error")) {
      setStatus("Nichts zu speichern.");
      return;
    }
    const ok = savePhrase(done.source, done.target, state.lastRequest?.text || "", $("output").textContent);
    setStatus(ok ? "Ins Phrasenbuch übernommen – gilt ab der nächsten Übersetzung." : "Nichts zu speichern.");
  };

  $("btn-dock").onclick = async () => applyLayout(await invoke("toggle_dock"));
  $("btn-hide").onclick = () => invoke("hide_window");
  $("btn-settings").onclick = openSettings;
  $("btn-back").onclick = () => {
    $("view-settings").hidden = true;
    $("view-main").hidden = false;
  };

  $("set-monitor").onchange = () => setLayout({ monitor: $("set-monitor").value });
  $("set-edge").onchange = () => setLayout({ edge: $("set-edge").value });
  $("set-width").onchange = () => setLayout({ width_percent: Number($("set-width").value) || 25 });
  $("set-ontop").onchange = () => setLayout({ floating_on_top: $("set-ontop").checked });
  $("set-hk-toggle").onchange = () => setLayout({ hotkey_toggle: $("set-hk-toggle").value.trim() });
  $("set-hk-clip").onchange = () => setLayout({ hotkey_clipboard: $("set-hk-clip").value.trim() });
  $("set-autostart").onchange = async () => {
    $("set-autostart").checked = await invoke("set_autostart", { enabled: $("set-autostart").checked });
  };
  $("set-reserve").onchange = () => setConfig({ engine: { vram_reserve_mb: Number($("set-reserve").value) || 0 } });
  $("set-keep").onchange = () => setConfig({ engine: { keep_loaded_seconds: Number($("set-keep").value) || 0 } });
  $("set-vector").onchange = () => setConfig({ memory: { vector: $("set-vector").checked } });
  $("set-checks").onchange = () => setConfig({ checks: { enabled: $("set-checks").checked } });

  $("pack-file").onclick = async () => {
    const path = await invoke("pick_file", { kind: "pack" });
    if (!path) return;
    $("pack-status").textContent = "Installiere …";
    send({ cmd: "pack_install", path });
  };
  $("pack-download").onclick = () => {
    const url = $("pack-url").value.trim();
    if (!url) return;
    $("pack-status").textContent = "Lade herunter …";
    send({ cmd: "pack_install", url });
  };

  $("ph-source").onchange = $("ph-target").onchange = requestPhrases;
  $("ph-add").onclick = () => {
    if (savePhrase($("ph-source").value, $("ph-target").value, $("ph-a").value, $("ph-b").value)) {
      $("ph-a").value = "";
      $("ph-b").value = "";
    }
  };
  $("ph-filter").oninput = renderPhrases;

  // Falls der Sidecar schon bereit war, bevor die Oberfläche zuhörte.
  send({ cmd: "status" });
}

async function pasteAndTranslate() {
  const text = await invoke("read_clipboard");
  if (!text) return;
  $("view-settings").hidden = true;
  $("view-main").hidden = false;
  $("input").value = text;
  translate();
}

init();
