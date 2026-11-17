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
  explainId: null,
  ocrId: null,
  ocrNote: null,
  history: [],
  quietHistoryId: null,
  sentCorrection: "",
  downloads: {},
  recordId: null,     // id of the running record_start, null when idle
  recognising: false, // recording stopped, text not yet back
  speaking: null,     // "input" or "output" while a text is read aloud
};

// downloads that belong to speech input; they are listed in the speech section, not in the first-start guide
const SPEECH_ITEMS = ["whisper", "speech_model"];
const SPEECH_MODEL_LINK = "https://huggingface.co/ggerganov/whisper.cpp/tree/main";

const DOWNLOAD_STATES = ["running", "verifying", "extracting", "done", "cancelled", "error"];
const STAGE_NAMES = ["start", "vram_check", "loading", "translating", "retry", "unloading", "clarify", "review",
  "explaining", "ocr", "senses"];
const SIZES = ["small", "medium", "large"];
const PROVIDERS = ["claude_sub", "claude_api", "chatgpt_sub", "openai_api", "openrouter"];
const OPENROUTER_KEYS_URL = "https://openrouter.ai/keys";
const MATCHES = ["whole", "exact", "similar"];

// Where a model of each size can be downloaded; opened in the browser from the settings.
const MODEL_LINKS = {
  small: { name: "Gemma 4 E2B", url: "https://huggingface.co/lmstudio-community/gemma-4-E2B-it-GGUF" },
  medium: { name: "Gemma 3 12B", url: "https://huggingface.co/lmstudio-community/gemma-3-12b-it-GGUF" },
  large: { name: "Gemma 3 27B", url: "https://huggingface.co/lmstudio-community/gemma-3-27b-it-GGUF" },
};
const PACK_EXAMPLE_URL = "https://raw.githubusercontent.com/msc306/AI-Translate/main/packs/de-en/manifest.json";
const PACK_SOURCE_URL = "https://github.com/msc306/AI-Translate/tree/main/packs";

/** Status text of a stage the sidecar reports; an unknown stage shows its name. */
function stageText(stage) {
  return STAGE_NAMES.includes(stage) ? t("stage_" + stage) : stage;
}

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
  return languageName(code, state.info?.languages.catalog.find((l) => l.code === code)?.label);
}

function showView(name) {
  for (const view of ["main", "settings", "history"]) $("view-" + view).hidden = view !== name;
}

/** Show a short message where the user is looking right now. */
function note(text) {
  if (!$("view-history").hidden) $("hist-note").textContent = text;
  else if (!$("view-settings").hidden) $("pack-status").textContent = text;
  else setStatus(text);
}

// ---------- Translate ----------

function clearResult() {
  state.output = "";
  state.lastDone = null;
  $("output").classList.remove("error");
  $("output").textContent = "";
  $("meta").textContent = "";
  $("warnings").hidden = true;
  $("used").hidden = true;
  $("question").hidden = true;
  $("explain").hidden = true;
  $("senses").hidden = true;
  state.explainId = null;
}

function translate(extra = {}) {
  const text = $("input").value;
  clearTimeout(state.autoTimer);
  clearResult();
  if (!text.trim()) {
    setStatus("");
    return;
  }
  const engine = $("engine").value || "local";
  setBusy(true);
  setStatus(t("stage_start"), true);
  state.lastRequest = { text };
  state.translateId = send({
    cmd: "translate",
    text,
    source: $("source").value || "auto",
    target: $("target").value || "auto",
    engine,
    size: $("size").value,
    style: $("style").value || "neutral",
    thorough: $("thorough").checked,
    clarify: $("clarify").checked,
    ...extra,
  });
}

/** The model found the text ambiguous: let the user pick a reading, then translate with it. */
function onQuestion(e) {
  setBusy(false);
  setStatus("");
  $("question-text").textContent = e.question;
  const buttons = (e.options || []).map((option) => {
    const button = el("button", { textContent: option.label, title: option.meaning });
    button.onclick = () => translate({ clarification: option.meaning });
    return button;
  });
  const skip = el("button", { textContent: t("skip_question") });
  skip.onclick = () => translate({ clarify: false });
  $("question-options").replaceChildren(...buttons, skip);
  $("question").hidden = false;
}

/** Remember an edited translation in the history, so it can be exported or saved as a phrase later. */
function noteCorrection() {
  const done = state.lastDone;
  const text = $("output").textContent.trim();
  if (state.busy || !done?.history_id || !text || $("output").classList.contains("error")) return;
  if (text === state.sentCorrection) return;
  state.sentCorrection = text;
  state.quietHistoryId = send({ cmd: "history_correct", entry_id: done.history_id, text });
}

function explain() {
  const done = state.lastDone;
  const translation = $("output").textContent.trim();
  if (state.busy || !done || !translation || $("output").classList.contains("error")) {
    setStatus(t("no_translation_to_explain"));
    return;
  }
  setBusy(true);
  setStatus(t("stage_explaining"), true);
  $("explain").hidden = true;
  state.explainId = send({
    cmd: "explain",
    text: state.lastRequest?.text || "",
    translation,
    source: done.source,
    target: done.target,
    engine: $("engine").value || "local",
    size: $("size").value,
  });
}

function onExplanation(e) {
  if (e.id !== state.explainId) return;
  state.explainId = null;
  setBusy(false);
  setStatus("");
  const nodes = [el("div", { textContent: e.summary || t("no_particulars") })];
  if (e.alternatives?.length) {
    nodes.push(el("h3", { textContent: t("alternatives") }));
    for (const alt of e.alternatives) {
      const take = el("button", { textContent: t("take") });
      take.onclick = () => {
        $("output").textContent = alt.text;
        noteCorrection();
      };
      nodes.push(el("div", { className: "alt" },
        el("div", {},
          el("div", { textContent: alt.text }),
          el("div", { className: "note", textContent: alt.note }),
          alt.example ? el("div", { className: "example", textContent: t("example_prefix") + "„" + alt.example + "“" }) : ""),
        take));
    }
  }
  if (e.notes?.length) {
    nodes.push(el("h3", { textContent: t("remarks") }));
    for (const item of e.notes) {
      nodes.push(el("div", {}, el("strong", { textContent: item.source }), el("span", { className: "note", textContent: " – " + item.note })));
    }
  }
  $("explain-body").replaceChildren(...nodes);
  $("explain").open = true; // a fresh explanation is shown; the summary line folds it away again
  $("explain").hidden = false;
}

