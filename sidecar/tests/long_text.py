"""Check that a long text is translated completely (the number of paragraphs stays the same).

Usage:  python sidecar/tests/long_text.py [small|medium|large]
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]

PARAGRAPHS = [
    "Am Montag bin ich mit dem falschen Fuß aufgestanden. Der Wecker hat nicht geklingelt, und der Kaffee war alle.",
    "Auf dem Weg zur Arbeit stand ich eine halbe Stunde im Stau. Der Fahrer vor mir hat offenbar die Ruhe weg.",
    "Im Büro wartete schon die nächste Überraschung: Der Server war abgestürzt, und niemand fühlte sich zuständig.",
    "Meine Kollegin meinte nur, ich solle die Kirche im Dorf lassen. Leichter gesagt als getan.",
    "Mittags haben wir uns beim Italiener um die Ecke gestärkt. Die Pizza dort ist wirklich nicht von schlechten Eltern.",
    "Am Nachmittag kam der Kunde mit einer Liste von Änderungswünschen. Da ist mir fast der Kragen geplatzt.",
    "Wir haben uns trotzdem zusammengerauft und einen Plan gemacht. Jeder übernimmt bis Freitag zwei Punkte.",
    "Gegen fünf habe ich dann Feierabend gemacht. Draußen goss es wie aus Eimern.",
    "Zu Hause habe ich die Füße hochgelegt und einen alten Film geschaut. Der Hund lag mir dabei auf den Füßen.",
    "Später rief meine Schwester an und erzählte, dass sie umzieht. Sie hat endlich eine Wohnung mit Balkon gefunden.",
    "Ich habe versprochen, am Wochenende beim Kistenschleppen zu helfen. Dafür gibt es angeblich Kuchen.",
    "Kurz vor Mitternacht bin ich ins Bett gefallen. Morgen wird hoffentlich ein besserer Tag.",
    "Dienstag fing tatsächlich besser an. Die Sonne schien, und der Bus kam pünktlich.",
    "Der Server lief wieder, weil jemand über Nacht das Netzteil getauscht hatte. Ehre, wem Ehre gebührt.",
    "Nur der Kunde hatte seine Liste über Nacht verdoppelt. Manche Leute kriegen den Hals nicht voll.",
    "Wir haben ihm freundlich erklärt, dass das den Rahmen sprengt. Er will es sich überlegen.",
]


def main() -> None:
    size = sys.argv[1] if len(sys.argv) > 1 else "medium"
    text = "\n\n".join(PARAGRAPHS)
    config = Path(tempfile.mkdtemp()) / "config.json"
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "sidecar" / "main.py"), "--app-dir", str(ROOT), "--config", str(config)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8",
    )
    proc.stdout.readline()
    proc.stdin.write(json.dumps({"id": 1, "cmd": "translate", "text": text, "source": "de", "target": "en", "size": size}) + "\n")
    proc.stdin.flush()
    out, last = "", {}
    for line in proc.stdout:
        event = json.loads(line)
        if event["event"] == "delta":
            out += event["text"]
        elif event["event"] == "replace":
            out = event["text"]
        if event["event"] in ("done", "error"):
            last = event
            break
    proc.stdin.write(json.dumps({"id": 2, "cmd": "shutdown"}) + "\n")
    proc.stdin.flush()
    proc.wait(timeout=30)
    got = [p for p in out.split("\n\n") if p.strip()]
    print(f"{size}: input {len(text)} characters / {len(PARAGRAPHS)} paragraphs -> output {len(out)} characters / {len(got)} paragraphs")
    print("tags echoed:", "<text>" in out or "</text>" in out)
    print("end:", {k: last.get(k) for k in ("event", "code", "message", "seconds", "unloaded") if k in last})
    print("first:", got[0] if got else "-")
    print("last:", got[-1] if got else "-")


if __name__ == "__main__":
    main()
