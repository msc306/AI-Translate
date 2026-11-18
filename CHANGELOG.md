# Changelog

All notable changes to this project.

## Unreleased

### New

- macOS support (Apple Silicon and Intel), not yet tested on a real Mac: the app detects the system
  and processor at start. On a Mac the local model runs with Metal (Apple Silicon) or on the
  processor (Intel Macs), screenshots are read with the macOS Vision text recogniser, speech input
  uses ffmpeg or SoX plus whisper.cpp from Homebrew, and the window docks as a strip at the screen
  edge. Settings and data live in `~/Library/Application Support/AITranslate`.
- `Cmd+Enter` translates as well as `Ctrl+Enter`.
- Build script `scripts/build-mac.sh` and a GitHub workflow that builds unsigned `.dmg` files.

## 0.6.0 – 2026-11-18

### New

- Local models run on AMD and Intel graphics cards (llama.cpp with Vulkan) and, more slowly, on the
  processor alone. The graphics card is detected automatically; the settings offer
  "Hardware for local models" to choose another card or the processor, and only the matching
  runtime is offered for download.

## 0.5.0 – 2026-11-17

### New

- Speech input: microphone button and shortcut (`Ctrl+Alt+M`, configurable). Recognition with
  whisper.cpp (download in the settings, any `ggml-*.bin` model selectable) or the Windows speech
  recogniser.
- Read aloud: speaker buttons for the input and the translation, voice selectable in the settings.

## 0.4.1 – 2026-11-17

### Changed

- The app is now called **AI Translate** (previously "Turing Translate"). On first start the
  settings, history, runtime and models of the old version are taken over.
- The project documentation on GitHub is in English.

## 0.4.0 – 2026-11-17

### New

- Paste screenshots (Ctrl+V or "Paste"): the text is read with the Windows text recogniser and
  translated.
- Interface in German, English, Spanish and French, switchable in the title bar and in the settings.
- Lithuanian and Latvian as translation languages.
- Single words and word lists get several meanings with example sentences.
- OpenRouter as its own provider with model list, search, "free only" filter and cost display.
- Model choice next to the provider in the main window.
- Short explanations (i icons) for provider, model, style and other controls.

### Changed

- Settings reordered: languages, local models, online providers, window; with explanatory sentences
  and links for downloading models.
- The history can be scrolled.

## 0.3.0 – 2026-11-13

### New

- Windows installer (per user, no administrator rights) with built-in Python; using the app needs
  neither Node.js nor Rust.
- "Getting started" in the window as long as neither a local model nor a provider is set up.
- Download of the llama.cpp runtime and a small model from within the app, with checksum, resume
  after interruption and progress display. If the connection stalls, the download restarts by itself
  after 90 seconds without progress.

### Changed

- The runtime and models are also searched in the local app data folder.
- If the chosen model size is not available, an available one is chosen.

## 0.2.0 – 2026-11-13

### New

- Online providers: Claude and OpenAI-compatible services by API key, Claude subscription through
  Claude Code, ChatGPT subscription through the Codex CLI. Token and cost display.
- Local models for small, medium and large freely selectable, also via "Browse".
- 24 languages; language packs installable from a file or an address.
- Phrase memory with a vector database (ChromaDB): also finds similarly worded entries and shows
  which entries were used.
- Style choice (neutral, formal, casual, literal) and context across paragraphs.
- Output check with one retry.
- History with search and export (CSV, JSON, Markdown); corrections can be saved as phrases, your
  own phrases exported as a language pack.
- Explain mode, clarifying question for ambiguous text, thorough mode.
- MCP server (`sidecar/mcp_server.py`).
- Test set for translation quality with optional grading by a second model.

### Changed

- Your own phrases now live in the user folder; bundled packs are no longer modified.
- The project's Python environment `.venv` is preferred.

## 0.1.0

- First version: docked window, local translation German ↔ English with phrase book, graphics memory
  freed after every translation.