/** One shared bubble for the small "i" icons: shows the text on hover, focus or tap. */
function initInfoTips() {
  const bubble = el("div", { id: "tip", hidden: true });
  bubble.setAttribute("role", "tooltip");
  document.body.append(bubble);
  const show = (icon) => {
    bubble.textContent = t(icon.dataset.tip);
    bubble.hidden = false;
    const box = icon.getBoundingClientRect();
    const width = Math.min(260, window.innerWidth - 16);
    bubble.style.width = width + "px";
    bubble.style.left = Math.max(8, Math.min(box.left + box.width / 2 - width / 2, window.innerWidth - width - 8)) + "px";
    const below = box.bottom + 6;
    const fits = below + bubble.offsetHeight <= window.innerHeight - 8;
    bubble.style.top = (fits ? below : Math.max(8, box.top - 6 - bubble.offsetHeight)) + "px";
  };
  const hide = () => { bubble.hidden = true; };
  for (const icon of document.querySelectorAll(".info[data-tip]")) {
    icon.setAttribute("role", "img");
    icon.addEventListener("mouseenter", () => show(icon));
    icon.addEventListener("focus", () => show(icon));
    icon.addEventListener("mouseleave", hide);
    icon.addEventListener("blur", hide);
  }
  window.addEventListener("scroll", hide, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
}

/** Read the text from the screenshot in the clipboard, put it into the input and translate it. */
function readScreenshot() {
  if (state.busy) send({ cmd: "cancel" });
  state.translateId = null; // the answer of a translation still running is no longer wanted
  clearTimeout(state.autoTimer);
  showView("main");
  clearResult();
  setBusy(true);
  setStatus(t("stage_ocr"), true);
  state.ocrId = send({ cmd: "ocr", clipboard: true, lang: $("source").value || "auto" });
}

function onOcr(e) {
  if (e.id !== state.ocrId) return;
  state.ocrId = null;
  const wanted = $("source").value || "auto";
  state.ocrNote = e.matched || wanted === "auto" ? null : {
    text: e.text,
    message: t("ocr_note", { language: languageLabel(wanted), used: e.lang }),
  };
  $("input").value = e.text;
  translate();
}

/** True when a paste carries a picture and no text, as a screenshot does. */
function isImagePaste(data) {
  if (!data || data.getData("text/plain")) return false;
  return [...data.items].some((item) => item.kind === "file" && item.type.startsWith("image/"));
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
  state.sentCorrection = state.output.trim();
  const parts = [];
  if (e.source && e.target) parts.push(`${languageLabel(e.source)} → ${languageLabel(e.target)}`);
  if (e.engine === "phrasebook") parts.push(t("phrasebook"));
  else if (e.engine === "local") {
    parts.push(t("meta_local", { model: e.model }));
    if (e.seconds != null) parts.push(t("meta_seconds", { seconds: e.seconds, load: e.load_seconds ?? 0 }));
    parts.push(e.unloaded ? t("meta_unloaded", { free: e.vram_free_after_mb }) : t("meta_loaded"));
  } else if (e.engine && e.engine !== "none") {
    const label = state.info?.engines.find((x) => x.id === e.engine)?.label || e.engine;
    parts.push(e.model ? `${label} · ${e.model}` : label);
    if (e.seconds != null) parts.push(`${e.seconds} s`);
    if (e.usage) {
      let usage = t("meta_tokens", { input: e.usage.input_tokens, output: e.usage.output_tokens });
      if (e.usage.cost_usd != null) usage += ` ≈ ${e.usage.cost_usd.toFixed(4)} $`;
      parts.push(usage);
    }
  }
  if (e.review) parts.push(e.review.changed ? t("review_changed") : t("review_ok"));
  $("meta").textContent = parts.join(" · ");

  const lines = (e.warnings || []).map((w) => "⚠ " + w.message)
    .concat((e.review?.issues || []).map((issue) => "✎ " + t("corrected_prefix") + issue));
  if (state.ocrNote?.text === state.lastRequest?.text) lines.push("⚠ " + state.ocrNote.message);
  $("warnings").hidden = !lines.length;
  $("warnings").textContent = lines.join("\n");

  const used = e.used || [];
  $("used").hidden = !used.length;
  if (used.length) {
    $("used").querySelector("summary").textContent =
      used.length === 1 ? t("used_one") : t("used_many", { count: used.length });
    $("used-list").replaceChildren(...used.map((u) => {
      let tag = MATCHES.includes(u.match) ? t("match_" + u.match) : u.match;
      if (u.similarity != null) tag += ` ${Math.round(u.similarity * 100)} %`;
      return el("div", { className: "used-row" },
        el("span", { className: "tag", textContent: tag }),
        el("span", { textContent: `${u.source} → ${u.target}` }));
    }));
  }
  renderSenses(e.senses || []);
}

/** Single words or word lists: common meanings, each with a short example sentence. */
function renderSenses(words) {
  $("senses").hidden = !words.length;
  if (!words.length) return;
  const nodes = [];
  for (const entry of words) {
    if (words.length > 1) nodes.push(el("h3", { textContent: entry.word }));
    for (const sense of entry.senses) {
      const head = el("div", { className: "sense-head" }, el("strong", { textContent: sense.translation }));
      if (sense.meaning) head.append(el("span", { className: "note", textContent: " – " + sense.meaning }));
      const row = el("div", { className: "sense" }, head);
      if (sense.example) {
        row.append(el("div", { className: "example", textContent: "„" + sense.example + "“" }));
        if (sense.example_translation) {
          row.append(el("div", { className: "example note", textContent: "→ " + sense.example_translation }));
        }
      }
      nodes.push(row);
    }
  }
  $("senses-body").replaceChildren(...nodes);
  $("senses").open = true;
}

function onError(e) {
  if (e.code === "cancelled") {
    setBusy(false);
    setStatus(t("cancelled"));
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
  let text = e.message || t("unknown_error");
  if (e.code === "vram_insufficient") {
    text = t("vram_insufficient", { free: e.free_mb, need: e.need_mb, reserve: e.reserve_mb });
  }
  showError(text);
}

// ---------- Sidecar events ----------

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
      $("pack-status").textContent = t("pack_installed", { pack: e.pack });
      $("pack-url").value = "";
      send({ cmd: "status" });
      break;
    case "pack_removed":
      $("pack-status").textContent = t("pack_removed", { pack: e.pack });
      send({ cmd: "status" });
      break;
    case "provider_models":
      if (e.provider === "openrouter") {
        state.orModels = e.models || [];
        $("or-picker").hidden = false;
        renderOpenRouterModels();
        $("p-openrouter-state").textContent = t("models_found", { count: state.orModels.length });
        break;
      }
      state.openaiModels = (e.models || []).map((m) => m.id);
      $("openai-models").replaceChildren(...(e.models || []).map((m) => new Option(m.id, m.id)));
      $("p-openai_api-state").textContent = t("models_found", { count: (e.models || []).length });
      break;
    case "sidecar_exit":
      showError(t("sidecar_exit"));
      break;
    case "history":
      state.history = e.items || [];
      if (e.id === state.quietHistoryId) state.quietHistoryId = null;
      else renderHistory();
      break;
    case "exported":
      note(t("exported", { count: e.count, path: e.path }));
      break;
    case "explanation":
      onExplanation(e);
      break;
    case "download":
      onDownload(e);
      break;
    case "ocr":
      onOcr(e);
      break;
    case "recording":
      onRecording(e);
      break;
    case "speech":
      onSpeech(e);
      break;
    case "error":
      if (e.id === state.recordId) {
        state.recordId = null;
        state.recognising = false;
        showMic();
        setBusy(false);
        setStatus(e.message);
        return;
      }
      if (e.id === state.ocrId) {
        state.ocrId = null;
        setBusy(false);
        setStatus(e.message);
        return;
      }
      if (e.id === state.explainId) {
        state.explainId = null;
        setBusy(false);
        setStatus(e.code === "cancelled" ? t("cancelled") : e.message);
        return;
      }
      if (e.code === "export_failed") {
        note(e.message);
        return;
      }
      if (e.id && e.id === state.orListId) {
        state.orListId = null;
        $("p-openrouter-state").textContent = e.message;
        return;
      }
      if (e.id !== state.translateId || ["pack_failed", "phrase_invalid"].includes(e.code)) {
        if (e.code === "pack_failed" || e.code === "phrase_invalid") onError(e);
        else if (!$("view-settings").hidden) setSettingsNote(e.message);
        return;
      }
      onError(e);
      break;
    default:
      if (e.id === state.explainId && e.event === "status") {
        setStatus(stageText(e.stage), true);
        return;
      }
      if (e.id !== state.translateId) return;
      if (e.event === "status") setStatus(stageText(e.stage), true);
      else if (e.event === "progress") setStatus(t("progress", { chunk: e.chunk, chunks: e.chunks }), true);
      else if (e.event === "delta" || e.event === "replace") {
        const box = $("output");
        const atEnd = box.scrollHeight - box.scrollTop - box.clientHeight < 30;
        state.output = e.event === "replace" ? e.text : state.output + e.text;
        box.textContent = state.output;
        if (atEnd) box.scrollTop = box.scrollHeight;
      } else if (e.event === "done") onDone(e);
      else if (e.event === "question") onQuestion(e);
      else if (e.event === "cancelled") { setBusy(false); setStatus(t("cancelled")); }
  }
}

