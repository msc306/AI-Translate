# Changelog

Alle nennenswerten Änderungen an diesem Projekt.

## 0.3.0 – 2026-11-13

### Neu

- Installer für Windows (per Benutzer, ohne Administratorrechte) mit eingebautem Python; wer das
  Programm nur nutzen will, braucht weder Node.js noch Rust.
- „Erste Schritte“ im Fenster, solange weder ein lokales Modell noch ein Anbieter eingerichtet ist.
- Download der llama.cpp-Laufzeit und eines kleinen Modells aus dem Programm heraus, mit
  Prüfsumme, Fortsetzen nach Abbruch und Fortschrittsanzeige. Hängt die Verbindung, startet der
  Download nach 90 Sekunden ohne Fortschritt selbst neu.

### Geändert

- Laufzeit und Modelle werden zusätzlich in `%LOCALAPPDATA%\TuringTranslate` gesucht.
- Ist die gewählte Modellgröße nicht vorhanden, wird eine vorhandene gewählt.

## 0.2.0 – 2026-11-13

### Neu

- Anbieter im Internet: Claude und OpenAI-kompatible Dienste per API-Schlüssel, Claude-Abo über
  Claude Code, ChatGPT-Abo über die Codex-CLI. Anzeige von Tokens und Kosten.
- Lokale Modelle für klein, mittel und groß frei wählbar, auch per „Durchsuchen“.
- 24 Sprachen, Sprachpakete aus Datei oder Adresse installierbar.
- Phrasengedächtnis mit Vektordatenbank (ChromaDB): findet auch ähnlich formulierte Einträge und
  zeigt, welche Einträge verwendet wurden.
- Stilwahl (neutral, förmlich, locker, wörtlich) und Zusammenhang über Abschnitte hinweg.
- Prüfung der Ausgabe mit einem erneuten Versuch.
- Verlauf mit Suche und Export (CSV, JSON, Markdown); Korrekturen lassen sich als Phrase speichern,
  eigene Phrasen als Sprachpaket exportieren.
- Erklär-Modus, Rückfrage bei Mehrdeutigkeit, Gründlich-Modus.
- MCP-Server (`sidecar/mcp_server.py`).
- Testset für die Übersetzungsqualität mit optionaler Bewertung durch ein zweites Modell.

### Geändert

- Eigene Phrasen liegen jetzt im Benutzerordner; mitgelieferte Pakete werden nicht mehr verändert.
- Die Python-Umgebung `.venv` des Projekts wird bevorzugt.

## 0.1.0

- Erste Fassung: angedocktes Fenster, lokale Übersetzung Deutsch ↔ Englisch mit Phrasenbuch,
  Freigabe des Grafikspeichers nach jeder Übersetzung.
