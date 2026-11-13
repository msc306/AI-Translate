"""Lokale Uebersetzung mit llama-server (llama.cpp).

Der Server wird pro Uebersetzung gestartet und danach beendet. Nur ein
beendeter Prozess gibt VRAM und RAM garantiert vollstaendig frei.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import socket
import subprocess
import threading
import time
from pathlib import Path

import gpu
import winjob

NO_WINDOW = 0x08000000
LMSTUDIO = Path.home() / ".lmstudio"


class EngineError(Exception):
    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.code = code
        self.extra = extra


def _version_key(path: Path):
    return [int(n) for n in re.findall(r"\d+", path.name.rsplit("-", 1)[-1])]


def find_llama_server(configured: str, app_dir: Path) -> tuple[Path, list[Path]]:
    """Sucht llama-server.exe. Rueckgabe: (exe, zusaetzliche DLL-Suchpfade)."""
    if configured and configured != "auto":
        exe = Path(configured)
        if exe.is_file():
            return exe, []
        raise EngineError("runtime_missing", f"llama-server nicht gefunden: {configured}")

    own = app_dir / "runtime" / "llama-server.exe"
    if own.is_file():
        return own, []

    backends = LMSTUDIO / "extensions" / "backends"
    candidates = sorted(backends.glob("llama.cpp-win-x86_64-nvidia-cuda12-avx2-*"), key=_version_key, reverse=True)
    for folder in candidates:
        exe = folder / "llama-server.exe"
        if not exe.is_file():
            continue
        dll_dirs = []
        try:
            manifest = json.loads((folder / "backend-manifest.json").read_text(encoding="utf-8"))
            for name in manifest.get("vendor_lib_package_names", []):
                vendor = backends / "vendor" / name
                if vendor.is_dir():
                    dll_dirs.append(vendor)
        except (OSError, ValueError):
            pass
        return exe, dll_dirs
    raise EngineError(
        "runtime_missing",
        "Keine llama.cpp-Laufzeit gefunden (weder runtime\\llama-server.exe noch LM Studio).",
    )


def list_models(app_dir: Path) -> list[dict]:
    """Alle GGUF-Sprachmodelle aus LM Studio und dem models-Ordner der App."""
    found = []
    for root in (LMSTUDIO / "models", app_dir / "models"):
        if not root.is_dir():
            continue
        for file in root.rglob("*.gguf"):
            if file.name.lower().startswith("mmproj") or "embed" in file.name.lower():
                continue
            found.append({"path": str(file), "name": file.stem, "size_mb": round(file.stat().st_size / 2**20)})
    return sorted(found, key=lambda m: m["size_mb"])


def required_vram_mb(model_path: Path, context_tokens: int) -> int:
    """Grobe Schaetzung: Gewichte + Kontextpuffer + Rechenpuffer."""
    weights = model_path.stat().st_size / 2**20
    return int(weights * 1.08 + context_tokens * 0.12 + 600)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LlamaServer:
    """Ein laufender llama-server-Prozess mit genau einem geladenen Modell."""

    def __init__(self, exe: Path, dll_dirs: list[Path], model_path: Path, context_tokens: int, log_file: Path):
        self.model_path = model_path
        self.port = _free_port()
        env = os.environ.copy()
        env["PATH"] = os.pathsep.join([*(str(d) for d in dll_dirs), str(exe.parent), env.get("PATH", "")])
        log_file.parent.mkdir(parents=True, exist_ok=True)
        self._log = open(log_file, "w", encoding="utf-8", errors="replace")
        self.proc = subprocess.Popen(
            [
                str(exe),
                "-m", str(model_path),
                "--host", "127.0.0.1",
                "--port", str(self.port),
                "-ngl", "999",
                "-c", str(context_tokens),
                "-np", "1",
                "--no-webui",
                "--offline",
                "--reasoning", "off",
                "--cache-ram", "0",
            ],
            stdin=subprocess.DEVNULL,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=NO_WINDOW,
        )
        winjob.bind_to_parent(self.proc)

    def wait_ready(self, cancel: threading.Event, timeout: float = 180.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cancel.is_set():
                raise EngineError("cancelled", "Abgebrochen.")
            if self.proc.poll() is not None:
                raise EngineError("load_failed", f"Modell konnte nicht geladen werden (Exit {self.proc.returncode}).")
            try:
                conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
                conn.request("GET", "/health")
                ok = conn.getresponse().status == 200
                conn.close()
                if ok:
                    return
            except OSError:
                pass
            time.sleep(0.15)
        raise EngineError("load_failed", "Zeitueberschreitung beim Laden des Modells.")

    def chat_stream(self, messages: list[dict], max_tokens: int, cancel: threading.Event):
        """Generator ueber Textstuecke der Antwort."""
        body = json.dumps(
            {
                "messages": messages,
                "stream": True,
                "temperature": 0.2,
                "top_p": 0.9,
                "max_tokens": max_tokens,
                "cache_prompt": False,
            }
        )
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=300)
        try:
            conn.request("POST", "/v1/chat/completions", body=body.encode("utf-8"),
                         headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            if response.status != 200:
                detail = response.read().decode("utf-8", "replace")[:300]
                raise EngineError("generation_failed", f"llama-server meldet {response.status}: {detail}")
            for raw in response:
                if cancel.is_set():
                    raise EngineError("cancelled", "Abgebrochen.")
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    delta = json.loads(payload)["choices"][0].get("delta", {})
                except (ValueError, KeyError, IndexError):
                    continue
                text = delta.get("content")
                if text:
                    yield text
        finally:
            conn.close()

    def stop(self) -> None:
        """Beendet den Prozess und wartet, bis er wirklich weg ist."""
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        try:
            self._log.close()
        except OSError:
            pass


def wait_vram_released(before_free_mb: int | None, gpu_index: int, timeout: float = 3.0) -> dict | None:
    """Wartet kurz, bis der Treiber den freigegebenen Speicher meldet."""
    deadline = time.monotonic() + timeout
    state = gpu.vram_mb(gpu_index)
    while state and before_free_mb is not None and state["free"] < before_free_mb - 300 and time.monotonic() < deadline:
        time.sleep(0.2)
        state = gpu.vram_mb(gpu_index)
    return state
