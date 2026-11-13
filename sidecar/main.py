"""Turing Translate sidecar: JSON lines on stdin/stdout, one request per line.

Requests carry "cmd" and "id"; every answer repeats the id and has an "event".
The core uses the standard library only. ChromaDB (semantic phrase search) is optional.
"""
import argparse
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import checks
import gpu
import languages
import local_engine
import phrases
import prompting
import providers
import textutil
from local_engine import EngineError
from vector_index import VectorIndex

_out_lock = threading.Lock()


def emit(message: dict) -> None:
    with _out_lock:
        sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        sys.stdout.flush()


DEFAULT_CONFIG = {
    "engine": {
        "default": "local",
        "model": "medium",
        "models": {"small": "auto", "medium": "auto", "large": "auto"},
        "vram_reserve_mb": 2048,
        "keep_loaded_seconds": 0,
        "context_tokens": 4096,
        "gpu_index": 0,
        "llama_server": "auto",
    },
    "providers": {
        "claude_api": {"enabled": False, "model": "claude-haiku-5-5", "effort": "low",
                       "key": "", "key_env": "ANTHROPIC_API_KEY"},
        "claude_sub": {"enabled": False, "model": "haiku", "command": "claude"},
        "openai_api": {"enabled": False, "base_url": "https://api.openai.com/v1", "model": "",
                       "key": "", "key_env": "OPENAI_API_KEY"},
        "chatgpt_sub": {"enabled": False, "model": "", "command": "codex"},
    },
    "languages": {"enabled": ["de", "en"]},
    "style": "neutral",
    "memory": {"vector": True, "min_similarity": 0.7, "max_hints": 3},
    "checks": {"enabled": True, "retry": True},
    "packs": {"index_url": ""},
}

MODEL_PREFERENCES = {
    "small": ["gemma-4-e2b", "gemma-4-e4b", "gemma-3-4b"],
    "medium": ["gemma-4-12b", "gemma-4-e4b", "gemma-3-12b"],
    "large": ["gemma-4-26b", "gemma-3-27b", "qwen3.8-27b"],
}
SIZES = ("small", "medium", "large")
CONTEXT_CHARS = 600


def deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        merged[key] = deep_merge(base[key], value) if isinstance(value, dict) and isinstance(base.get(key), dict) else value
    return merged


def migrate(stored: dict) -> dict:
    """Old configs kept the Claude API settings under engine.api."""
    old = (stored.get("engine") or {}).pop("api", None) if isinstance(stored.get("engine"), dict) else None
    if isinstance(old, dict):
        target = stored.setdefault("providers", {}).setdefault("claude_api", {})
        for key, value in old.items():
            target.setdefault(key, value)
    return stored


