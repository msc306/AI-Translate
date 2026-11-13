# Turing Translate

A small translator for the Windows desktop that docks to the screen edge. It translates with a
local model on your own graphics card or with an online provider, knows idioms through a phrase
memory, and frees the graphics memory again after every translation. The interface is German.

Ein kleiner Übersetzer für den Windows-Desktop, der am Bildschirmrand andockt.

## Was er kann

- **Lokal oder im Internet übersetzen.** Lokal mit einem GGUF-Modell (klein, mittel, groß – jeweils
  frei wählbar), oder über Claude bzw. OpenAI-kompatible Dienste.
- **Abo statt API-Schlüssel.** Ein Claude-Abo (Pro/Max) lässt sich über das Programm Claude Code
  nutzen, ein ChatGPT-Abo über die Codex-CLI. API-Schlüssel funktionieren ebenfalls.
- **Phrasengedächtnis.** Redewendungen werden sinngemäß übersetzt („Ich verstehe nur Bahnhof“ →
  „It's all Greek to me“). Eigene Einträge und Korrekturen werden gespeichert. Eine
  Vektordatenbank (ChromaDB) findet auch Einträge, die nur ähnlich formuliert sind; die Anzeige
  zeigt, welche Einträge in eine Übersetzung eingeflossen sind.
- **Mehrere Sprachen.** 24 Sprachen lassen sich in den Einstellungen einschalten; Sprachpakete mit
  Redewendungen können aus einer Datei oder von einer Adresse geladen werden.
- **Stilwahl.** Neutral, förmlich, locker oder wörtlich.
- **Prüfung der Ausgabe.** Leere, unübersetzte oder auffällig kurze/lange Ergebnisse werden einmal
  neu versucht und sonst mit einem Hinweis markiert.
- **Schonender Umgang mit dem Grafikspeicher.** Vor dem Laden wird geprüft, ob genug frei ist;
  danach wird das Modell wieder entladen.

## Voraussetzungen

- Windows 10/11
- [Node.js](https://nodejs.org), [Rust](https://rustup.rs) und [uv](https://docs.astral.sh/uv/)
- Für lokale Modelle: eine NVIDIA-Grafikkarte und `llama-server.exe` von
  [llama.cpp](https://github.com/ggml-org/llama.cpp). Ist [LM Studio](https://lmstudio.ai)
  installiert, werden dessen llama.cpp und dessen Modelle automatisch gefunden. Sonst
  `llama-server.exe` nach `runtime\` legen oder den Pfad in der Konfiguration angeben.
- Für die Anbieter im Internet je nach Wahl: ein API-Schlüssel,
  [Claude Code](https://claude.com/claude-code) (angemeldet mit dem Abo) oder die Codex-CLI.

## Einrichten und starten

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
npm run dev
```

`setup.ps1` legt die Python-Umgebung `.venv` an, installiert ChromaDB für das Phrasengedächtnis
(mit `-NoMemory` überspringen) und die Node-Pakete. GGUF-Modelle gehören in den Ordner `models\`
oder werden in den Einstellungen über „Durchsuchen“ gewählt.

Beim ersten Start mit Phrasengedächtnis wird einmalig ein kleines Sprachmodell für die Suche
geladen (ca. 120 MB). Danach arbeitet die Suche ohne Internet.

## Anbieter

| Anbieter | Braucht | Stand |
|---|---|---|
| Lokal | GGUF-Modell, NVIDIA-Grafikkarte | getestet |
| Claude (Abo) | Claude Code, angemeldet | getestet |
| Claude (API-Schlüssel) | Schlüssel oder `ANTHROPIC_API_KEY` | umgesetzt |
| OpenAI-kompatibel | Schlüssel oder `OPENAI_API_KEY`; die Adresse ist einstellbar, damit gehen auch andere Dienste und lokale Server | umgesetzt |
| ChatGPT (Abo) | Codex-CLI, angemeldet | umgesetzt, noch nicht mit echtem Abo geprüft |

Schlüssel liegen nur in `%APPDATA%\TuringTranslate\config.json` oder in einer Umgebungsvariable.
Bei den Anbietern im Internet verlässt der zu übersetzende Text den Rechner.

## Sprachpakete

Ein Paket ist ein Ordner oder eine ZIP-Datei mit zwei Dateien:

```text
manifest.json   {"id": "de-fr", "name": "Deutsch ↔ Französisch", "version": "1.0.0",
                 "languages": [{"code": "de"}, {"code": "fr"}]}
phrases.json    {"phrases": [{"de": ["Alles in Butter", "Alles im Lot"], "fr": "Tout va bien"}]}
```

Jeder Eintrag nennt pro Sprache eine Formulierung oder eine Liste von Varianten. Installierte
Pakete und eigene Einträge liegen unter `%APPDATA%\TuringTranslate\`; das mitgelieferte Paket
`packs\de-en` wird nie verändert.

## Tests

```powershell
.venv\Scripts\python sidecar\tests\test_units.py            # ohne Grafikkarte und Internet
.venv\Scripts\python sidecar\tests\test_units.py --vector   # zusätzlich die Vektordatenbank
.venv\Scripts\python sidecar\tests\smoke_sidecar.py medium  # echte Übersetzungen
.venv\Scripts\python sidecar\evals\run_eval.py --engine local --size medium --judge claude_sub
```

Der letzte Befehl lässt das Testset in `sidecar\evals\cases.json` laufen (Redewendungen,
Formatierung, falsche Freunde, eingeschleuste Befehle, Stil) und optional ein zweites Modell die
Übersetzungen bewerten. Die Berichte landen in `sidecar\evals\results\`.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `src-tauri\` | Fenster, Andocken, Tastenkürzel, Zwischenablage (Rust, Tauri 2) |
| `ui\` | Oberfläche (HTML, CSS, JavaScript ohne Build-Schritt) |
| `sidecar\` | Übersetzungsdienst (Python; der Kern nutzt nur die Standardbibliothek) |
| `packs\` | mitgeliefertes Sprachpaket |

Die Oberfläche spricht mit dem Dienst über JSON-Zeilen; das Protokoll steht am Anfang von
`sidecar\main.py`. Hinweise für die Arbeit am Code stehen in `CLAUDE.md`.

## Lizenz

MIT, siehe `LICENSE`.
