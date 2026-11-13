"""End-to-end check of the sidecar process over its JSON-lines protocol.

Run: .venv\\Scripts\\python sidecar\\tests\\smoke_sidecar.py [small|medium|large|claude_sub|claude_api|openai_api]
Uses a temporary config (the real settings stay untouched) unless --real-config is given.
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent.parent
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
CHOICE = ARGS[0] if ARGS else "small"
ENGINE = "local" if CHOICE in ("small", "medium", "large") else CHOICE

TEXTS = [
    ("Ich glaub, ich spinne", {}),                                             # whole phrase from the pack
    ("Gestern hatte ich einen Kater, aber heute ist alles in Butter.", {}),      # phrases inside a sentence
    ("Ehrlich gesagt werde ich noch wahnsinnig, wenn der Zug wieder ausfällt.", {}),  # only similar
    ("Could you send me the report by Friday? Thanks a lot!", {"style": "formal"}),
    ("Der erste Absatz handelt von Anna. Sie wohnt in Köln.\n\nSie arbeitet dort als Ärztin und fährt jeden "
     "Tag mit dem Rad.", {}),
]


def main():
    work = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    cmd = [sys.executable, str(ROOT / "sidecar" / "main.py"), "--app-dir", str(ROOT)]
    if "--real-config" not in sys.argv:
        config = Path(work.name) / "config.json"
        providers = {ENGINE: {"enabled": True}} if ENGINE != "local" else {}
        config.write_text(json.dumps({"providers": providers}), encoding="utf-8")
        cmd += ["--config", str(config)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding="utf-8")

    def send(message):
        proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        proc.stdin.flush()

    def read_until(request_id, final):
        events = []
        for line in proc.stdout:
            event = json.loads(line)
            if event.get("id") == request_id or request_id is None:
                events.append(event)
                if event.get("event") in final:
                    return events
        raise SystemExit("sidecar closed unexpectedly")

    read_until(None, {"ready"})
    send({"cmd": "status", "id": "s"})
    status = read_until("s", {"status_info"})[-1]
    print("engines:", ", ".join(f"{e['id']}={'ready' if e['ready'] else e['reason']}" for e in status["engines"]))
    print("presets:", {k: v.get("name", "missing") for k, v in status["presets"].items() if isinstance(v, dict)})

    # Wait for the phrase memory so the "similar" case is meaningful.
    deadline = time.monotonic() + 300
    while status["memory"]["state"] == "loading" and time.monotonic() < deadline:
        time.sleep(1)
        send({"cmd": "status", "id": "s"})
        status = read_until("s", {"status_info"})[-1]
    print("memory:", status["memory"])

    failed = 0
    for number, (text, extra) in enumerate(TEXTS):
        request = {"cmd": "translate", "id": f"t{number}", "text": text, "engine": ENGINE, **extra}
        if ENGINE == "local":
            request["size"] = CHOICE
        send(request)
        events = read_until(f"t{number}", {"done", "error"})
        last = events[-1]
        output = ""
        for event in events:
            if event["event"] == "delta":
                output += event["text"]
            elif event["event"] == "replace":
                output = event["text"]
        print(f"\n> {text!r}")
        if last["event"] == "error":
            failed += 1
            print(f"  ERROR {last['code']}: {last['message']}")
            continue
        print(f"  {output!r}")
        used = [f"{u['match']}:{u['source']}" for u in last.get("used", [])]
        print(f"  {last['engine']} {last.get('model') or ''} {last.get('source')}->{last.get('target')} "
              f"{last['seconds']}s used={used} warnings={[w['code'] for w in last.get('warnings', [])]} "
              f"usage={last.get('usage')}")
        if not output.strip():
            failed += 1

    send({"cmd": "shutdown"})
    proc.wait(timeout=30)
    print(f"\n{failed} failed" if failed else "\nall translated")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