class Sidecar:
    def __init__(self, app_dir: Path, config_path: Path):
        self.app_dir = app_dir
        self.config_path = config_path
        self.user_dir = config_path.parent
        self.book = phrases.PhraseBook(self._load_packs(), self.user_dir / "phrases.json")
        self.index = VectorIndex(self.user_dir / "memory")
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self.server: local_engine.LlamaServer | None = None
        self.server_lock = threading.Lock()
        self.unload_timer: threading.Timer | None = None
        self.sync_index()

    def _load_packs(self):
        return phrases.load_packs((self.app_dir / "packs", "app"), (self.user_dir / "packs", "user"))

    def sync_index(self) -> None:
        if self.config()["memory"].get("vector"):
            self.index.sync(self.book.documents())

    # ---------- configuration ----------
    def _stored(self) -> dict:
        try:
            return migrate(json.loads(self.config_path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return {}

    def config(self) -> dict:
        cfg = deep_merge(DEFAULT_CONFIG, self._stored())
        enabled = [c for c in cfg["languages"].get("enabled") or [] if c in languages.CATALOG]
        cfg["languages"]["enabled"] = list(dict.fromkeys(enabled)) if len(set(enabled)) >= 2 else ["de", "en"]
        return cfg

    def save_config(self, patch: dict) -> dict:
        stored = deep_merge(self._stored(), patch)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.config()

    def public_config(self) -> dict:
        """The config for the UI: stored keys are replaced by a flag."""
        cfg = self.config()
        for provider in cfg["providers"].values():
            if "key" in provider:
                provider["key_set"] = bool(provider["key"])
                provider["key_from_env"] = bool(os.environ.get(provider.get("key_env") or "", ""))
                provider["key"] = ""
        return cfg

    def resolve_model(self, size: str, engine_cfg: dict) -> Path:
        configured = engine_cfg["models"].get(size, "auto")
        if configured and configured != "auto":
            path = Path(configured)
            if path.is_file():
                return path
            raise EngineError("model_missing", f"Modelldatei fehlt: {configured}", size=size)
        available = local_engine.list_models(self.app_dir)
        for needle in MODEL_PREFERENCES.get(size, []):
            for model in available:
                if needle in model["name"].lower():
                    return Path(model["path"])
        raise EngineError("model_missing", f"Kein Modell für die Größe '{size}' gefunden. In den Einstellungen "
                                           "lässt sich eine Modelldatei auswählen.", size=size)

    # ---------- status ----------
    def status(self) -> dict:
        full = self.config()
        cfg = full["engine"]
        presets = {}
        for size in SIZES:
            try:
                path = self.resolve_model(size, cfg)
                presets[size] = {
                    "path": str(path),
                    "name": path.stem,
                    "auto": cfg["models"].get(size, "auto") in ("", "auto"),
                    "size_mb": round(path.stat().st_size / 2**20),
                    "need_mb": local_engine.required_vram_mb(path, cfg["context_tokens"]),
                }
            except EngineError as err:
                presets[size] = {"missing": True, "message": str(err)}
        try:
            exe, _ = local_engine.find_llama_server(cfg["llama_server"], self.app_dir)
            runtime = str(exe)
        except EngineError as err:
            runtime = None
            presets["runtime_error"] = str(err)

        models = local_engine.list_models(self.app_dir)
        known = {m["path"] for m in models}
        for size in SIZES:  # files picked via "Durchsuchen" may live anywhere
            chosen = cfg["models"].get(size)
            if chosen and chosen != "auto" and chosen not in known and Path(chosen).is_file():
                path = Path(chosen)
                models.append({"path": chosen, "name": path.stem, "size_mb": round(path.stat().st_size / 2**20)})
                known.add(chosen)
        for model in models:
            model["need_mb"] = local_engine.required_vram_mb(Path(model["path"]), cfg["context_tokens"])

        return {
            "vram": gpu.vram_mb(cfg["gpu_index"]),
            "presets": presets,
            "models": models,
            "runtime": runtime,
            "loaded": str(self.server.model_path) if self.server else None,
            "engines": providers.availability(full["providers"]),
            "languages": {
                "enabled": full["languages"]["enabled"],
                "catalog": [{"code": code, "label": languages.label(code), "name": languages.name(code),
                             "phrases": len(self.book._index.get(code, {}))}
                            for code in languages.CATALOG],
            },
            "styles": [{"id": key, "label": value[0]} for key, value in prompting.STYLES.items()],
            "packs": [pack.info() for pack in self.book.packs.values()],
            "memory": self.index.info() if full["memory"].get("vector") else {"state": "off", "count": 0, "error": ""},
            "config": self.public_config(),
        }

    # ---------- model lifecycle ----------
    def unload(self) -> None:
        with self.server_lock:
            if self.unload_timer:
                self.unload_timer.cancel()
                self.unload_timer = None
            if self.server:
                self.server.stop()
                self.server = None

    def _ensure_server(self, req_id, model_path: Path, cfg: dict) -> tuple[local_engine.LlamaServer, float]:
        """Load the model if enough VRAM is free. Returns (server, load time in seconds)."""
        with self.server_lock:
            if self.unload_timer:
                self.unload_timer.cancel()
                self.unload_timer = None
            if self.server and self.server.model_path == model_path and self.server.proc.poll() is None:
                return self.server, 0.0
            if self.server:
                self.server.stop()
                self.server = None

            emit({"id": req_id, "event": "status", "stage": "vram_check"})
            state = gpu.vram_mb(cfg["gpu_index"])
            if state is None:
                raise EngineError("no_gpu", "Keine NVIDIA-Grafikkarte abfragbar (nvidia-smi).")
            need = local_engine.required_vram_mb(model_path, cfg["context_tokens"])
            available = state["free"] - cfg["vram_reserve_mb"]
            if available < need:
                raise EngineError(
                    "vram_insufficient",
                    f"Zu wenig freier VRAM: {state['free']} MB frei, benötigt werden {need} MB "
                    f"plus {cfg['vram_reserve_mb']} MB Reserve.",
                    free_mb=state["free"], need_mb=need, reserve_mb=cfg["vram_reserve_mb"],
                )

            exe, dll_dirs = local_engine.find_llama_server(cfg["llama_server"], self.app_dir)
            emit({"id": req_id, "event": "status", "stage": "loading", "model": model_path.stem})
            started = time.monotonic()
            server = local_engine.LlamaServer(
                exe, dll_dirs, model_path, cfg["context_tokens"], self.user_dir / "llama-server.log"
            )
            self.server = server
        try:
            server.wait_ready(self.cancel)
        except EngineError:
            self.unload()
            raise
        return server, time.monotonic() - started

    def _release(self, cfg: dict) -> None:
        keep = float(cfg.get("keep_loaded_seconds") or 0)
        if keep <= 0:
            self.unload()
            return
        with self.server_lock:
            if self.unload_timer:
                self.unload_timer.cancel()
            self.unload_timer = threading.Timer(keep, self.unload)
            self.unload_timer.daemon = True
            self.unload_timer.start()

    # ---------- translating ----------
    def _direction(self, req: dict, text: str, enabled: list[str]) -> tuple[str, str]:
        source = req.get("source") or "auto"
        target = req.get("target") or "auto"
        if source not in languages.CATALOG:
            candidates = [c for c in enabled if c != target] if target in languages.CATALOG else enabled
            candidates = candidates or enabled
            source = self.book.language_of(text, candidates) or languages.detect(text, candidates)
        if target not in languages.CATALOG or target == source:
            target = next(c for c in enabled + ["en", "de"] if c != source)
        return source, target

    def _memory(self, chunk: str, source: str, target: str, cfg: dict):
        """Literal phrase matches (mandatory) and semantically similar ones (advice)."""
        hints = self.book.hints(chunk, source, target)
        similar = []
        memory = cfg["memory"]
        if memory.get("vector"):
            seen = {h["id"] for h in hints}
            for hit in self.index.query(chunk, source, int(memory.get("max_hints") or 4),
                                        float(memory.get("min_similarity") or 0.6)):
                entry = self.book.describe(hit["id"], source, target, hit["text"])
                if entry and hit["id"] not in seen:
                    similar.append({**entry, "match": "similar", "similarity": hit["similarity"]})
        return hints, similar

    def translate(self, req: dict) -> None:
        req_id = req.get("id")
        started = time.monotonic()
        try:
            text = req.get("text") or ""
            full = self.config()
            cfg = full["engine"]
            engine = req.get("engine") or cfg.get("default") or "local"
            if not text.strip():
                emit({"id": req_id, "event": "done", "engine": "none", "seconds": 0})
                return
            source, target = self._direction(req, text, full["languages"]["enabled"])
            emit({"id": req_id, "event": "status", "stage": "start", "source": source, "target": target})

            hit = self.book.exact(text, source, target)
            if hit:
                translation, item = hit
                emit({"id": req_id, "event": "delta", "text": translation})
                emit({"id": req_id, "event": "done", "engine": "phrasebook", "source": source, "target": target,
                      "used": [{**self.book.describe(item["id"], source, target), "match": "whole"}],
                      "warnings": [], "seconds": round(time.monotonic() - started, 2)})
                return

            style = req.get("style") or full.get("style") or "neutral"
            pair = {source, target}
            style_notes = " ".join(p.style_notes for p in self.book.packs.values()
                                   if p.style_notes and pair <= set(p.codes))
            src_name, tgt_name = languages.name(source), languages.name(target)

            size = model_name = None
            server = None
            load_seconds = 0.0
            vram_before = None
            was_loaded = False
            if engine == "local":
                size = req.get("size") or cfg["model"]
                model_path = self.resolve_model(size, cfg)
                model_name = model_path.stem
                vram_before = gpu.vram_mb(cfg["gpu_index"])
                was_loaded = self.server is not None
                server, load_seconds = self._ensure_server(req_id, model_path, cfg)
            else:
                model_name = (full["providers"].get(engine) or {}).get("model") or ""

            usage = providers.new_usage()

            def run(messages, chunk):
                if engine == "local":
                    return server.chat_stream(messages, len(chunk) // 2 + 256, self.cancel)
                return providers.stream(engine, messages, full["providers"], self.cancel, usage)

            def stream_chunk(messages, chunk):
                parts = []
                for piece in run(messages, chunk):
                    if not parts:
                        piece = piece.lstrip()
                        if not piece:
                            continue
                    parts.append(piece)
                    emit({"id": req_id, "event": "delta", "text": piece})
                output = "".join(parts)
                clean = prompting.strip_wrapper(output)
                if clean != output:  # the model echoed the <text> wrapper: show the cleaned text
                    emit({"id": req_id, "event": "replace", "text": done_text + clean})
                return clean

            emit({"id": req_id, "event": "status", "stage": "translating"})
            chunks = textutil.chunk_text(text)
            done_text = ""
            used, problems = {}, []
            previous = None
            try:
                for number, (chunk, separator) in enumerate(chunks):
                    hints, similar = self._memory(chunk, source, target, full)
                    for entry in hints + similar:
                        used.setdefault(entry["id"], entry)
                    kwargs = dict(
                        hints=[(h["source"], h["target"]) for h in hints],
                        similar=[(s["source"], s["target"]) for s in similar],
                        style=style, style_notes=style_notes, context=previous)
                    output = stream_chunk(prompting.build_messages(chunk, src_name, tgt_name, **kwargs), chunk)

                    failed = checks.check(chunk, output, source, target) if full["checks"].get("enabled") else []
                    if failed and full["checks"].get("retry"):
                        emit({"id": req_id, "event": "status", "stage": "retry", "reason": failed[0]})
                        emit({"id": req_id, "event": "replace", "text": done_text})
                        retry = prompting.build_messages(chunk, src_name, tgt_name,
                                                         retry_note=checks.RETRY_NOTES[failed[0]], **kwargs)
                        output = stream_chunk(retry, chunk)
                        failed = checks.check(chunk, output, source, target)
                    for code in failed:
                        if code not in problems:
                            problems.append(code)

                    done_text += output + separator
                    if separator:
                        emit({"id": req_id, "event": "delta", "text": separator})
                    if len(chunks) > 1:
                        emit({"id": req_id, "event": "progress", "chunk": number + 1, "chunks": len(chunks)})
                    previous = (chunk[-CONTEXT_CHARS:], output[-CONTEXT_CHARS:])
            finally:
                if engine == "local":
                    emit({"id": req_id, "event": "status", "stage": "unloading"})
                    self._release(cfg)

            done = {"id": req_id, "event": "done", "engine": engine, "model": model_name, "size": size,
                    "source": source, "target": target, "style": style,
                    "used": list(used.values()), "warnings": checks.warnings(problems),
                    "seconds": round(time.monotonic() - started, 2)}
            if engine == "local":
                unloaded = self.server is None
                if unloaded and vram_before and not was_loaded:
                    vram_after = local_engine.wait_vram_released(vram_before["free"], cfg["gpu_index"])
                else:
                    vram_after = gpu.vram_mb(cfg["gpu_index"])
                done.update(unloaded=unloaded, load_seconds=round(load_seconds, 2),
                            vram_free_before_mb=vram_before["free"] if vram_before else None,
                            vram_free_after_mb=vram_after["free"] if vram_after else None)
            elif usage["input_tokens"] or usage["output_tokens"]:
                done["usage"] = {"input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
                                 "cost_usd": round(usage["cost_usd"], 6) if usage["cost_known"] else None}
            emit(done)
        except EngineError as err:
            emit({"id": req_id, "event": "error", "code": err.code, "message": str(err), **err.extra})
        except Exception as err:  # never let the worker die silently
            emit({"id": req_id, "event": "error", "code": "internal", "message": f"{type(err).__name__}: {err}"})

    # ---------- language packs ----------
    def _packs_changed(self) -> None:
        self.book.set_packs(self._load_packs())
        self.sync_index()

    def pack_install(self, req: dict) -> str:
        target_dir = self.user_dir / "packs"
        if req.get("url"):
            url = str(req["url"])
            if not url.lower().startswith("https://"):
                raise phrases.PackError("Sprachpakete werden nur über https:// geladen.")
            with tempfile.TemporaryDirectory(prefix="turing-translate-") as work:
                archive = Path(work) / "pack.zip"
                try:
                    with urllib.request.urlopen(url, timeout=30) as resp:
                        data = resp.read(phrases.MAX_PACK_BYTES + 1)
                except (OSError, ValueError) as err:
                    raise phrases.PackError(f"Download fehlgeschlagen: {err}")
                if len(data) > phrases.MAX_PACK_BYTES:
                    raise phrases.PackError("Das Sprachpaket ist zu groß.")
                archive.write_bytes(data)
                pack_id = phrases.install_pack(archive, target_dir)
        else:
            source = Path(str(req.get("path") or ""))
            if source.name == "manifest.json":
                source = source.parent
            if not source.exists():
                raise phrases.PackError("Die gewählte Datei wurde nicht gefunden.")
            pack_id = phrases.install_pack(source, target_dir)
        self._packs_changed()
        pack = self.book.packs.get(pack_id)
        if pack:  # switch the pack's languages on right away
            enabled = self.config()["languages"]["enabled"]
            self.save_config({"languages": {"enabled": enabled + [c for c in pack.codes
                                                                  if c not in enabled and c in languages.CATALOG]}})
        return pack_id

    def pack_remove(self, pack_id: str) -> None:
        pack = self.book.packs.get(pack_id)
        if not pack or pack.origin != "user":
            raise phrases.PackError("Nur selbst installierte Sprachpakete lassen sich entfernen.")
        for name in ("manifest.json", "phrases.json"):
            (pack.folder / name).unlink(missing_ok=True)
        try:
            pack.folder.rmdir()
        except OSError:
            pass
        self._packs_changed()

    def pack_index(self) -> list:
        url = self.config()["packs"].get("index_url") or ""
        if not url.lower().startswith("https://"):
            return []
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                data = json.loads(resp.read(2_000_000).decode("utf-8"))
        except (OSError, ValueError) as err:
            raise phrases.PackError(f"Paketliste nicht abrufbar: {err}")
        rows = data.get("packs", []) if isinstance(data, dict) else data
        return [row for row in rows if isinstance(row, dict) and row.get("id") and row.get("url")]

    # ---------- requests ----------
    def handle(self, req: dict) -> bool:
        cmd = req.get("cmd")
        req_id = req.get("id")
        if cmd == "translate":
            self.stop_worker()
            self.cancel.clear()
            self.worker = threading.Thread(target=self.translate, args=(req,), daemon=True)
            self.worker.start()
        elif cmd == "cancel":
            self.cancel.set()
            emit({"id": req_id, "event": "cancelled"})
        elif cmd == "status":
            emit({"id": req_id, "event": "status_info", **self.status()})
        elif cmd == "vram":
            emit({"id": req_id, "event": "vram", "vram": gpu.vram_mb(self.config()["engine"]["gpu_index"])})
        elif cmd == "set_config":
            self.save_config(req.get("config") or {})
            self.sync_index()
            emit({"id": req_id, "event": "config", "config": self.public_config()})
        elif cmd == "unload":
            self.unload()
            emit({"id": req_id, "event": "unloaded"})
        elif cmd in ("phrases", "phrase_save", "phrase_delete"):
            enabled = self.config()["languages"]["enabled"]
            source = req.get("source") or enabled[0]
            target = req.get("target") or enabled[1]
            try:
                if cmd == "phrase_save":
                    self.book.save(source, target, req.get("source_text") or "", req.get("target_text") or "",
                                   req.get("entry_id") or "")
                    self.sync_index()
                elif cmd == "phrase_delete":
                    self.book.delete(req.get("entry_id") or "")
                    self.sync_index()
            except ValueError as err:
                emit({"id": req_id, "event": "error", "code": "phrase_invalid", "message": str(err)})
                return True
            emit({"id": req_id, "event": "phrases", "source": source, "target": target,
                  "phrases": self.book.pairs(source, target)})
        elif cmd in ("pack_install", "pack_remove", "pack_index"):
            try:
                if cmd == "pack_install":
                    emit({"id": req_id, "event": "pack_installed", "pack": self.pack_install(req)})
                elif cmd == "pack_remove":
                    self.pack_remove(req.get("pack") or "")
                    emit({"id": req_id, "event": "pack_removed", "pack": req.get("pack")})
                else:
                    emit({"id": req_id, "event": "pack_index", "packs": self.pack_index()})
            except (phrases.PackError, OSError) as err:
                emit({"id": req_id, "event": "error", "code": "pack_failed", "message": str(err)})
        elif cmd == "provider_models":
            try:
                cfg = self.config()["providers"]["openai_api"]
                emit({"id": req_id, "event": "provider_models", "models": providers.openai_models(cfg)})
            except EngineError as err:
                emit({"id": req_id, "event": "error", "code": err.code, "message": str(err)})
        elif cmd == "shutdown":
            self.stop_worker()
            self.unload()
            return False
        else:
            emit({"id": req_id, "event": "error", "code": "unknown_command", "message": f"Unbekannter Befehl: {cmd}"})
        return True

    def stop_worker(self) -> None:
        if self.worker and self.worker.is_alive():
            self.cancel.set()
            self.worker.join(timeout=30)


def stdin_lines():
    """Yield request lines without ever parking in a blocking read on a Windows pipe.

    While a thread sits in a blocking read on a pipe, Windows makes every other call that
    touches the same pipe wait. Native libraries (numpy, onnxruntime) look at the standard
    handles while their DLLs load, so a background import would freeze until the next request
    arrived, and with it every thread start in this process. Polling the pipe avoids that.
    """
    if os.name != "nt":
        yield from sys.stdin
        return
    import ctypes
    import msvcrt
    from ctypes import wintypes

    try:
        fd = sys.stdin.fileno()
        handle = msvcrt.get_osfhandle(fd)
    except (OSError, ValueError):
        yield from sys.stdin
        return
    peek = ctypes.WinDLL("kernel32", use_last_error=True).PeekNamedPipe
    peek.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, wintypes.LPDWORD,
                     wintypes.LPDWORD, wintypes.LPDWORD]
    peek.restype = wintypes.BOOL
    available = wintypes.DWORD(0)
    if not peek(handle, None, 0, None, ctypes.byref(available), None) and ctypes.get_last_error() != 109:
        yield from sys.stdin  # a console or a file, not a pipe
        return
    pending = b""
    while True:
        if not peek(handle, None, 0, None, ctypes.byref(available), None):
            return  # the other end closed the pipe
        if not available.value:
            time.sleep(0.02)
            continue
        chunk = os.read(fd, available.value)
        if not chunk:
            return
        pending += chunk
        while b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            yield line.decode("utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", default=str(Path(__file__).resolve().parent.parent))
    default_config = Path(os.environ.get("APPDATA") or Path.home()) / "TuringTranslate" / "config.json"
    parser.add_argument("--config", default=str(default_config))
    args = parser.parse_args()

    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sidecar = Sidecar(Path(args.app_dir), Path(args.config))
    emit({"event": "ready"})
    try:
        for line in stdin_lines():
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except ValueError:
                emit({"event": "error", "code": "bad_json", "message": "Ungültige Anfrage"})
                continue
            if not sidecar.handle(req):
                break
    finally:
        sidecar.stop_worker()
        sidecar.unload()


if __name__ == "__main__":
    main()