function setSettingsNote(text) {
  $("p-openai_api-state").textContent = text;
}

/** Fill a select and keep the current (or the wanted) value if it still exists. */
// ---------- Speech: microphone input and reading aloud ----------

function showMic() {
  const button = $("btn-mic");
  const recording = Boolean(state.recordId) && !state.recognising;
  button.classList.toggle("active", recording);
  button.disabled = state.recognising;
  button.title = recording ? t("mic_stop_title") : t("mic_title");
}

function toggleMic() {
  if (state.recognising) return;
  if (state.recordId) {
    state.recognising = true;
    state.recordId = send({ cmd: "record_stop", lang: $("source").value || uiLanguage });
    showMic();
    setStatus(t("stage_transcribing"), true);
    return;
  }
  stopSpeaking();
  showView("main");
  state.recordId = send({ cmd: "record_start" });
  showMic();
  setStatus(t("stage_recording"), true);
}

function onRecording(e) {
  if (e.id !== state.recordId) return;
  if (e.state === "stopped") state.recordSeconds = e.seconds;
  if (e.state === "stopped" && !state.recognising) {
    // stopped by the sidecar itself (maximum length reached)
    state.recognising = true;
    setStatus(t("stage_transcribing"), true);
  } else if (e.state === "cancelled") {
    state.recordId = null;
    state.recognising = false;
    setStatus("");
  }
  showMic();
}

function onSpeech(e) {
  if (e.id !== state.recordId) return;
  state.recordId = null;
  state.recognising = false;
  showMic();
  const input = $("input");
  const before = input.value.slice(0, input.selectionStart ?? input.value.length);
  const after = input.value.slice(input.selectionEnd ?? input.value.length);
  const gap = before && !/\s$/.test(before) ? " " : "";
  input.value = before + gap + e.text + after;
  const caret = (before + gap + e.text).length;
  input.setSelectionRange(caret, caret);
  input.focus();
  setStatus(t("speech_done", { engine: e.engine === "whisper" ? "Whisper" : "Windows", seconds: state.recordSeconds ?? "?" }));
  if (input.value.trim()) translate();
}

function voicesFor(lang) {
  const voices = window.speechSynthesis ? speechSynthesis.getVoices() : [];
  return voices.filter((v) => v.lang.toLowerCase().startsWith(lang.toLowerCase()));
}

function pickVoice(lang) {
  let chosen = "";
  try { chosen = localStorage.getItem("voice") || ""; } catch {}
  const matching = voicesFor(lang);
  return matching.find((v) => v.name === chosen) || matching.find((v) => v.localService) || matching[0] || null;
}

