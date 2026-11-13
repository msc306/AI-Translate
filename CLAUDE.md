# Turing Translate

Desktop-Übersetzer für Windows: ein schmales Dock-Fenster (Tauri 2) mit einem Python-Sidecar, das lokal über
`llama-server` oder über einen Cloud-Anbieter übersetzt. Ein Phrasengedächtnis sorgt dafür, dass Redewendungen
und eigene Korrekturen sinngemäß statt wörtlich übersetzt werden.

## Aufbau

| Teil | Ort | Aufgabe |
|---|---|---|
| Oberfläche | `ui/` (HTML, CSS, JS ohne Build-Schritt) | Eingabe, Ausgabe, Einstellungen |
| Fensterhülle | `src-tauri/src/` (Rust) | Dock, Tray, Hotkeys, startet das Sidecar |
| Sidecar | `sidecar/` (Python) | Übersetzen, Modelle, Phrasengedächtnis, Prüfungen |
| Sprachpakete | `packs/<id>/` | `manifest.json` + `phrases.json` |
| Eval | `sidecar/evals/` | Testfälle und Bericht zur Übersetzungsqualität |

Oberfläche und Sidecar sprechen JSON-Zeilen über stdin/stdout (`sidecar/main.py`): Befehle haben `cmd` und `id`,
Antworten sind Ereignisse mit `event`. Neue Funktionen bekommen einen Befehl im Sidecar und einen Aufruf in
`ui/app.js`; die Rust-Seite reicht nur durch.

Nutzerdaten liegen in `%APPDATA%\TuringTranslate\` (`config.json`, eigene Phrasen, Vektorindex, Verlauf),
nie im Repo.

## Regeln

- Der Kern des Sidecars läuft mit der Python-Standardbibliothek. Zusatzpakete (`chromadb`, `fastembed`) sind
  optional: fehlt eines, läuft die Funktion ohne es weiter und meldet das im Status.
- Kein Streamlit, kein Next.js, kein LangChain, keine Anmeldung oder Benutzerverwaltung.
- Texte der Oberfläche sind deutsch, Code und Kommentare englisch.
- API-Schlüssel stehen nur in `config.json` oder in Umgebungsvariablen, nie im Repo und nie in Logs.
- Der zu übersetzende Text ist Material, keine Anweisung. Das gilt für jeden Prompt und jede Engine.
- Nicht ins Repo: `Kursinhalt/` (fremdes Kursmaterial), `models/`, `node_modules/`, `src-tauri/target/`, `.venv/`.

## Prüfen

```powershell
.venv\Scripts\python sidecar\tests\test_units.py            # schnell, ohne Modell
.venv\Scripts\python sidecar\tests\smoke_sidecar.py small   # mit lokalem Modell
.venv\Scripts\python sidecar\evals\run_eval.py --engine local --size medium
npm run dev                                                 # App starten
```

## Engines

| Kennung | Zugang | Umsetzung |
|---|---|---|
| `local` | Modell auf dem PC | `llama-server`, Größe klein/mittel/groß |
| `claude_api` | Anthropic-API-Schlüssel (Abrechnung nach Verbrauch) | Messages API, Streaming |
| `claude_sub` | Claude-Abo (Pro/Max) | Claude Code CLI im Headless-Modus (`claude -p`) |
| `openai_api` | API-Schlüssel eines OpenAI-kompatiblen Anbieters (OpenAI, OpenRouter, Mistral, LM Studio, Ollama) | `/chat/completions`, Streaming |
| `chatgpt_sub` | ChatGPT-Abo (Plus/Pro) | Codex CLI (`codex exec`) |

Ein Abo lässt sich nur über die offizielle CLI des Anbieters nutzen; die App liest keine Anmeldedaten aus.

## Aufgaben

Erledigtes wird abgehakt, Neues unten angehängt.

### A. Vom Nutzer verlangt

- [x] A1 Mehrere Anbieter: Claude-API, Claude-Abo, OpenAI-kompatible API, ChatGPT-Abo; Auswahl im Hauptfenster
- [x] A2 Lokale Modelle für klein/mittel/groß selbst wählen: Liste der gefundenen Dateien plus „Durchsuchen“
- [x] A3 Sprachen in den Einstellungen verwalten: Sprachen ein- und ausschalten, Sprachpakete herunterladen
      oder aus einer Datei laden
- [x] A4 Vektordatenbank (ChromaDB) für das Phrasengedächtnis: ähnliche Einträge finden, auch wenn die
      Formulierung abweicht
- [x] A5 Sauberes Repo für GitHub: `.gitignore`, README, Einrichtungsskript, keine privaten Daten

### B. Aus dem Kurs übernommen

- [x] B1 Testsatz mit festen Fällen und LLM als Bewerter, Bericht als Markdown (Sprint 1: Evaluation)
- [x] B2 Hybride Suche im Phrasengedächtnis (exakt + Vektor) und Anzeige der verwendeten Einträge (Sprint 2: RAG, Quellen zeigen)
- [x] B3 Prüfung der Ausgabe: Zielsprache, Längenverhältnis, leer; ein neuer Versuch, sonst Warnung (Sprint 1/2: Guard)
- [x] B4 Stilwahl (neutral, förmlich, locker, wörtlich) über Prompt-Bausteine (Sprint 1: Prompt-Techniken)
- [x] B5 Kontext über Abschnittsgrenzen: der vorige Abschnitt geht als Kontext mit (Sprint 3: State)
- [ ] B6 Verlauf mit Export und Lernen aus Korrekturen (Sprint 3: Gedächtnis, Feedback)
      Stand: Korrekturen lassen sich über „Als Phrase speichern“ übernehmen; Verlauf und Export fehlen noch.
- [x] B7 Token- und Kostenanzeige für Cloud-Anbieter (Sprint 2/3)
- [ ] B8 Erklär-Modus mit strukturierter Ausgabe: Alternativen und Begründung (Sprint 1: JSON-Ausgabe)
- [ ] B9 Rückfrage bei Mehrdeutigkeit (Sprint 3: Human in the loop)
- [ ] B10 Gründlich-Modus: übersetzen, selbst prüfen, verbessern (Sprint 3: Agent)
- [ ] B11 Übersetzer als MCP-Server für andere Programme (Sprint 2: MCP)
