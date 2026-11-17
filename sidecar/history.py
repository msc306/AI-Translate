"""Translation history: the last translations, the user's corrections, and export."""
import csv
import json
import threading
import time
import uuid
from pathlib import Path

from i18n import tr

FORMATS = ("csv", "json", "md")
FIELDS = ("time", "source", "target", "engine", "model", "style", "source_text", "output", "corrected")


class History:
    def __init__(self, file: Path, limit: int = 500):
        self.file = file
        self.limit = limit
        self._lock = threading.Lock()
        self.entries = []  # oldest first
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            self.entries = [e for e in data if isinstance(e, dict) and e.get("id")]
        except (OSError, ValueError):
            pass

    def _store(self) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.file.with_suffix(".tmp")
        temp.write_text(json.dumps(self.entries, ensure_ascii=False), encoding="utf-8")
        temp.replace(self.file)

    def add(self, limit: int | None = None, **fields) -> str:
        entry = {"id": uuid.uuid4().hex[:12], "time": time.strftime("%Y-%m-%d %H:%M:%S"), "corrected": "", **fields}
        with self._lock:
            self.entries.append(entry)
            del self.entries[:-(limit or self.limit)]
            self._store()
        return entry["id"]

    def items(self, query: str = "", corrected_only: bool = False, limit: int = 200) -> list[dict]:
        """Newest first."""
        needle = query.strip().lower()
        rows = []
        for entry in reversed(self.entries):
            if corrected_only and not entry.get("corrected"):
                continue
            if needle and not any(needle in (entry.get(k) or "").lower()
                                  for k in ("source_text", "output", "corrected")):
                continue
            rows.append(entry)
            if len(rows) >= limit:
                break
        return rows

    def get(self, entry_id: str) -> dict | None:
        return next((e for e in self.entries if e["id"] == entry_id), None)

    def correct(self, entry_id: str, text: str) -> bool:
        """Store the user's corrected translation ('' when it equals the original output)."""
        with self._lock:
            entry = self.get(entry_id)
            if not entry:
                return False
            text = text.strip()
            entry["corrected"] = "" if text == (entry.get("output") or "").strip() else text
            self._store()
        return True

    def delete(self, entry_id: str) -> None:
        with self._lock:
            self.entries = [e for e in self.entries if e["id"] != entry_id]
            self._store()

    def clear(self) -> None:
        with self._lock:
            self.entries = []
            self._store()

    def export(self, path: Path, fmt: str, corrected_only: bool = False) -> int:
        if fmt not in FORMATS:
            raise ValueError(tr("Unbekanntes Format: {fmt}", fmt=fmt))
        rows = self.items(corrected_only=corrected_only, limit=self.limit)
        rows = [{k: e.get(k) or "" for k in FIELDS} for e in rows]
        if fmt == "json":
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        elif fmt == "csv":
            # utf-8-sig and semicolons so that a German Excel opens the file correctly
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter=";")
                writer.writeheader()
                writer.writerows(rows)
        else:
            def cell(value):
                return value.replace("|", "\\|").replace("\n", "<br>")
            columns = (tr("Zeit"), tr("Richtung"), tr("Anbieter"), tr("Ausgangstext"), tr("Übersetzung"),
                       tr("Korrektur"))
            lines = ["# " + tr("AI Translate: Verlauf"), "",
                     "| " + " | ".join(columns) + " |",
                     "|---|---|---|---|---|---|"]
            lines += ["| " + " | ".join(cell(c) for c in (
                r["time"], f"{r['source']} → {r['target']}", r["engine"],
                r["source_text"], r["output"], r["corrected"])) + " |" for r in rows]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return len(rows)