function stopSpeaking() {
  if (window.speechSynthesis) speechSynthesis.cancel();
  state.speaking = null;
  showSpeakButtons();
}

function showSpeakButtons() {
  for (const [which, id] of [["input", "btn-speak-input"], ["output", "btn-speak-output"]]) {
    const active = state.speaking === which;
    $(id).classList.toggle("active", active);
    $(id).title = active ? t("speak_stop_title") : t(`speak_${which}_title`);
  }
}

function speak(which) {
  if (!window.speechSynthesis) return;
  if (state.speaking === which) {
    stopSpeaking();
    return;
  }
  stopSpeaking();
  const done = state.lastDone;
  const text = which === "input"
    ? $("input").value.trim()
    : ($("output").classList.contains("error") ? "" : $("output").textContent.trim());
  if (!text) {
    setStatus(t("nothing_to_speak"));
    return;
  }
  let lang = which === "input" ? ($("source").value || done?.source) : (done?.target || $("target").value);
  lang = lang || uiLanguage;
  const utterance = new SpeechSynthesisUtterance(text);
  const voice = pickVoice(lang);
  if (voice) {
    utterance.voice = voice;
    utterance.lang = voice.lang;
  } else {
    utterance.lang = lang;
    setStatus(t("no_voice", { language: languageLabel(lang) }));
  }
  utterance.onend = utterance.onerror = () => {
    if (state.speaking === which) {
      state.speaking = null;
      showSpeakButtons();
    }
  };
  state.speaking = which;
  showSpeakButtons();
  speechSynthesis.speak(utterance);
}

function fillVoices() {
  const voices = window.speechSynthesis ? speechSynthesis.getVoices() : [];
  let chosen = "";
  try { chosen = localStorage.getItem("voice") || ""; } catch {}
  fillSelect($("set-voice"), [["", t("voice_auto")], ...voices.map((v) => [v.name, `${v.name} (${v.lang})`])], chosen);
}

function renderSpeechSettings(info) {
  const speechInfo = info.speech || {};
  const config = info.config.speech || {};
  fillSelect($("set-speech-engine"), [
    ["auto", t("speech_engine_auto")],
    ["whisper", t("speech_engine_whisper")],
    ["windows", t("speech_engine_windows")],
  ], config.engine || "auto");
  const models = speechInfo.models || [];
  const configured = config.model || "auto";
  const autoName = speechInfo.auto_model || "";
  const options = [["auto", autoName ? t("speech_model_auto", { name: autoName }) : t("speech_model_none")],
    ...models.map((m) => [m.path, `${m.name} (${m.size_mb} MB)`])];
  if (configured !== "auto" && !models.some((m) => m.path === configured)) {
    options.push([configured, t("file_missing", { path: configured })]);
  }
  fillSelect($("set-speech-model"), options, configured);
  let status = t("speech_none");
  if (speechInfo.whisper && models.length) status = t("speech_ready_whisper");
  else if ((speechInfo.windows || []).length) {
    status = t("speech_ready_windows", { languages: speechInfo.windows.join(", ") });
  }
  $("speech-status").textContent = status;
  fillVoices();
}

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

// ---------- Interface language ----------

/** Switch the texts of the window and of the tray menu; the caller redraws what is built from data. */
function showUiLanguage(code) {
  const lang = setTextLanguage(code);
  try { localStorage.setItem("ui_lang", lang); } catch (err) { /* first paint falls back to German */ }
  applyTexts();
  for (const id of ["ui-lang", "set-ui-lang"]) {
    const long = id === "set-ui-lang";
    fillSelect($(id), UI_LANGUAGES.map((l) => [l, long ? UI_LANGUAGE_NAMES[l] : l.toUpperCase()]), lang);
  }
  $("pack-download-hint").textContent = t("pack_download_hint", { example: PACK_EXAMPLE_URL, source: PACK_SOURCE_URL });
  for (const icon of document.querySelectorAll(".info[data-tip]")) icon.setAttribute("aria-label", t(icon.dataset.tip));
  invoke("set_ui_language", { lang }).catch(() => {});
  if (state.layout) applyLayout(state.layout);
  showMic();
  showSpeakButtons();
  $("speech-model-link").title = t("model_link_title", { url: SPEECH_MODEL_LINK });
}

/** The user picked a language: show it at once and store it, so the sidecar answers in it too. */
function chooseUiLanguage(code) {
  showUiLanguage(code);
  state.uiLangPending = uiLanguage;
  setConfig({ ui_language: uiLanguage });
  if (state.info) applyStatusInfo(state.info);
  if (!$("view-history").hidden) renderHistory();
  if (!$("view-settings").hidden) openSettings();
  renderPhrases();
}

function applyStatusInfo(info) {
  const first = !state.info;
  state.info = info;
  state.config = info.config;
  const config = info.config;
  const stored = config.ui_language;
  if (state.uiLangPending && stored === state.uiLangPending) state.uiLangPending = null;
  if (stored && stored !== uiLanguage && !state.uiLangPending) showUiLanguage(stored);
  const enabled = info.languages.enabled;
  const langs = enabled.map((code) => [code, languageLabel(code)]);

  fillSelect($("source"), [["auto", t("auto_detect")], ...langs], first ? localStorage.getItem("source") : undefined);
  fillSelect($("target"), [["auto", t("auto")], ...langs], first ? localStorage.getItem("target") : undefined);
  fillSelect($("style"), info.styles.map((s) => [s.id, s.label]), first ? (localStorage.getItem("style") || config.style) : undefined);

  const engines = info.engines.filter((e) => e.id === "local" || e.enabled)
    .map((e) => [e.id, e.ready ? e.label : `${e.label} – ${e.reason}`, !e.ready]);
  fillSelect($("engine"), engines, first ? config.engine.default : undefined);
  $("engine").hidden = engines.length < 2;

  for (const option of $("size").options) {
    const preset = info.presets?.[option.value];
    option.disabled = !preset || preset.missing;
    const label = t(`size_${option.value}_opt`);
    option.textContent = option.disabled ? `${label} – ${t("not_installed")}` : label;
  }
  const current = $("size").selectedOptions[0];
  if (first || !current || current.disabled) {
    const wanted = first ? (localStorage.getItem("size") || config.engine.model) : $("size").value;
    const option = [...$("size").options].find((o) => o.value === wanted && !o.disabled)
      || [...$("size").options].find((o) => !o.disabled);
    if (option) $("size").value = option.value;
  }
  renderModelChoice();

  for (const item of info.downloads || []) {
    if (item.running && !state.downloads[item.item]) state.downloads[item.item] = { state: "running" };
  }
  renderSetup(info);
  renderSettings(info);
  if (first) requestPhrases();
}

