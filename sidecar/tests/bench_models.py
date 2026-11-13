"""Compare local models on idioms: load time, speed, release of graphics memory, quality.

Usage:  python sidecar/tests/bench_models.py [part of a model name ...]
The sentences are deliberately NOT in the phrase book, so the model has to cope on its own.
"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import gpu  # noqa: E402
import local_engine  # noqa: E402
import prompting  # noqa: E402

APP_DIR = Path(__file__).resolve().parents[2]
SENTENCES = [
    ("German", "English", "Ich glaub, mein Schwein pfeift! Der hat doch nicht alle Tassen im Schrank."),
    ("German", "English", "Nach der Nachtschicht war ich völlig durch den Wind und hab erstmal blau gemacht."),
    ("German", "English", "Das Projekt ist ins Wasser gefallen, weil der Chef kalte Füße bekommen hat."),
    ("German", "English", "Jetzt mal Butter bei die Fische: Wer hat hier Mist gebaut?"),
    ("German", "English", "Bitte senden Sie uns die unterschriebenen Unterlagen bis spätestens Freitag zurück."),
    ("English", "German", "He kicked the bucket last year, and his kids have been at each other's throats ever since."),
    ("English", "German", "Don't beat yourself up over it, we'll cross that bridge when we come to it."),
    ("English", "German", "I'm swamped today, can I take a rain check on lunch?"),
]


def bench(model: dict) -> None:
    path = Path(model["path"])
    exe, dll_dirs = local_engine.find_llama_server("auto", APP_DIR)
    before = gpu.vram_mb()
    print(f"\n=== {model['name']}  ({model['size_mb']} MB, estimated need {local_engine.required_vram_mb(path, 4096)} MB) ===")
    cancel = threading.Event()
    t0 = time.monotonic()
    server = local_engine.LlamaServer(exe, dll_dirs, path, 4096, Path(tempfile.gettempdir()) / "turing-translate-bench.log")
    try:
        server.wait_ready(cancel)
        load = time.monotonic() - t0
        loaded = gpu.vram_mb()
        print(f"load: {load:.1f} s | graphics memory used by the model: {before['free'] - loaded['free']} MB")
        total_chars, total_time = 0, 0.0
        for src, tgt, sentence in SENTENCES:
            t1 = time.monotonic()
            out = "".join(server.chat_stream(prompting.build_messages(sentence, src, tgt, []), 400, cancel)).strip()
            dt = time.monotonic() - t1
            total_chars += len(out)
            total_time += dt
            print(f"  [{dt:4.1f}s] {sentence}\n          -> {out}")
        print(f"speed: {total_chars / total_time:.0f} characters/s")
    finally:
        t2 = time.monotonic()
        server.stop()
        after = local_engine.wait_vram_released(before["free"], 0)
        print(f"unload: {time.monotonic() - t2:.1f} s | graphics memory free before {before['free']} MB, after {after['free']} MB")


if __name__ == "__main__":
    needles = [n.lower() for n in sys.argv[1:]]
    for candidate in local_engine.list_models(APP_DIR):
        if not needles or any(n in candidate["name"].lower() for n in needles):
            bench(candidate)
