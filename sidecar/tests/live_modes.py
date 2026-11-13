"""Live check of the clarifying question, thorough mode and explain mode with a real engine.

Run: .venv\\Scripts\\python sidecar\\tests\\live_modes.py [small|medium|large|claude_sub|claude_api|openai_api]
Uses a temporary config, so the app's own settings and history stay untouched.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import main as sidecar_main

APP_DIR = Path(__file__).resolve().parent.parent.parent
SIZES = ("small", "medium", "large")


def main() -> None:
    choice = sys.argv[1] if len(sys.argv) > 1 else "medium"
    base = {"engine": "local", "size": choice} if choice in SIZES else {"engine": choice}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as work:
        config = Path(work) / "config.json"
        settings = {"memory": {"vector": False}, "engine": {"keep_loaded_seconds": 60}}
        if choice not in SIZES:
            settings["providers"] = {choice: {"enabled": True}}
        config.write_text(json.dumps(settings), encoding="utf-8")
        side = sidecar_main.Sidecar(APP_DIR, config)
        events = []
        sidecar_main.emit = events.append

        def run(method, **request):
            events.clear()
            getattr(side, method)({"id": 1, **base, **request})
            last = events[-1]
            if last["event"] == "error":
                print("   ERROR:", last["message"])
            return last, "".join(e.get("text", "") for e in events if e["event"] == "delta")

        def final_text():
            text = ""
            for e in events:
                if e["event"] == "delta":
                    text += e["text"]
                elif e["event"] == "replace":
                    text = e["text"]
            return text

        print("== clarifying question ==")
        for text in ("Der Ton war wirklich furchtbar.", "Kannst du mir bitte das Salz reichen?",
                     "She saw her duck.", "Wir treffen uns morgen um zehn im Büro."):
            last, _ = run("translate", text=text, clarify=True)
            if last["event"] == "question":
                print(f"   {text}\n     ? {last['question']}")
                for option in last["options"]:
                    print(f"       - {option['label']}: {option['meaning']}")
                pick = last["options"][-1]
                run("translate", text=text, clarify=True, clarification=pick["meaning"])
                print(f"     chosen '{pick['label']}' => {final_text()}")
            else:
                print(f"   {text}\n     (no question, last event '{last['event']}') => {final_text()}  [{last.get('seconds')} s]")

        print("== thorough mode ==")
        for text in ("Ich bekomme ein Steak, und mein Chef will eventuell später noch dazukommen.",
                     "Das Meeting wurde auf Donnerstag verschoben, weil der Beamer kaputt ist."):
            last, draft = run("translate", text=text, thorough=True)
            print(f"   {text}\n     draft: {draft}\n     final: {final_text()}\n     review: {last.get('review')}  [{last.get('seconds')} s]")

        print("== explain ==")
        last, _ = run("explain", text="Ich drücke dir die Daumen, das wird schon schiefgehen.",
                      translation="I press my thumbs for you, it will go wrong.", source="de", target="en")
        print(json.dumps({k: last.get(k) for k in ("summary", "alternatives", "notes")}, ensure_ascii=False, indent=2))
        side.unload()


if __name__ == "__main__":
    main()
