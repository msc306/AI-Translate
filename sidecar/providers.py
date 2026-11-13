"""Cloud engines: Claude API, Claude subscription (Claude Code CLI), OpenAI-compatible API,
ChatGPT subscription (Codex CLI).

Every engine is a generator that yields pieces of text. Token counts and costs are added to the
`usage` dict. Standard library only.
"""
import http.client
import json
import os
import shutil
import subprocess
import tempfile
import threading
import urllib.parse
from pathlib import Path

import winjob
from local_engine import NO_WINDOW, EngineError

LABELS = {
    "local": "Lokal (GPU)",
    "claude_api": "Claude (API-Schlüssel)",
    "claude_sub": "Claude (Abo: Pro/Max)",
    "openai_api": "OpenAI-kompatibel (API-Schlüssel)",
    "chatgpt_sub": "ChatGPT (Abo, über Codex)",
}

# USD per million tokens (input, output); used for the cost estimate only.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-fable-5-2": (8.0, 40.0),
}

CANCELLED = ("cancelled", "Abgebrochen")


def new_usage() -> dict:
    return {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "cost_known": False}


def _key(cfg: dict) -> str:
    return (cfg.get("key") or os.environ.get(cfg.get("key_env") or "", "")).strip()


def _split(messages):
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    turns = [m for m in messages if m["role"] != "system"]
    return system, turns


def _error_text(raw: str) -> str:
    try:
        data = json.loads(raw)
        error = data.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)
        if error:
            return str(error)
    except (ValueError, AttributeError):
        pass
    return raw.strip()[:300]


def _connect(url: str, timeout: float = 120):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise EngineError("api_failed", f"Ungültige Adresse: {url}")
    cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    return cls(parts.hostname, parts.port, timeout=timeout), path


def _sse(url, headers, body, cancel, name):
    """POST a JSON body and yield the decoded `data:` events of the answer stream."""
    conn, path = _connect(url)
    try:
        conn.request("POST", path, json.dumps(body).encode("utf-8"),
                     {"content-type": "application/json", **headers})
        resp = conn.getresponse()
        if resp.status != 200:
            detail = _error_text(resp.read(4000).decode("utf-8", "replace"))
            raise EngineError("api_failed", f"{name} meldet HTTP {resp.status}: {detail}", status=resp.status)
        for raw in resp:
            if cancel.is_set():
                raise EngineError(*CANCELLED)
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                yield json.loads(data)
            except ValueError:
                continue
    except OSError as err:
        raise EngineError("api_failed", f"{name} nicht erreichbar: {err}")
    finally:
        conn.close()


# ---------------------------------------------------------------- Claude API

def claude_api(messages, cfg, cancel, usage):
    key = _key(cfg)
    if not key:
        raise EngineError("api_key_missing",
                          "Kein Claude-API-Schlüssel hinterlegt (Einstellungen → Anbieter).")
    system, turns = _split(messages)
    model = cfg.get("model") or "claude-haiku-5-5"
    # No temperature/top_p: current Claude models reject sampling parameters.
    body = {"model": model, "max_tokens": 16000, "stream": True, "system": system, "messages": turns}
    if cfg.get("effort"):
        body["output_config"] = {"effort": cfg["effort"]}
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}

    tokens_in = tokens_out = 0
    for event in _sse("https://api.anthropic.com/v1/messages", headers, body, cancel, "Claude-API"):
        kind = event.get("type")
        if kind == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta" and delta.get("text"):
                yield delta["text"]
        elif kind == "message_start":
            start = (event.get("message") or {}).get("usage") or {}
            tokens_in = (start.get("input_tokens", 0) + start.get("cache_read_input_tokens", 0)
                         + start.get("cache_creation_input_tokens", 0))
        elif kind == "message_delta":
            tokens_out = (event.get("usage") or {}).get("output_tokens", tokens_out)
            if (event.get("delta") or {}).get("stop_reason") == "refusal":
                raise EngineError("refused", "Claude hat die Übersetzung dieses Textes abgelehnt.")
        elif kind == "error":
            raise EngineError("api_failed", f"Claude-API: {_error_text(json.dumps(event))}")
    usage["input_tokens"] += tokens_in
    usage["output_tokens"] += tokens_out
    if model in PRICES:
        price_in, price_out = PRICES[model]
        usage["cost_usd"] += (tokens_in * price_in + tokens_out * price_out) / 1_000_000
        usage["cost_known"] = True


# ------------------------------------------------------- OpenAI-compatible API

