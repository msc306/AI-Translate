"""Local translation with llama-server (llama.cpp).

The server is started per translation and stopped afterwards. Only a
stopped process guarantees that VRAM and RAM are fully released.
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

import winjob
from i18n import tr

NO_WINDOW = 0x08000000


def lmstudio_dir() -> Path:
    return Path(os.environ.get("AI_TRANSLATE_LMSTUDIO") or Path.home() / ".lmstudio")


def data_dir() -> Path:
    """Folder for the downloaded runtime and models: large files, kept out of the roaming profile."""
    override = os.environ.get("AI_TRANSLATE_DATA")
    if override:
        return Path(override)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "AITranslate"


class EngineError(Exception):
    def __init__(self, code: str, message: str, **extra):
        super().__init__(message)
        self.code = code
        self.extra = extra


def _version_key(path: Path):
    return [int(n) for n in re.findall(r"\d+", path.name.rsplit("-", 1)[-1])]


# Own runtime folders and LM Studio backend folders per llama.cpp backend, in the order tried.
RUNTIME_FOLDERS = {"cuda": ["runtime"], "vulkan": ["runtime-vulkan"], "cpu": ["runtime-cpu"]}
LMSTUDIO_BACKENDS = {
    "cuda": ["llama.cpp-win-x86_64-nvidia-cuda12-avx2-*"],
    "vulkan": ["llama.cpp-win-x86_64-vulkan-avx2-*"],
    "cpu": ["llama.cpp-win-x86_64-avx2-*"],
}


def find_llama_server(configured: str, app_dir: Path, backend: str = "cuda") -> tuple[Path, list[Path]]:
    """Searches for llama-server.exe for a backend (cuda, vulkan, cpu).

    Returns: (exe, additional DLL search paths). The processor backend also accepts any GPU build,
    since those run on the processor too when no layer is offloaded.
    """
    if configured and configured != "auto":
        exe = Path(configured)
        if exe.is_file():
            return exe, []
        raise EngineError("runtime_missing", tr("llama-server nicht gefunden: {path}", path=configured))

    order = [backend] + (["vulkan", "cuda"] if backend == "cpu" else [])
    for kind in order:
        for name in RUNTIME_FOLDERS.get(kind, []):
            for folder in (app_dir / name, data_dir() / name):
                own = folder / "llama-server.exe"
                if own.is_file():
                    return own, []
        found = _lmstudio_server(kind)
        if found:
            return found
    raise EngineError(
        "runtime_missing",
        tr("Keine llama.cpp-Laufzeit gefunden. Sie lässt sich in den Einstellungen herunterladen."),
    )


def _lmstudio_server(backend: str) -> tuple[Path, list[Path]] | None:
    """llama-server from LM Studio's newest matching backend, with its vendor DLL folders."""
    backends = lmstudio_dir() / "extensions" / "backends"
    candidates = []
    for pattern in LMSTUDIO_BACKENDS.get(backend, []):
        candidates += backends.glob(pattern)
    candidates.sort(key=_version_key, reverse=True)
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
    return None


def _server_env(exe: Path, dll_dirs: list[Path]) -> dict:
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([*(str(d) for d in dll_dirs), str(exe.parent), env.get("PATH", "")])
    return env


_DEVICE_LINE = re.compile(r"^\s*(Vulkan\d+):\s*(.+?)\s*\(")


def vulkan_device(exe: Path, dll_dirs: list[Path], card_name: str) -> str | None:
    """llama.cpp's name ("Vulkan1") of the card called `card_name`, or None if not listed.

    Vulkan numbers cards in its own order, which need not match Windows' order, so the names decide.
    """
    try:
        out = subprocess.run(
            [str(exe), "--list-devices"], stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30, env=_server_env(exe, dll_dirs),
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    wanted = re.sub(r"\W+", "", card_name.lower())
    for line in (out.stdout + out.stderr).splitlines():
        match = _DEVICE_LINE.match(line)
        if match and re.sub(r"\W+", "", match.group(2).lower()) == wanted:
            return match.group(1)
    return None


def device_args(backend: str, device: str | None = None) -> list[str]:
    """llama-server arguments that put the model on the chosen hardware."""
    if backend == "cpu":
        return ["-ngl", "0", "--device", "none"]
    args = ["-ngl", "999"]
    if device:
        args += ["--device", device]
    return args


def list_models(app_dir: Path) -> list[dict]:
    """All GGUF language models from LM Studio, the app's models folder and the download folder."""
    found = []
    for root in (lmstudio_dir() / "models", app_dir / "models", data_dir() / "models"):
        if not root.is_dir():
            continue
        for file in root.rglob("*.gguf"):
            if file.name.lower().startswith("mmproj") or "embed" in file.name.lower():
                continue
            found.append({"path": str(file), "name": file.stem, "size_mb": round(file.stat().st_size / 2**20)})
    return sorted(found, key=lambda m: m["size_mb"])


def required_vram_mb(model_path: Path, context_tokens: int) -> int:
    """Rough estimate: weights + context buffer + compute buffer."""
    weights = model_path.stat().st_size / 2**20
    return int(weights * 1.08 + context_tokens * 0.12 + 600)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LlamaServer:
    """A running llama-server process with exactly one loaded model."""

    def __init__(self, exe: Path, dll_dirs: list[Path], model_path: Path, context_tokens: int, log_file: Path,
                 device: list[str] | None = None):
        self.model_path = model_path
        self.port = _free_port()
        env = _server_env(exe, dll_dirs)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        self._log = open(log_file, "w", encoding="utf-8", errors="replace")
        self.proc = subprocess.Popen(
            [
                str(exe),
                "-m", str(model_path),
                "--host", "127.0.0.1",
                "--port", str(self.port),
                *(device or ["-ngl", "999"]),
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
                raise EngineError("cancelled", tr("Abgebrochen."))
            if self.proc.poll() is not None:
                raise EngineError("load_failed", tr("Modell konnte nicht geladen werden (Exit {code}).",
                                                     code=self.proc.returncode))
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
        raise EngineError("load_failed", tr("Zeitueberschreitung beim Laden des Modells."))

    def chat_stream(self, messages: list[dict], max_tokens: int, cancel: threading.Event):
        """Generator over text pieces of the response."""
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
                raise EngineError("generation_failed", tr("llama-server meldet {status}: {detail}",
                                                           status=response.status, detail=detail))
            for raw in response:
                if cancel.is_set():
                    raise EngineError("cancelled", tr("Abgebrochen."))
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
        """Terminates the process and waits until it is really gone."""
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


def wait_vram_released(before_free_mb: int | None, query, timeout: float = 3.0) -> dict | None:
    """Waits briefly until the driver reports the released memory. `query()` returns the VRAM state."""
    deadline = time.monotonic() + timeout
    state = query()
    while state and before_free_mb is not None and state["free"] < before_free_mb - 300 and time.monotonic() < deadline:
        time.sleep(0.2)
        state = query()
    return state
