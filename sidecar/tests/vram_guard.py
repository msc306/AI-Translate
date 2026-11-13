"""Prueft die VRAM-Sperre und die API-Sperre.

1. Reserve groesser als der Grafikspeicher -> vram_insufficient, es wird nichts geladen.
2. engine "claude_api" ohne Freischaltung -> engine_disabled, es wird nichts gesendet.

Aufruf:  python sidecar/tests/vram_guard.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]


def llama_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq llama-server.exe"], capture_output=True, text=True,
                         encoding="oem", errors="replace", stdin=subprocess.DEVNULL).stdout
    return "llama-server.exe" in out


def main() -> None:
    config = Path(tempfile.mkdtemp()) / "config.json"
    config.write_text(json.dumps({"engine": {"vram_reserve_mb": 999999}}), encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "sidecar" / "main.py"), "--app-dir", str(ROOT), "--config", str(config)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8",
    )
    proc.stdout.readline()

    def run(request: dict) -> dict:
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()
        for line in proc.stdout:
            event = json.loads(line)
            if event.get("id") == request["id"] and event["event"] in ("done", "error"):
                return event
        return {}

    text = "Das ist ein Satz, der nicht im Phrasenbuch steht."
    a = run({"id": 1, "cmd": "translate", "text": text, "size": "small"})
    print("VRAM-Sperre:", {k: a.get(k) for k in ("event", "code", "free_mb", "need_mb", "reserve_mb")}, "| llama-server laeuft:", llama_running())
    b = run({"id": 2, "cmd": "translate", "text": text, "engine": "claude_api"})
    print("API-Sperre:", {k: b.get(k) for k in ("event", "code", "message")})
    proc.stdin.write(json.dumps({"id": 3, "cmd": "shutdown"}) + "\n")
    proc.stdin.flush()
    proc.wait(timeout=30)


if __name__ == "__main__":
    main()
