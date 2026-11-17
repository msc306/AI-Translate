"""MCP server: offers the translator to AI assistants (Claude Code, Claude Desktop, ...) as tools.

Speaks JSON-RPC over stdin/stdout (MCP stdio transport) and drives the normal sidecar as a child
process, so the same engines, phrase memory and settings are used as in the app.

Register it for example with:
    claude mcp add ai-translate -- <path>\\.venv\\Scripts\\python.exe <path>\\sidecar\\mcp_server.py
"""
import argparse
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
VERSION = "0.2.0"
TIMEOUT = 600  # seconds for one translation, including loading a local model

ENGINES = ["local", "claude_sub", "claude_api", "openai_api", "openrouter", "chatgpt_sub"]
COMMON = {
    "engine": {"type": "string", "enum": ENGINES,
               "description": "Which engine to use. Default: the one chosen in the app (usually 'local')."},
    "size": {"type": "string", "enum": ["small", "medium", "large"],
             "description": "Local model size; only used with engine 'local'."},
}
TOOLS = [
    {
        "name": "translate",
        "description": "Translate text with the AI Translate app on this PC (local GPU model by default, "
                       "nothing leaves the machine). Uses the user's phrase book for idioms and fixed terms. "
                       "Call list_languages first to see which languages are enabled.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to translate."},
                "target": {"type": "string", "description": "Target language code such as 'en' or 'de'. "
                                                            "Default: chosen automatically from the enabled languages."},
                "source": {"type": "string", "description": "Source language code. Default: detected."},
                "style": {"type": "string", "enum": ["neutral", "formal", "casual", "literal"]},
                "thorough": {"type": "boolean", "description": "Second pass that reviews and corrects the draft. "
                                                               "About twice as slow."},
                **COMMON,
            },
            "required": ["text"],
        },
    },
    {
        "name": "explain_translation",
        "description": "Explain a translation: why it fits or what is wrong, alternatives and notes on idioms "
                       "or false friends. Explanations are in German. For texts up to 1500 characters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The source text."},
                "translation": {"type": "string", "description": "The translation to explain."},
                "source": {"type": "string", "description": "Source language code."},
                "target": {"type": "string", "description": "Target language code."},
                **COMMON,
            },
            "required": ["text", "translation"],
        },
    },
    {
        "name": "list_languages",
        "description": "List the enabled languages, the available engines and the styles of the translator.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class ToolError(Exception):
    pass


class Translator:
    """The sidecar as a child process; one request at a time."""

    def __init__(self, app_dir: Path, config: str | None):
        command = [sys.executable, str(Path(__file__).with_name("main.py")), "--app-dir", str(app_dir)]
        if config:
            command += ["--config", config]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.child = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"}, creationflags=flags)
        self.events = queue.Queue()
        self.next_id = 1
        threading.Thread(target=self._read, daemon=True).start()
        self._wait(lambda e: e.get("event") == "ready", 60)

    def _read(self) -> None:
        for line in self.child.stdout:
            try:
                self.events.put(json.loads(line))
            except ValueError:
                pass
        self.events.put({"event": "sidecar_exit"})

    def _wait(self, wanted, timeout: float) -> dict:
        try:
            while True:
                event = self.events.get(timeout=timeout)
                if event.get("event") == "sidecar_exit":
                    raise ToolError("The translation service stopped.")
                if wanted(event):
                    return event
        except queue.Empty:
            raise ToolError("The translator did not answer in time.") from None

    def request(self, message: dict, final: tuple, timeout: float = TIMEOUT) -> tuple[dict, str]:
        """Send one command; return its final event and the text streamed before it."""
        req_id = self.next_id
        self.next_id += 1
        self.child.stdin.write(json.dumps({"id": req_id, **message}, ensure_ascii=False) + "\n")
        self.child.stdin.flush()
        text = ""
        while True:
            event = self._wait(lambda e: e.get("id") == req_id, timeout)
            kind = event.get("event")
            if kind == "delta":
                text += event.get("text") or ""
            elif kind == "replace":
                text = event.get("text") or ""
            elif kind == "error":
                raise ToolError(event.get("message") or event.get("code") or "error")
            elif kind in final:
                return event, text

    def close(self) -> None:
        try:
            self.child.stdin.write('{"cmd": "shutdown"}\n')
            self.child.stdin.flush()
            self.child.wait(timeout=10)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            self.child.kill()


def pick(args: dict, *names) -> dict:
    return {n: args[n] for n in names if args.get(n) not in (None, "")}


def call_tool(translator: Translator, name: str, args: dict) -> str:
    if name == "translate":
        if not str(args.get("text") or "").strip():
            raise ToolError("text is empty")
        done, text = translator.request(
            {"cmd": "translate", "clarify": False, "history": False,
             **pick(args, "text", "source", "target", "style", "thorough", "engine", "size")}, ("done",))
        lines = [text.strip(), "", f"[{done.get('source')} -> {done.get('target')}, engine: {done.get('engine')}"
                 + (f", model: {done['model']}" if done.get("model") else "") + "]"]
        lines += [f"Warning: {w['message']}" for w in done.get("warnings") or []]
        lines += [f"Phrase book: {u['source']} -> {u['target']} ({u['match']})" for u in done.get("used") or []]
        lines += [f"Corrected in review: {issue}" for issue in (done.get("review") or {}).get("issues") or []]
        return "\n".join(lines)
    if name == "explain_translation":
        event, _ = translator.request(
            {"cmd": "explain", **pick(args, "text", "translation", "source", "target", "engine", "size")},
            ("explanation",))
        lines = [event.get("summary") or ""]
        if event.get("alternatives"):
            lines += ["", "Alternatives:"] + [f"- {a['text']} ({a['note']})" for a in event["alternatives"]]
        if event.get("notes"):
            lines += ["", "Notes:"] + [f"- {n['source']}: {n['note']}" for n in event["notes"]]
        return "\n".join(lines)
    if name == "list_languages":
        info, _ = translator.request({"cmd": "status"}, ("status_info",), 60)
        enabled = set(info["languages"]["enabled"])
        return json.dumps({
            "languages": [{"code": l["code"], "name": l["name"]}
                          for l in info["languages"]["catalog"] if l["code"] in enabled],
            "engines": [{"id": e["id"], "ready": e["ready"]} for e in info["engines"] if e["id"] == "local" or e["enabled"]],
            "default_engine": info["config"]["engine"]["default"],
            "styles": [s["id"] for s in info["styles"]],
        }, ensure_ascii=False)
    raise ToolError(f"Unknown tool: {name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--config", default=None, help="config file (default: the app's own settings)")
    options = parser.parse_args()
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")

    translator = None

    def reply(msg_id, result=None, error=None):
        message = {"jsonrpc": "2.0", "id": msg_id}
        message.update({"error": error} if error else {"result": result})
        sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                reply(None, error={"code": -32700, "message": "Parse error"})
                continue
            method, msg_id = msg.get("method"), msg.get("id")
            if msg_id is None:  # notification: nothing to answer
                continue
            params = msg.get("params") or {}
            if method == "initialize":
                wanted = params.get("protocolVersion")
                reply(msg_id, {"protocolVersion": wanted if wanted in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                               "capabilities": {"tools": {}},
                               "serverInfo": {"name": "ai-translate", "version": VERSION}})
            elif method == "ping":
                reply(msg_id, {})
            elif method == "tools/list":
                reply(msg_id, {"tools": TOOLS})
            elif method == "tools/call":
                try:
                    if translator is None:  # started on first use: listing tools stays instant
                        translator = Translator(Path(options.app_dir), options.config)
                    text = call_tool(translator, params.get("name"), params.get("arguments") or {})
                    reply(msg_id, {"content": [{"type": "text", "text": text}], "isError": False})
                except ToolError as err:
                    reply(msg_id, {"content": [{"type": "text", "text": str(err)}], "isError": True})
            else:
                reply(msg_id, error={"code": -32601, "message": f"Method not found: {method}"})
    finally:
        if translator:
            translator.close()


if __name__ == "__main__":
    main()