// ---------- Settings ----------

function setConfig(config) {
  send({ cmd: "set_config", config });
}

function renderModelRows(info) {
  const rows = [];
  for (const size of SIZES) {
    const preset = info.presets?.[size] || {};
    const configured = info.config.engine.models[size] || "auto";
    const select = el("select");
    const autoLabel = preset.auto && !preset.missing ? t("auto_named", { name: preset.name }) : t("auto");
    select.add(new Option(autoLabel, "auto"));
    for (const model of info.models) {
      select.add(new Option(t("model_option", {
        name: model.name, size: (model.size_mb / 1024).toFixed(1), need: model.need_mb,
      }), model.path));
    }
    if (configured !== "auto" && ![...select.options].some((o) => o.value === configured)) {
      select.add(new Option(t("file_missing", { path: configured }), configured));
    }
    select.value = configured;
    select.onchange = () => setConfig({ engine: { models: { [size]: select.value } } });
    const browse = el("button", { textContent: t("browse") });
    browse.onclick = async () => {
      const path = await invoke("pick_file", { kind: "model" });
      if (path) setConfig({ engine: { models: { [size]: path } } });
    };
    const example = MODEL_LINKS[size];
    const link = el("button", { textContent: t("model_link"), title: t("model_link_title", { url: example.url }) });
    link.onclick = () => invoke("open_url", { url: example.url }).catch((err) => setSettingsNote(String(err)));
    rows.push(el("div", { className: "model-row" },
      el("label", {}, t("size_" + size), el("span", { className: "row nowrap" }, select, browse)),
      el("div", { className: "row" }, link),
      el("p", { className: "meta", textContent: t("model_link_hint", { name: example.name }) })));
  }
  $("set-model-rows").replaceChildren(...rows);

  const lines = [];
  if (info.vram) lines.push(t("vram_line", { free: info.vram.free, total: info.vram.total }));
  else lines.push(t("no_gpu"));
  if (!info.runtime) lines.push(t("no_runtime"));
  $("set-models").textContent = lines.join("\n");
  renderDownloads(info);
}

// ---------- First start and downloads ----------

function localReady(info) {
  return !!info.runtime && SIZES.some((size) => info.presets?.[size] && !info.presets[size].missing);
}

function downloadText(item) {
  const run = state.downloads[item.item];
  if (run && run.state !== "done") {
    const amount = run.total_mb ? " · " + t("dl_amount", { done: run.done_mb || 0, total: run.total_mb }) : "";
    const label = DOWNLOAD_STATES.includes(run.state) ? t("dl_" + run.state) : run.state;
    return `${label}${amount}${run.message ? ` · ${run.message}` : ""}`;
  }
  return item.installed ? t("installed") : `${(item.size_mb / 1024).toFixed(1)} GB`;
}

function isRunning(item) {
  const run = state.downloads[item];
  return !!run && ["running", "verifying", "extracting"].includes(run.state);
}

function startDownload(item) {
  state.downloads[item] = { state: "running" };
  send({ cmd: "download", item });
  if (state.info) { renderDownloads(state.info); renderSetup(state.info); }
}

function renderDownloads(info) {
  const rows = (info.downloads || []).filter((item) => !SPEECH_ITEMS.includes(item.item)).map(downloadRow);
  const hint = el("p", { className: "meta", textContent: t("downloads_hint", { dir: info.data_dir }) });
  $("set-downloads").replaceChildren(...rows, ...(rows.length ? [hint] : []));
  $("set-speech-downloads").replaceChildren(
    ...(info.downloads || []).filter((item) => SPEECH_ITEMS.includes(item.item)).map(downloadRow));
}

function downloadRow(item) {
    const button = el("button");
    if (isRunning(item.item)) {
      button.textContent = t("cancel");
      button.onclick = () => send({ cmd: "download_cancel", item: item.item });
    } else {
      button.textContent = item.installed ? t("installed_button") : t("download");
      button.disabled = item.installed;
      button.onclick = () => startDownload(item.item);
    }
    const why = TEXTS["why_" + item.item] ? t("why_" + item.item) : "";
    return el("div", { className: "row nowrap" },
      el("span", { className: "grow" }, item.label,
        el("div", { className: "meta", textContent: downloadText(item) }),
        el("div", { className: "meta", textContent: why })),
      button);
}

function renderSetup(info) {
  const online = info.engines.some((e) => e.id !== "local" && e.enabled && e.ready);
  const downloads = (info.downloads || []).filter((item) => !SPEECH_ITEMS.includes(item.item));
  const anyRunning = downloads.some((item) => isRunning(item.item));
  const show = anyRunning || (!localReady(info) && !online);
  $("setup").hidden = !show;
  if (!show) return;
  const gpu = !!info.vram;
  $("setup-text").textContent = gpu
    ? (localReady(info)
        ? t("setup_ready")
        : t("setup_missing", { what: [
            info.runtime ? null : t("setup_runtime"),
            (info.models || []).length ? null : t("setup_model"),
          ].filter(Boolean).join(t("and")) }))
    : t("setup_no_gpu");
  $("setup-local").hidden = !gpu;
  const missing = downloads.filter((item) => !item.installed);
  const button = $("setup-download");
  button.disabled = anyRunning || !missing.length;
  button.textContent = anyRunning ? t("downloading") : t("setup_download");
  $("setup-progress").textContent = downloads
    .filter((item) => state.downloads[item.item] || item.installed)
    .map((item) => `${item.label}: ${downloadText(item)}`).join("\n");
}

