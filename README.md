# AI Translate

**AI Translate** is a small translator for the Windows desktop that docks to the screen edge like a
second taskbar. It translates with a model on your own graphics card or through an online provider,
knows idioms through a phrase memory, and frees the graphics memory again after every translation.
The interface is available in German, English, Spanish and French.

**Contents:** [Features](#features) · [Install](#install) · [Requirements](#requirements) ·
[Run from source](#run-from-source) · [Build the installer](#build-the-installer) ·
[Usage](#usage) · [Providers](#providers) · [Language packs](#language-packs) ·
[Use as an MCP server](#use-as-an-mcp-server) · [Tests](#tests) · [Structure](#structure)

## Features

- **Translate locally or online.** Locally with a GGUF model (small, medium, large – each freely
  selectable), or through Claude, OpenRouter or OpenAI-compatible services.
- **Translate screenshots.** A pasted image is read with the Windows text recogniser; the recognised
  text lands in the input field and is translated like typed text. The image never leaves the PC.
- **Subscription instead of an API key.** A Claude subscription (Pro/Max) can be used through Claude
  Code, a ChatGPT subscription through the Codex CLI. API keys work as well.
- **Phrase memory.** Idioms are translated by meaning ("Ich verstehe nur Bahnhof" → "It's all Greek
  to me"). Your own entries and corrections are kept. A vector database (ChromaDB) also finds entries
  that are only worded similarly; the app shows which entries went into a translation.
- **Many languages.** 26 languages can be switched on in the settings; language packs with idioms can
  be loaded from a file or an address.
- **Interface in four languages.** German, English, Spanish or French, chosen in the title bar next to
  the name or in the settings.
- **Word meanings.** Single words and word lists get several meanings with example sentences.
- **Style.** Neutral, formal, casual or literal.
- **Output check.** Empty, untranslated or strikingly short/long results are retried once and
  otherwise marked with a warning.
- **History and export.** Translations are stored locally, can be searched and exported as CSV, JSON
  or Markdown. Editing a translation in the result field or in the history saves a correction – and
  one click turns it into a phrase that applies from the next translation on. Your own phrases can be
  shared as a language pack.
- **Explain.** On request the model justifies a translation, names alternatives and points out idioms
  and false friends.
- **Clarifying question.** If a short text is ambiguous ("The note was awful"), the translator asks
  what is meant (can be switched off).
- **Thorough mode.** The model reviews its draft in a second pass and improves it.
- **Usable by other programs.** An MCP server offers translation as a tool.
- **Careful with graphics memory.** Before loading, the app checks that enough is free; afterwards
  the model is unloaded again.

## Install

1. Download `AI.Translate_<version>_x64-setup.exe` from
   [Releases](https://github.com/msc306/AI-Translate/releases) and run it. It installs for the
   current user, no administrator rights are needed. Python is included.
2. On first start the window shows **Getting started** as long as neither a local model nor a
   provider is set up:
   - **Download runtime and model** fetches the llama.cpp runtime (CUDA 12.4, about 680 MB) and the
     small model Gemma 4 E2B (Apache-2.0, about 3.3 GB) into `%LOCALAPPDATA%\AITranslate`. Every
     file is verified by its checksum; an interrupted download resumes next time, and a stalled one
     restarts by itself. After that the app translates without internet. The very first translation
     can take a good minute because Windows reads the model from disk for the first time; after that
     a sentence takes a few seconds.
   - Without an NVIDIA graphics card, or if you prefer not to download anything, choose an online
     provider in the settings.
3. Larger models (medium, large) can be chosen as a GGUF file in the settings.

The installer is not signed, so Windows SmartScreen asks on first start ("More info" → "Run
anyway"). The checksum of every release file is listed in the release notes. In the installed
version the phrase memory matches by wording; the similarity search with ChromaDB is available when
running from source.

**Upgrading from "Turing Translate" (0.4.0 and earlier):** the app was renamed. On first start
AI Translate takes over the settings, history, runtime and models of the old version. The old
version can then be uninstalled under Windows Settings → Apps.

## Requirements

- Windows 10/11 (64-bit)
- For local models: an NVIDIA graphics card with a current driver (about 5 GB of graphics memory is
  enough for the small model). If [LM Studio](https://lmstudio.ai) is installed, its llama.cpp
  runtime and models are found automatically.
- For the online providers, depending on the choice: an API key,
  [Claude Code](https://claude.com/claude-code) (signed in with the subscription) or the Codex CLI.
- Only for running from source: [Node.js](https://nodejs.org), [Rust](https://rustup.rs) and
  [uv](https://docs.astral.sh/uv/).

## Run from source

```powershell
git clone https://github.com/msc306/AI-Translate.git
cd AI-Translate
powershell -ExecutionPolicy Bypass -File setup.ps1
npm run dev
```

`setup.ps1` creates the Python environment `.venv`, installs ChromaDB for the phrase memory (skip
with `-NoMemory`) and the Node packages. GGUF models go into the `models\` folder or are chosen in
the settings with "Browse".

On the first start with phrase memory a small embedding model for the search is downloaded once
(about 120 MB). After that the search works offline.

`npm run build` produces `src-tauri\target\release\ai-translate.exe`. This build still expects the
folders `sidecar\`, `packs\` and `.venv\` in the project folder.

## Build the installer

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-installer.ps1
```

The script stages the sidecar (without tests), the language packs and the official embeddable
Python from python.org in `build\bundle`, checks that the sidecar starts with it, and builds an NSIS
installer with `src-tauri\tauri.bundle.conf.json` into `src-tauri\target\release\bundle\nsis\`.

## Usage

- `Ctrl+Alt+T` shows and hides the window, `Ctrl+Alt+U` translates the clipboard. The app also sits
  in the notification area of the taskbar.
- Screenshots: capture an area with `Win+Shift+S` and paste it with `Ctrl+V` (or "Paste" or
  `Ctrl+Alt+U`). Text recognition uses the languages installed in Windows. If the language of the
  image is missing, another one is used and single characters may be wrong; add it under Settings →
  Time & language → Language & region.
- Source and target language, provider, model and style sit above the input field. With the source
  language on "automatic" the direction is detected.
- The result can be edited directly in the result field. The change is stored as a correction in the
  history and can be adopted as a phrase.
- The settings (gear icon) cover languages, local models, providers, window position and the phrase
  memory. Below each model size a button leads to a page where a suitable model can be downloaded.
- Settings, your own phrases and the history are stored in `%APPDATA%\AITranslate\`.

## Providers

| Provider | Needs | Status |
|---|---|---|
| Local | GGUF model, NVIDIA graphics card | tested |
| Claude (subscription) | Claude Code, signed in | tested |
| Claude (API key) | key or `ANTHROPIC_API_KEY` | implemented, not yet checked with a real key |
| OpenAI-compatible | key or `OPENAI_API_KEY`; the address is configurable, so other services and local servers work too | implemented, not yet checked with a real key |
| OpenRouter | key or `OPENROUTER_API_KEY`; model list with search, prices and a "free only" filter, cost per model | implemented, model list checked live, translation not yet checked with a real key |
| ChatGPT (subscription) | Codex CLI, signed in | implemented, not yet checked with a real subscription |

Keys are stored only in `%APPDATA%\AITranslate\config.json` or in an environment variable. With the
online providers the text to be translated leaves the computer.

## Language packs

A pack is a folder or ZIP file with two files:

```text
manifest.json   {"id": "de-fr", "name": "German ↔ French", "version": "1.0.0",
                 "languages": [{"code": "de"}, {"code": "fr"}]}
phrases.json    {"phrases": [{"de": ["Alles in Butter", "Alles im Lot"], "fr": "Tout va bien"}]}
```

Each entry gives one wording or a list of variants per language. Installed packs and your own
entries are stored in `%APPDATA%\AITranslate\`; the bundled pack `packs\de-en` is never changed.

## Use as an MCP server

Programs that speak the Model Context Protocol can use the translator as a tool. For Claude Code,
for example (adjust the path):

```powershell
claude mcp add ai-translate -- C:\path\.venv\Scripts\python.exe C:\path\sidecar\mcp_server.py
```

Tools: `translate`, `explain_translation`, `list_languages`. The app's settings and phrase memory
apply; nothing is written to the history.

## Tests

```powershell
.venv\Scripts\python sidecar\tests\test_units.py            # no graphics card or internet needed
.venv\Scripts\python sidecar\tests\test_units.py --vector   # also the vector database
.venv\Scripts\python sidecar\tests\smoke_sidecar.py medium  # real translations
.venv\Scripts\python sidecar\tests\live_modes.py medium     # clarifying question, thorough, explain
.venv\Scripts\python sidecar\tests\long_text.py medium      # long text, paragraphs are kept
.venv\Scripts\python sidecar\tests\vram_guard.py            # locks for graphics memory and providers
.venv\Scripts\python sidecar\evals\run_eval.py --engine local --size medium --judge claude_sub
```

The last command runs the test set in `sidecar\evals\cases.json` (idioms, formatting, false friends,
injected instructions, style) and optionally lets a second model grade the translations. Reports are
written to `sidecar\evals\results\`.

## Structure

| Folder | Contents |
|---|---|
| `src-tauri\` | window, docking, hotkeys, clipboard (Rust, Tauri 2) |
| `ui\` | interface (HTML, CSS, JavaScript without a build step) |
| `sidecar\` | translation service (Python; the core uses only the standard library) |
| `packs\` | bundled language pack |
| `scripts\` | installer build |

The interface talks to the service in JSON lines; the protocol is described at the top of
`sidecar\main.py`. Notes for working on the code are in `CLAUDE.md` (German), the changes per
version in `CHANGELOG.md`.

## License

MIT, see `LICENSE`.