def _openai_base(cfg: dict) -> str:
    return (cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")


def _openai_headers(cfg: dict) -> dict:
    key = _key(cfg)
    if not key and "api.openai.com" in _openai_base(cfg):
        raise EngineError("api_key_missing",
                          "Kein OpenAI-API-Schlüssel hinterlegt (Einstellungen → Anbieter).")
    return {"authorization": f"Bearer {key}"} if key else {}


def openai_api(messages, cfg, cancel, usage):
    headers = _openai_headers(cfg)
    model = (cfg.get("model") or "").strip()
    if not model:
        raise EngineError("api_failed", "Für den OpenAI-kompatiblen Anbieter ist kein Modell eingestellt.")
    body = {"model": model, "messages": messages, "stream": True,
            "stream_options": {"include_usage": True}}
    for event in _sse(_openai_base(cfg) + "/chat/completions", headers, body, cancel, "Der Anbieter"):
        if event.get("error"):
            raise EngineError("api_failed", f"Der Anbieter meldet: {_error_text(json.dumps(event))}")
        for choice in event.get("choices") or []:
            piece = (choice.get("delta") or {}).get("content")
            if piece:
                yield piece
        counts = event.get("usage")
        if counts:
            usage["input_tokens"] += counts.get("prompt_tokens", 0)
            usage["output_tokens"] += counts.get("completion_tokens", 0)


def openai_models(cfg: dict) -> list[str]:
    """Model ids offered by the configured OpenAI-compatible server."""
    conn, path = _connect(_openai_base(cfg) + "/models", timeout=20)
    try:
        conn.request("GET", path, headers=_openai_headers(cfg))
        resp = conn.getresponse()
        raw = resp.read(2_000_000).decode("utf-8", "replace")
        if resp.status != 200:
            raise EngineError("api_failed", f"HTTP {resp.status}: {_error_text(raw)}")
        return sorted(item["id"] for item in json.loads(raw).get("data", []) if item.get("id"))
    except (OSError, ValueError) as err:
        raise EngineError("api_failed", f"Modellliste nicht abrufbar: {err}")
    finally:
        conn.close()


# ------------------------------------------------------------ subscription CLIs

def find_cli(command: str) -> str | None:
    """Locate a command line tool; also looks where the installers put it on Windows."""
    command = (command or "").strip()
    if not command:
        return None
    if Path(command).is_file():
        return command
    found = shutil.which(command)
    if found:
        return found
    home = Path.home()
    for folder in (home / ".local" / "bin", home / "AppData" / "Roaming" / "npm"):
        for suffix in (".exe", ".cmd", ""):
            candidate = folder / (command + suffix)
            if candidate.is_file():
                return str(candidate)
    return None


def _spawn(args, stdin_text, cwd, env, cancel):
    try:
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, cwd=cwd, env=env,
                                creationflags=NO_WINDOW if os.name == "nt" else 0)
    except OSError as err:
        raise EngineError("cli_failed", f"{Path(args[0]).name} lässt sich nicht starten: {err}")
    try:
        winjob.bind_to_parent(proc)
    except Exception:
        pass

    def watch():
        while proc.poll() is None:
            if cancel.wait(0.2):
                proc.kill()
                return

    threading.Thread(target=watch, daemon=True).start()
    try:
        proc.stdin.write(stdin_text.encode("utf-8"))
        proc.stdin.close()
    except OSError:
        pass
    return proc


def _finish(proc):
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def claude_sub(messages, cfg, cancel, usage):
    """Translate through the user's Claude subscription by running Claude Code without tools."""
    exe = find_cli(cfg.get("command") or "claude")
    if not exe:
        raise EngineError("cli_missing", "Claude Code wurde nicht gefunden. Installieren und einmal "
                                         "`claude` starten, um sich mit dem Abo anzumelden.")
    system, turns = _split(messages)
    # Without the key the CLI uses the subscription login instead of billing the API account.
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    with tempfile.TemporaryDirectory(prefix="turing-translate-") as work:
        prompt_file = Path(work) / "system.txt"
        prompt_file.write_text(system, encoding="utf-8")
        args = [exe, "-p", "--output-format", "stream-json", "--include-partial-messages", "--verbose",
                "--model", cfg.get("model") or "haiku", "--system-prompt-file", str(prompt_file),
                "--tools", "", "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence"]
        proc = _spawn(args, turns[-1]["content"], work, env, cancel)
        got_text = finished = False
        tail = []
        try:
            for raw in proc.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    tail = (tail + [line])[-5:]
                    continue
                kind = event.get("type")
                if kind == "stream_event":
                    inner = event.get("event") or {}
                    delta = inner.get("delta") or {}
                    if inner.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                        if delta.get("text"):
                            got_text = True
                            yield delta["text"]
                elif kind == "result":
                    finished = True
                    if event.get("is_error"):
                        raise EngineError("cli_failed", _login_hint(str(event.get("result") or "Fehler"), "claude"))
                    counts = event.get("usage") or {}
                    usage["input_tokens"] += (counts.get("input_tokens", 0)
                                              + counts.get("cache_read_input_tokens", 0)
                                              + counts.get("cache_creation_input_tokens", 0))
                    usage["output_tokens"] += counts.get("output_tokens", 0)
                    if not got_text and event.get("result"):
                        yield str(event["result"])
        finally:
            _finish(proc)
        if cancel.is_set():
            raise EngineError(*CANCELLED)
        if not finished:
            raise EngineError("cli_failed", _login_hint(" ".join(tail) or "Claude Code hat nicht geantwortet.",
                                                        "claude"))