function onDownload(e) {
  const finished = ["done", "cancelled", "error"].includes(e.state);
  state.downloads[e.item] = e;
  if (finished) {
    if (e.state === "done") delete state.downloads[e.item];
    send({ cmd: "status" });
  } else if (state.info) {
    renderDownloads(state.info);
    renderSetup(state.info);
  }
}

function renderProviders(info) {
  for (const id of PROVIDERS) {
    const cfg = info.config.providers[id];
    const engine = info.engines.find((e) => e.id === id);
    $(`p-${id}-on`).checked = !!cfg.enabled;
    $(`p-${id}-state`).textContent = engine?.ready ? t("ready") : (engine?.reason || "");
    if (document.activeElement !== $(`p-${id}-model`)) $(`p-${id}-model`).value = cfg.model || "";
    const key = $(`p-${id}-key`);
    if (key) {
      key.value = "";
      key.placeholder = cfg.key_set ? t("key_saved")
        : cfg.key_from_env ? t("key_env", { name: cfg.key_env }) : t("key_enter");
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
        $("pack-status").textContent = t("min_two_languages");
        return;
      }
      setConfig({ languages: { enabled: next } });
    };
    const count = lang.phrases ? ` (${lang.phrases})` : "";
    return el("label", { className: "check", title: lang.phrases ? t("phrases_count_title", { count: lang.phrases }) : "" },
      box, languageName(lang.code, lang.label) + count);
  }));

  $("set-packs").replaceChildren(...info.packs.map((pack) => {
    const texts = el("div", { className: "texts" },
      el("div", { textContent: pack.name || pack.id }),
      el("div", { className: "en", textContent: t("pack_line", {
        count: pack.phrases ?? 0, origin: pack.origin === "user" ? t("origin_user") : t("origin_bundled"),
      }) }));
    const row = el("div", { className: "ph" }, texts);
    if (pack.origin === "user") {
      const remove = el("button", { textContent: "✕", title: t("pack_remove_title") });
      remove.onclick = () => send({ cmd: "pack_remove", pack: pack.id });
      row.append(remove);
    }
    return row;
  }));
}

function renderSettings(info) {
  const config = info.config;
  renderModelRows(info);
  renderSpeechSettings(info);
  renderProviders(info);
  renderLanguages(info);
  $("set-reserve").value = config.engine.vram_reserve_mb;
  $("set-keep").value = config.engine.keep_loaded_seconds;
  $("set-vector").checked = !!config.memory.vector;
  $("set-checks").checked = !!config.checks.enabled;
  $("set-history").checked = config.history?.enabled !== false;
  const memory = info.memory || {};
  $("set-memory").textContent = {
    off: t("mem_off"),
    loading: t("mem_loading"),
    ready: t("mem_ready", { count: memory.count }),
    unavailable: t("mem_unavailable", { error: memory.error || t("mem_no_chroma") }),
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

// ---------- Phrasebook ----------

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
    const remove = el("button", { textContent: "✕", title: t("entry_delete_title") });
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

// ---------- History ----------

function historyCommand(cmd, extra = {}) {
  return send({ cmd, query: $("hist-filter").value, corrected_only: $("hist-corrected").checked, ...extra });
}

function openHistory() {
  showView("history");
  $("hist-note").textContent = t("hist_note");
  historyCommand("history");
}

function renderHistory() {
  const list = $("hist-list");
  if (!state.history.length) {
    list.replaceChildren(el("div", { className: "meta", textContent: t("no_entries") }));
    return;
  }
  list.replaceChildren(...state.history.map((entry) => {
    const current = () => (entry.corrected || entry.output || "").trim();
    const tag = el("span", { className: "tag", textContent: t("corrected"), hidden: !entry.corrected });
    const out = el("div", {
      className: "out", contentEditable: "plaintext-only", spellcheck: false,
      textContent: current(), title: t("click_to_correct"),
    });
    // No re-render after this save: a click on a button of the same entry must still land.
    out.onblur = () => {
      const text = out.textContent.trim();
      if (!text || text === current()) return;
      entry.corrected = text === (entry.output || "").trim() ? "" : text;
      tag.hidden = !entry.corrected;
      state.quietHistoryId = historyCommand("history_correct", { entry_id: entry.id, text });
    };
    const load = el("button", { textContent: "↩", title: t("load_title") });
    load.onclick = () => {
      clearResult();
      $("input").value = entry.source_text;
      state.lastRequest = { text: entry.source_text };
      state.output = current();
      state.sentCorrection = state.output;
      $("output").textContent = state.output;
      state.lastDone = { source: entry.source, target: entry.target, history_id: entry.id };
      $("meta").textContent = `${languageLabel(entry.source)} → ${languageLabel(entry.target)} · ${t("from_history", { time: entry.time })}`;
      showView("main");
    };
    const star = el("button", { textContent: "★", title: t("star_title") });
    star.onclick = () => {
      const ok = savePhrase(entry.source, entry.target, entry.source_text, out.textContent);
      note(ok ? t("saved_as_phrase") : t("nothing_to_save"));
    };
    const remove = el("button", { textContent: "✕", title: t("entry_delete_title") });
    remove.onclick = () => historyCommand("history_delete", { entry_id: entry.id });
    const engine = state.info?.engines.find((x) => x.id === entry.engine)?.label || entry.engine;
    return el("div", { className: "hist" },
      el("div", { className: "head" },
        el("span", { textContent: `${entry.time} · ${languageLabel(entry.source)} → ${languageLabel(entry.target)} · ${engine}` }),
        tag, el("span", { className: "spacer" }), load, star, remove),
      el("div", { className: "src", textContent: entry.source_text }),
      out);
  }));
}

// ---------- Window ----------

function applyLayout(layout) {
  state.layout = layout;
  const docked = layout.mode === "docked";
  document.body.classList.toggle("floating", !docked);
  document.body.classList.toggle("edge-left", layout.edge === "left");
  $("btn-dock").textContent = docked ? "⇱" : "⇲";
  $("btn-dock").title = docked ? t("dock_undock_title") : t("dock_dock_title");
  $("set-edge").value = layout.edge;
  $("set-width").value = Math.round(layout.width_percent);
  $("set-ontop").checked = layout.floating_on_top;
  $("set-hk-toggle").value = layout.hotkey_toggle;
  $("set-hk-clip").value = layout.hotkey_clipboard;
  $("set-hk-mic").value = layout.hotkey_mic || "";
}

async function setLayout(patch) {
  try {
    applyLayout(await invoke("set_layout", { patch }));
  } catch (err) {
    setStatus(String(err));
  }
}

async function openSettings() {
  showView("settings");
  const monitors = await invoke("list_monitors");
  const select = $("set-monitor");
  select.replaceChildren();
  monitors.forEach((m, index) => {
    const label = t("monitor_line", {
      index: index + 1, name: m.name.replace(/^\\\\\.\\/, ""), width: m.width, height: m.height, x: m.x, y: m.y,
    }) + (m.primary ? t("primary") : "");
    select.add(new Option(label, m.name));
  });
  if (!monitors.some((m) => m.name === state.layout.monitor)) {
    select.add(new Option(t("not_connected", { name: state.layout.monitor }), state.layout.monitor));
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
    $("p-openai_api-state").textContent = t("loading_models");
    send({ cmd: "provider_models" });
  };
  $("p-openrouter-list").onclick = () => {
    $("p-openrouter-state").textContent = t("loading_models");
    state.orListId = send({ cmd: "provider_models", provider: "openrouter" });
  };
  $("or-keys").onclick = () => invoke("open_url", { url: OPENROUTER_KEYS_URL }).catch(() => {});
  $("or-search").oninput = renderOpenRouterModels;
  $("or-free").onchange = renderOpenRouterModels;
  // Arrow keys only move the selection; a click or Enter takes the model and folds the list away.
  const takeOpenRouterModel = () => {
    const id = $("or-list").value;
    if (!id) return;
    $("p-openrouter-model").value = id;
    rememberModel("openrouter", id);
    setConfig({ providers: { openrouter: { model: id } } });
    $("or-picker").hidden = true;
    $("p-openrouter-state").textContent = t("model_taken", { model: id });
  };
  $("or-list").onclick = (e) => { if (e.target.tagName === "OPTION") takeOpenRouterModel(); };
  $("or-list").onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); takeOpenRouterModel(); } };
}

