# AI-Translate

**Turing Translate** is a small translator for the Windows desktop that docks to the screen edge.
It translates with a local model on your own graphics card or with an online provider, knows
idioms through a phrase memory, and frees the graphics memory again after every translation.
The interface and the rest of this document are German.

**Turing Translate** ist ein kleiner Übersetzer für den Windows-Desktop, der am Bildschirmrand
andockt wie eine zweite Taskleiste. Er übersetzt mit einem Modell auf der eigenen Grafikkarte oder
über einen Anbieter im Internet.

**Inhalt:** [Was er kann](#was-er-kann) · [Installieren](#installieren) ·
[Voraussetzungen](#voraussetzungen) · [Aus dem Quellcode starten](#aus-dem-quellcode-starten) ·
[Installer bauen](#installer-bauen) · [Bedienung](#bedienung) ·
[Anbieter](#anbieter) · [Sprachpakete](#sprachpakete) ·
[Als MCP-Server nutzen](#als-mcp-server-nutzen) · [Tests](#tests) · [Aufbau](#aufbau)

## Was er kann

- **Lokal oder im Internet übersetzen.** Lokal mit einem GGUF-Modell (klein, mittel, groß – jeweils
  frei wählbar), oder über Claude, OpenRouter bzw. OpenAI-kompatible Dienste.
- **Screenshots übersetzen.** Ein eingefügtes Bild wird mit der Texterkennung von Windows gelesen;
  der erkannte Text landet im Eingabefeld und wird wie getippter Text übersetzt. Das Bild verlässt
  den PC nicht.
- **Abo statt API-Schlüssel.** Ein Claude-Abo (Pro/Max) lässt sich über das Programm Claude Code
  nutzen, ein ChatGPT-Abo über die Codex-CLI. API-Schlüssel funktionieren ebenfalls.
- **Phrasengedächtnis.** Redewendungen werden sinngemäß übersetzt („Ich verstehe nur Bahnhof“ →
  „It's all Greek to me“). Eigene Einträge und Korrekturen werden gespeichert. Eine
  Vektordatenbank (ChromaDB) findet auch Einträge, die nur ähnlich formuliert sind; die Anzeige
  zeigt, welche Einträge in eine Übersetzung eingeflossen sind.
- **Mehrere Sprachen.** 26 Sprachen lassen sich in den Einstellungen einschalten; Sprachpakete mit
  Redewendungen können aus einer Datei oder von einer Adresse geladen werden.
- **Oberfläche in vier Sprachen.** Deutsch, Englisch, Spanisch oder Französisch, wählbar in der
  Titelleiste neben dem Namen oder in den Einstellungen.
- **Stilwahl.** Neutral, förmlich, locker oder wörtlich.
- **Prüfung der Ausgabe.** Leere, unübersetzte oder auffällig kurze/lange Ergebnisse werden einmal
  neu versucht und sonst mit einem Hinweis markiert.
- **Verlauf und Export.** Übersetzungen werden lokal gespeichert, lassen sich durchsuchen und als
  CSV, JSON oder Markdown ausgeben. Wer eine Übersetzung im Ergebnisfeld oder im Verlauf ändert,
  speichert damit eine Korrektur – und kann sie mit einem Klick als Phrase übernehmen, die ab der
  nächsten Übersetzung gilt. Eigene Phrasen lassen sich als Sprachpaket weitergeben.
- **Erklären.** Auf Wunsch begründet das Modell eine Übersetzung, nennt Alternativen und weist auf
  Redewendungen und falsche Freunde hin.
- **Rückfrage bei Mehrdeutigkeit.** Ist ein kurzer Text mehrdeutig („Der Ton war furchtbar“), fragt
  der Übersetzer nach, was gemeint ist (abschaltbar).
- **Gründlich-Modus.** Das Modell prüft seinen Entwurf in einem zweiten Durchgang und verbessert ihn.
- **Für andere Programme nutzbar.** Ein MCP-Server stellt das Übersetzen als Werkzeug bereit.
- **Schonender Umgang mit dem Grafikspeicher.** Vor dem Laden wird geprüft, ob genug frei ist;
  danach wird das Modell wieder entladen.

## Installieren

1. Unter [Releases](https://github.com/msc306/AI-Translate/releases) die Datei
   `Turing.Translate_<Version>_x64-setup.exe` herunterladen und starten. Sie installiert für den
   angemeldeten Benutzer, Administratorrechte sind nicht nötig. Python ist enthalten.
2. Beim ersten Start zeigt das Fenster **Erste Schritte**, solange weder ein lokales Modell noch ein
   Anbieter eingerichtet ist:
   - **Laufzeit und Modell herunterladen** lädt die llama.cpp-Laufzeit (CUDA 12.4, ca. 680 MB) und
     das kleine Modell Gemma 4 E2B (Apache-2.0, ca. 3,3 GB) nach `%LOCALAPPDATA%\TuringTranslate`.
     Jede Datei wird anhand ihrer Prüfsumme kontrolliert; ein abgebrochener Download setzt beim
     nächsten Mal fort; bleibt die Verbindung hängen, startet der Download von selbst neu. Danach
     übersetzt das Programm ohne Internet. Die allererste Übersetzung kann gut eine Minute dauern,
     weil Windows das Modell erstmals von der Platte liest; danach dauert ein Satz wenige Sekunden.
   - Ohne NVIDIA-Grafikkarte, oder wer nichts herunterladen möchte, wählt in den Einstellungen einen
     Anbieter im Internet.
3. Größere Modelle (mittel, groß) lassen sich in den Einstellungen als GGUF-Datei auswählen.

Der Installer ist nicht signiert; Windows SmartScreen fragt deshalb beim ersten Start nach
(„Weitere Informationen“ → „Trotzdem ausführen“). Die Prüfsumme jeder Release-Datei steht in den
Release-Notizen. Das Phrasengedächtnis sucht in der installierten Fassung nach Wortlaut; die
Ähnlichkeitssuche mit ChromaDB gibt es in der Fassung aus dem Quellcode.

## Voraussetzungen

- Windows 10/11 (64 Bit)
- Für lokale Modelle: eine NVIDIA-Grafikkarte mit aktuellem Treiber (für das kleine Modell reichen
  etwa 5 GB Grafikspeicher). Ist [LM Studio](https://lmstudio.ai) installiert, werden dessen
  llama.cpp-Laufzeit und Modelle automatisch gefunden.
- Für die Anbieter im Internet je nach Wahl: ein API-Schlüssel,
  [Claude Code](https://claude.com/claude-code) (angemeldet mit dem Abo) oder die Codex-CLI.
- Nur für den Start aus dem Quellcode: [Node.js](https://nodejs.org), [Rust](https://rustup.rs)
  und [uv](https://docs.astral.sh/uv/).

## Aus dem Quellcode starten

```powershell
git clone https://github.com/msc306/AI-Translate.git
cd AI-Translate
powershell -ExecutionPolicy Bypass -File setup.ps1
npm run dev
```

`setup.ps1` legt die Python-Umgebung `.venv` an, installiert ChromaDB für das Phrasengedächtnis
(mit `-NoMemory` überspringen) und die Node-Pakete. GGUF-Modelle gehören in den Ordner `models\`
oder werden in den Einstellungen über „Durchsuchen“ gewählt.

Beim ersten Start mit Phrasengedächtnis wird einmalig ein kleines Sprachmodell für die Suche
geladen (ca. 120 MB). Danach arbeitet die Suche ohne Internet.

`npm run build` erzeugt `src-tauri\target\release\turing-translate.exe`. Diese Fassung erwartet die
Ordner `sidecar\`, `packs\` und `.venv\` weiterhin im Projektordner.

## Installer bauen

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-installer.ps1
```

Das Skript stellt in `build\bundle` den Sidecar (ohne Tests), die Sprachpakete und das offizielle
Embeddable-Python von python.org zusammen, prüft, dass der Sidecar damit startet, und baut mit
`src-tauri\tauri.bundle.conf.json` einen NSIS-Installer nach
`src-tauri\target\release\bundle\nsis\`.

## Bedienung

- `Strg+Alt+T` blendet das Fenster ein und aus, `Strg+Alt+U` übersetzt den Inhalt der
  Zwischenablage. Das Programm sitzt außerdem im Infobereich der Taskleiste.
- Screenshots: Bildausschnitt mit `Win+Umschalt+S` aufnehmen und mit `Strg+V` einfügen (oder
  „Einfügen“ bzw. `Strg+Alt+U`). Die Texterkennung nutzt die in Windows installierten Sprachen. Fehlt
  die Sprache des Bildes, liest sie mit einer anderen und einzelne Zeichen können falsch sein;
  nachinstallieren lässt sie sich unter Einstellungen → Zeit und Sprache → Sprache und Region.
- Quell- und Zielsprache, Anbieter, Modellgröße und Stil stehen über dem Eingabefeld. Steht die
  Quellsprache auf „automatisch“, wird die Richtung erkannt.
- Das Ergebnis lässt sich direkt im Ergebnisfeld ändern. Die Änderung wird als Korrektur im
  Verlauf gespeichert und lässt sich als Phrase übernehmen.
- In den Einstellungen (Zahnrad) lassen sich Sprachen, lokale Modelle, Anbieter, Fensterplatz und das
  Phrasengedächtnis einrichten. Unter jeder Modellgröße führt ein Knopf zu einer Seite, auf der es ein
  passendes Modell zum Herunterladen gibt.
- Einstellungen, eigene Phrasen und der Verlauf liegen unter `%APPDATA%\TuringTranslate\`.

## Anbieter

| Anbieter | Braucht | Stand |
|---|---|---|
| Lokal | GGUF-Modell, NVIDIA-Grafikkarte | getestet |
| Claude (Abo) | Claude Code, angemeldet | getestet |
| Claude (API-Schlüssel) | Schlüssel oder `ANTHROPIC_API_KEY` | umgesetzt, noch nicht mit echtem Schlüssel geprüft |
| OpenAI-kompatibel | Schlüssel oder `OPENAI_API_KEY`; die Adresse ist einstellbar, damit gehen auch andere Dienste und lokale Server | umgesetzt, noch nicht mit echtem Schlüssel geprüft |
| OpenRouter | Schlüssel oder `OPENROUTER_API_KEY`; Modellliste mit Suche, Preisen und Filter „nur kostenlose“, Kosten je Modell | umgesetzt, Modellliste live geprüft, Übersetzen noch nicht mit echtem Schlüssel geprüft |
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

## Als MCP-Server nutzen

Andere Programme, die das Model Context Protocol sprechen, können den Übersetzer als Werkzeug
verwenden. Für Claude Code zum Beispiel (Pfad anpassen):

```powershell
claude mcp add turing-translate -- C:\Pfad\.venv\Scripts\python.exe C:\Pfad\sidecar\mcp_server.py
```

Werkzeuge: `translate`, `explain_translation`, `list_languages`. Es gelten die Einstellungen und
das Phrasengedächtnis der App; in den Verlauf wird dabei nichts geschrieben.

## Tests

```powershell
.venv\Scripts\python sidecar\tests\test_units.py            # ohne Grafikkarte und Internet
.venv\Scripts\python sidecar\tests\test_units.py --vector   # zusätzlich die Vektordatenbank
.venv\Scripts\python sidecar\tests\smoke_sidecar.py medium  # echte Übersetzungen
.venv\Scripts\python sidecar\tests\live_modes.py medium     # Rückfrage, Gründlich, Erklären
.venv\Scripts\python sidecar\tests\long_text.py medium      # langer Text, Absätze bleiben erhalten
.venv\Scripts\python sidecar\tests\vram_guard.py            # Sperren für Grafikspeicher und Anbieter
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
| `scripts\` | Bau des Installers |

Die Oberfläche spricht mit dem Dienst über JSON-Zeilen; das Protokoll steht am Anfang von
`sidecar\main.py`. Hinweise für die Arbeit am Code stehen in `CLAUDE.md`, die Änderungen je
Version in `CHANGELOG.md`.

## Lizenz

MIT, siehe `LICENSE`.