def chatgpt_sub(messages, cfg, cancel, usage):
    """Translate through the user's ChatGPT subscription by running the Codex CLI. No streaming."""
    exe = find_cli(cfg.get("command") or "codex")
    if not exe:
        raise EngineError("cli_missing", "Die Codex-CLI wurde nicht gefunden. Installieren (npm i -g "
                                         "@openai/codex) und einmal `codex login` ausführen.")
    system, turns = _split(messages)
    prompt = f"{system}\n\n<text_to_translate>\n{turns[-1]['content']}\n</text_to_translate>"
    with tempfile.TemporaryDirectory(prefix="turing-translate-") as work:
        answer = Path(work) / "answer.txt"
        args = [exe, "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only",
                "--output-last-message", str(answer)]
        if cfg.get("model"):
            args += ["--model", cfg["model"]]
        args.append("-")
        proc = _spawn(args, prompt, work, None, cancel)
        try:
            output = proc.stdout.read().decode("utf-8", "replace")
            proc.wait()
        finally:
            _finish(proc)
        if cancel.is_set():
            raise EngineError(*CANCELLED)
        text = answer.read_text(encoding="utf-8", errors="replace").strip() if answer.is_file() else ""
        if not text:
            raise EngineError("cli_failed", _login_hint(output.strip()[-300:] or "Codex hat nicht geantwortet.",
                                                        "codex login"))
        yield text


def _login_hint(message: str, command: str) -> str:
    lowered = message.lower()
    if "login" in lowered or "log in" in lowered or "auth" in lowered or "credential" in lowered:
        return f"{message} – bitte einmal `{command}` im Terminal ausführen und anmelden."
    return message


# ------------------------------------------------------------------ dispatcher

ENGINES = {"claude_api": claude_api, "claude_sub": claude_sub,
           "openai_api": openai_api, "chatgpt_sub": chatgpt_sub}


def stream(engine, messages, providers_cfg, cancel, usage):
    cfg = (providers_cfg or {}).get(engine) or {}
    if engine not in ENGINES:
        raise EngineError("unknown_engine", f"Unbekannter Anbieter: {engine}")
    if not cfg.get("enabled"):
        raise EngineError("engine_disabled", f"{LABELS[engine]} ist in den Einstellungen nicht aktiviert.")
    yield from ENGINES[engine](messages, cfg, cancel, usage)


def availability(providers_cfg: dict) -> list[dict]:
    """What the UI needs to offer the engines: enabled, ready, and why not."""
    result = [{"id": "local", "label": LABELS["local"], "enabled": True, "ready": True, "reason": ""}]
    for engine in ENGINES:
        cfg = (providers_cfg or {}).get(engine) or {}
        reason = ""
        if engine == "claude_api" and not _key(cfg):
            reason = "API-Schlüssel fehlt"
        elif engine == "openai_api":
            if not _key(cfg) and "api.openai.com" in _openai_base(cfg):
                reason = "API-Schlüssel fehlt"
            elif not (cfg.get("model") or "").strip():
                reason = "Modell fehlt"
        elif engine == "claude_sub" and not find_cli(cfg.get("command") or "claude"):
            reason = "Claude Code nicht installiert"
        elif engine == "chatgpt_sub" and not find_cli(cfg.get("command") or "codex"):
            reason = "Codex-CLI nicht installiert"
        result.append({"id": engine, "label": LABELS[engine], "enabled": bool(cfg.get("enabled")),
                       "ready": not reason, "reason": reason})
    return result