// ---------- Model choice in the main window ----------

const CLAUDE_API_MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2"];
const CLAUDE_SUB_MODELS = [["haiku", "Haiku"], ["sonnet", "Sonnet"], ["opus", "Opus"]];
const MORE_MODELS = "__more__";

function recentModels(engine) {
  try { return JSON.parse(localStorage.getItem("models_" + engine) || "[]"); } catch (err) { return []; }
}

function rememberModel(engine, model) {
  if (!model) return;
  const list = [model, ...recentModels(engine).filter((m) => m !== model)].slice(0, 8);
  try { localStorage.setItem("models_" + engine, JSON.stringify(list)); } catch (err) { /* not kept */ }
}

/** Local shows the size choice; an online provider shows its model plus the ones used recently. */
function renderModelChoice() {
  const engine = $("engine").value || "local";
  const local = engine === "local";
  $("size").hidden = !local;
  $("model").hidden = local;
  if (local) return;
  const current = state.config?.providers?.[engine]?.model || "";
  let options;
  if (engine === "claude_sub") {
    options = [...CLAUDE_SUB_MODELS];
  } else {
    const ids = [current, ...recentModels(engine)];
    if (engine === "claude_api") ids.push(...CLAUDE_API_MODELS);
    if (engine === "openai_api") ids.push(...(state.openaiModels || []));
    const names = Object.fromEntries((state.orModels || []).map((m) => [m.id, m.name]));
    options = [...new Set(ids.filter(Boolean))].map((id) => [id, names[id] || id]);
    if (engine === "chatgpt_sub") options.unshift(["", t("model_default")]);
    else if (!current) options.unshift(["", "–"]);
    options.push([MORE_MODELS, t("model_more")]);
  }
  fillSelect($("model"), options, current);
}

async function openModelSettings(engine) {
  await openSettings();
  const field = $(`p-${engine}-model`);
  if (field) field.scrollIntoView({ block: "center" });
  if (engine === "openrouter") {
    if (state.orModels?.length) { $("or-picker").hidden = false; renderOpenRouterModels(); }
    else $("p-openrouter-list").click();
  }
}

/** USD per million tokens, short. */
function formatPrice(value) {
  if (value == null) return "?";
  return value >= 10 ? value.toFixed(0) : value >= 1 ? value.toFixed(2) : value.toFixed(3);
}

function renderOpenRouterModels() {
  const all = state.orModels || [];
  const words = $("or-search").value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const freeOnly = $("or-free").checked;
  const current = $("p-openrouter-model").value.trim();
  const shown = all.filter((m) => (!freeOnly || m.free)
    && words.every((w) => m.id.toLowerCase().includes(w) || (m.name || "").toLowerCase().includes(w)));
  $("or-list").replaceChildren(...shown.slice(0, 400).map((m) => {
    const price = m.free ? t("or_price_free")
      : t("or_price", { input: formatPrice(m.price_in), output: formatPrice(m.price_out) });
    const option = new Option(`${m.name} · ${price}`, m.id);
    option.title = m.id;
    option.selected = m.id === current;
    return option;
  }));
  $("or-count").textContent = t("or_count", { shown: shown.length, total: all.length });
}

async function init() {
  await listen("sidecar", (e) => onSidecar(e.payload));
  await listen("layout", (e) => applyLayout(e.payload));
  await listen("shown", () => $("input").focus());
  await listen("translate-clipboard", pasteAndTranslate);

  // The last language shows at once; the stored setting follows with the first status of the sidecar.
  let remembered = null;
  try { remembered = localStorage.getItem("ui_lang"); } catch (err) { /* German */ }
  showUiLanguage(remembered || "de");
  $("ui-lang").onchange = () => chooseUiLanguage($("ui-lang").value);
  $("set-ui-lang").onchange = () => chooseUiLanguage($("set-ui-lang").value);

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
    renderModelChoice();
    setConfig({ engine: { default: $("engine").value } });
    retranslate();
  };
  $("model").onchange = () => {
    const engine = $("engine").value;
    const model = $("model").value;
    if (model === MORE_MODELS) {
      renderModelChoice();
      openModelSettings(engine);
      return;
    }
    rememberModel(engine, model);
    if (state.config?.providers?.[engine]) state.config.providers[engine].model = model;
    const field = $(`p-${engine}-model`);
    if (field) field.value = model;
    setConfig({ providers: { [engine]: { model } } });
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
  // a pasted screenshot is read as text, wherever the focus is in the main view
  document.addEventListener("paste", (e) => {
    if ($("view-main").hidden || !isImagePaste(e.clipboardData)) return;
    e.preventDefault();
    readScreenshot();
  });
  $("input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.ctrlKey) { e.preventDefault(); translate(); }
  });

  $("btn-translate").onclick = () => translate();
  $("btn-cancel").onclick = () => {
    if (state.ocrId != null) {
      // the recogniser cannot be stopped; its answer is ignored instead
      state.ocrId = null;
      setBusy(false);
      setStatus(t("cancelled"));
      return;
    }
    send({ cmd: "cancel" });
  };
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
    setStatus(t("copied"));
  };
  $("btn-save-phrase").onclick = () => {
    const done = state.lastDone;
    if (state.busy || !done || $("output").classList.contains("error")) {
      setStatus(t("nothing_to_save"));
      return;
    }
    noteCorrection();
    const ok = savePhrase(done.source, done.target, state.lastRequest?.text || "", $("output").textContent);
    setStatus(ok ? t("phrase_taken") : t("nothing_to_save"));
  };

  $("btn-dock").onclick = async () => applyLayout(await invoke("toggle_dock"));
  $("btn-hide").onclick = () => invoke("hide_window");
  $("btn-settings").onclick = openSettings;
  $("setup-settings").onclick = openSettings;
  $("setup-download").onclick = () => {
    // runtime first: it is small and makes the model usable as soon as that arrives
    for (const item of (state.info?.downloads || []).filter((d) => !d.installed && !SPEECH_ITEMS.includes(d.item))) {
      startDownload(item.item);
    }
  };
  $("btn-back").onclick = $("btn-history-back").onclick = () => showView("main");
  $("btn-explain").onclick = explain;
  $("btn-mic").onclick = toggleMic;
  $("btn-speak-input").onclick = () => speak("input");
  $("btn-speak-output").onclick = () => speak("output");
  await listen("mic-toggle", toggleMic);
  if (window.speechSynthesis) speechSynthesis.onvoiceschanged = () => { if (state.info) fillVoices(); };
  initInfoTips();
  $("pack-example").onclick = () => { $("pack-url").value = PACK_EXAMPLE_URL; };
  $("output").addEventListener("blur", noteCorrection);
  for (const id of ["thorough", "clarify"]) {
    $(id).checked = localStorage.getItem(id) === "1";
    $(id).onchange = () => localStorage.setItem(id, $(id).checked ? "1" : "0");
  }

  $("btn-history").onclick = openHistory;
  let filterTimer = null;
  $("hist-filter").oninput = () => {
    clearTimeout(filterTimer);
    filterTimer = setTimeout(() => historyCommand("history"), 250);
  };
  $("hist-corrected").onchange = () => historyCommand("history");
  $("hist-export").onclick = async () => {
    const format = $("hist-format").value;
    const path = await invoke("pick_save", { kind: format, name: `uebersetzungen.${format}` });
    if (path) send({ cmd: "history_export", path, format, corrected_only: $("hist-corrected").checked });
  };
  let clearArmed = null;
  $("hist-clear").onclick = () => {
    if (!clearArmed) {  // second click within four seconds confirms
      $("hist-clear").textContent = t("hist_clear_confirm");
      clearArmed = setTimeout(() => { clearArmed = null; $("hist-clear").textContent = t("hist_clear"); }, 4000);
      return;
    }
    clearTimeout(clearArmed);
    clearArmed = null;
    $("hist-clear").textContent = t("hist_clear");
    historyCommand("history_clear");
  };
  $("set-history").onchange = () => setConfig({ history: { enabled: $("set-history").checked } });
  $("ph-export").onclick = async () => {
    const path = await invoke("pick_save", { kind: "pack", name: "meine-phrasen.zip" });
    if (path) send({ cmd: "phrases_export", path });
  };

  $("set-monitor").onchange = () => setLayout({ monitor: $("set-monitor").value });
  $("set-edge").onchange = () => setLayout({ edge: $("set-edge").value });
  $("set-width").onchange = () => setLayout({ width_percent: Number($("set-width").value) || 25 });
  $("set-ontop").onchange = () => setLayout({ floating_on_top: $("set-ontop").checked });
  $("set-hk-toggle").onchange = () => setLayout({ hotkey_toggle: $("set-hk-toggle").value.trim() });
  $("set-hk-clip").onchange = () => setLayout({ hotkey_clipboard: $("set-hk-clip").value.trim() });
  $("set-hk-mic").onchange = () => setLayout({ hotkey_mic: $("set-hk-mic").value.trim() });
  $("set-speech-engine").onchange = () => setConfig({ speech: { engine: $("set-speech-engine").value } });
  $("set-speech-model").onchange = () => setConfig({ speech: { model: $("set-speech-model").value } });
  $("speech-browse").onclick = async () => {
    const path = await invoke("pick_file", { kind: "speech" });
    if (path) setConfig({ speech: { model: path } });
  };
  $("speech-model-link").onclick = () =>
    invoke("open_url", { url: SPEECH_MODEL_LINK }).catch((err) => setSettingsNote(String(err)));
  $("set-voice").onchange = () => {
    try { localStorage.setItem("voice", $("set-voice").value); } catch {}
  };
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
    $("pack-status").textContent = t("installing");
    send({ cmd: "pack_install", path });
  };
  $("pack-download").onclick = () => {
    const url = $("pack-url").value.trim();
    if (!url) return;
    $("pack-status").textContent = t("downloading_pack");
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

  // If the sidecar was already ready before the UI started listening.
  send({ cmd: "status" });
}

async function pasteAndTranslate() {
  const text = await invoke("read_clipboard");
  if (!text) {
    // no text: the clipboard may hold a screenshot
    readScreenshot();
    return;
  }
  showView("main");
  $("input").value = text;
  translate();
}

init();
