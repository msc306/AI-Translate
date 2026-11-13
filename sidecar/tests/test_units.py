"""Unit tests without GPU or network. Run: .venv\\Scripts\\python sidecar\\tests\\test_units.py

Options:  --vector   also test the ChromaDB index (downloads the embedding model on first run)
          --claude   also translate one sentence through the Claude subscription (needs a login)
"""
import json
import sys
import tempfile
import threading
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import checks
import languages
import main as sidecar_main
import phrases
import prompting
import providers
import vector_index

APP_DIR = Path(__file__).resolve().parent.parent.parent
failures = []


def expect(name, condition, detail=""):
    print(("ok   " if condition else "FAIL ") + name + (f"  -> {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def test_languages():
    samples = {
        "de": "Ich habe heute keine Zeit, weil wir noch einkaufen müssen.",
        "en": "I do not have time today because we still have to go shopping.",
        "fr": "Je ne peux pas venir ce soir parce que nous avons du travail.",
        "es": "No puedo ir esta noche porque tenemos mucho trabajo que hacer.",
        "it": "Non posso venire questa sera perché abbiamo molto lavoro.",
        "nl": "Ik kan vanavond niet komen omdat we nog veel werk hebben.",
        "ru": "Я не могу прийти сегодня вечером, потому что у нас много работы.",
        "ja": "今日は仕事がたくさんあるので行けません。",
        "zh": "我今天晚上不能来，因为我们有很多工作。",
    }
    for code, text in samples.items():
        got, _ = languages.guess(text)
        expect(f"language guess {code}", got == code, f"got {got}")
    expect("detect restricted to candidates", languages.detect("Das ist ein Test", ["en", "de"]) == "de")
    expect("detect falls back to first", languages.detect("12345", ["en", "de"]) == "en")


def test_checks():
    src = "Ich habe heute keine Zeit, weil wir noch einkaufen müssen und danach kochen."
    good = "I don't have time today because we still have to go shopping and cook afterwards."
    expect("check passes good output", checks.check(src, good, "de", "en") == [])
    expect("check empty", checks.check(src, "  ", "de", "en") == ["empty"])
    expect("check untranslated", "untranslated" in checks.check(src, src, "de", "en"))
    expect("check wrong language", "wrong_language" in checks.check(
        src, "Ich habe heute keine Zeit, weil wir einkaufen und danach noch kochen müssen.", "de", "en"))
    expect("check too short", "too_short" in checks.check(src, "No time.", "de", "en"))
    expect("check too long", "too_long" in checks.check(src, good * 4, "de", "en"))
    expect("check ignores short text", checks.check("Hallo", "Hello", "de", "en") == [])


def test_phrases():
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        packs = phrases.load_packs((APP_DIR / "packs", "app"))
        expect("pack de-en loads", "de-en" in packs and len(packs["de-en"].entries) >= 20)
        book = phrases.PhraseBook(packs, work / "phrases.json")
        first = book.pairs("de", "en")[0]
        hit = book.exact(first["source"][0] + "!", "de", "en")
        expect("exact match ignores punctuation", bool(hit) and hit[0] == first["target"])
        hints = book.hints(f"Also ehrlich, {first['source'][0]} und dann ging es weiter.", "de", "en")
        expect("hint found inside sentence", any(h["id"] == first["id"] for h in hints))

        new_id = book.save("de", "en", "Das ist mir Wurst", "I couldn't care less")
        expect("user entry saved", book.exact("das ist mir wurst", "de", "en")[0] == "I couldn't care less")
        again = book.save("de", "en", "Das ist mir Wurst", "It's all the same to me")
        expect("correction updates instead of duplicating", again == new_id and len(book.user_entries) == 1)

        override = book.save("de", "en", first["source"], "OVERRIDE", first["id"])
        expect("user override wins over pack", book.exact(first["source"][0], "de", "en")[0] == "OVERRIDE")
        expect("pack file untouched", "OVERRIDE" not in (APP_DIR / "packs/de-en/phrases.json").read_text("utf-8"))

        reloaded = phrases.PhraseBook(packs, work / "phrases.json")
        expect("user entries persist", reloaded.exact(first["source"][0], "de", "en")[0] == "OVERRIDE")
        reloaded.delete(override)
        expect("deleted override stays hidden", reloaded.exact(first["source"][0], "de", "en") is None)

        archive = work / "fr.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("de-fr/manifest.json", json.dumps({
                "id": "de-fr", "name": "Deutsch ↔ Französisch",
                "languages": [{"code": "de", "name": "German"}, {"code": "fr", "name": "French"}]}))
            z.writestr("de-fr/phrases.json", json.dumps({"phrases": [{"de": "Guten Appetit", "fr": "Bon appétit"}]}))
        expect("pack install from zip", phrases.install_pack(archive, work / "packs") == "de-fr")
        merged = phrases.load_packs((APP_DIR / "packs", "app"), (work / "packs", "user"))
        book.set_packs(merged)
        expect("installed pack usable", book.exact("guten appetit", "de", "fr")[0] == "Bon appétit")
        bad = work / "bad.zip"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("manifest.json", json.dumps({"id": "../evil", "languages": [{"code": "de"}, {"code": "fr"}]}))
        try:
            phrases.install_pack(bad, work / "packs")
            expect("bad pack id rejected", False)
        except phrases.PackError:
            expect("bad pack id rejected", True)


def test_prompting():
    messages = prompting.build_messages(
        "Hallo Welt", "German", "English", hints=[("Hallo", "Hi")], similar=[("Welt", "world")],
        style="formal", style_notes="PACKNOTE", context=("Vorher", "Before"), retry_note="RETRY.")
    system = messages[0]["content"]
    expect("prompt has glossary", '"Hallo" => "Hi"' in system and "Mandatory" in system)
    expect("prompt has similar block", '"Welt" => "world"' in system and "Similar phrases" in system)
    expect("prompt has context", "<previous_translation>\nBefore" in system)
    expect("explicit style replaces pack notes", "formal, polite" in system and "PACKNOTE" not in system)
    expect("prompt has retry note", "RETRY." in system)
    expect("user message wraps the text in tags",
           messages[1] == {"role": "user", "content": "<text>\nHallo Welt\n</text>"})
    expect("echoed tags are removed", prompting.strip_wrapper("<text>\nHi\n</text>") == "Hi")
    expect("plain output stays untouched", prompting.strip_wrapper(" Hi\n") == " Hi\n")
    plain = prompting.build_messages("x", "German", "English", style_notes="PACKNOTE")[0]["content"]
    expect("neutral style keeps pack notes", "PACKNOTE" in plain and "{" not in plain)


def test_config_and_direction():
    with tempfile.TemporaryDirectory() as work:
        config = Path(work) / "config.json"
        config.write_text(json.dumps({"engine": {"api": {"enabled": True, "key": "sk-test"}},
                                      "memory": {"vector": False}}), encoding="utf-8")
        sidecar = sidecar_main.Sidecar(APP_DIR, config)
        cfg = sidecar.config()
        expect("old api config migrated", cfg["providers"]["claude_api"]["enabled"] is True
               and "api" not in cfg["engine"])
        public = sidecar.public_config()["providers"]["claude_api"]
        expect("key hidden from UI", public["key"] == "" and public["key_set"] is True)
        expect("auto direction de->en", sidecar._direction({}, "Das ist ein Test für die Richtung", ["de", "en"])
               == ("de", "en"))
        expect("short idiom is recognised by the phrase book",
               sidecar._direction({}, "Alles in Butter", ["de", "en"]) == ("de", "en"))
        expect("idiom in a long sentence leaves it to the detector",
               sidecar._direction({}, "My colleague keeps saying alles in Butter whenever I ask him about the project",
                                  ["de", "en"]) == ("en", "de"))
        expect("auto direction en->de", sidecar._direction({}, "This is a test for the direction", ["de", "en"])
               == ("en", "de"))
        expect("fixed target, same source flips", sidecar._direction(
            {"target": "en"}, "This is a test for the direction", ["de", "en"]) == ("de", "en"))
        expect("fixed pair respected", sidecar._direction(
            {"source": "en", "target": "fr"}, "whatever", ["de", "en"]) == ("en", "fr"))
        sidecar.save_config({"languages": {"enabled": ["de", "en", "fr", "xx"]}})
        expect("unknown language dropped", sidecar.config()["languages"]["enabled"] == ["de", "en", "fr"])
        status = sidecar.status()
        expect("status lists engines", [e["id"] for e in status["engines"]][:2] == ["local", "claude_api"])
        expect("status lists catalog", len(status["languages"]["catalog"]) == len(languages.CATALOG))


def test_vector():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as work:
        book = phrases.PhraseBook(phrases.load_packs((APP_DIR / "packs", "app")), Path(work) / "phrases.json")
        index = vector_index.VectorIndex(Path(work) / "memory")
        index.sync(book.documents())
        ready = index.wait()
        expect("vector index ready", ready, index.error)
        if not ready:
            return
        print(f"     indexed {index.count} texts")
        probes = [
            ("Ich glaube, ich werde verrückt, wenn das so weitergeht.", "de"),
            ("Das war wirklich kinderleicht für mich.", "de"),
            ("Honestly that exam was super easy.", "en"),
            ("Die Rechnung muss bis Freitag bezahlt werden.", "de"),
        ]
        for text, lang in probes:
            hits = index.query(text, lang, 3, 0.0)
            print(f"     {text!r}")
            for hit in hits:
                print(f"       {hit['similarity']:.2f}  {hit['text']}")
        book.save("de", "en", "Das ist mir Wurst", "I couldn't care less")
        index.sync(book.documents())
        index.wait()
        hits = index.query("Das ist mir Wurst", "de", 1, 0.9)
        expect("new entry searchable", bool(hits) and hits[0]["id"].startswith("user:"))


def test_claude_subscription():
    usage = providers.new_usage()
    messages = prompting.build_messages("Das ist ja wohl die Höhe!", "German", "English")
    cfg = {"enabled": True, "model": "haiku", "command": "claude"}
    try:
        text = "".join(providers.claude_sub(messages, cfg, threading.Event(), usage))
        print(f"     -> {text!r}  usage={usage}")
        expect("claude subscription translates", bool(text.strip()))
    except providers.EngineError as err:
        expect("claude subscription translates", False, str(err))


if __name__ == "__main__":
    test_languages()
    test_checks()
    test_phrases()
    test_prompting()
    test_config_and_direction()
    if "--vector" in sys.argv:
        test_vector()
    if "--claude" in sys.argv:
        test_claude_subscription()
    print(f"\n{len(failures)} failed" if failures else "\nall passed")
    sys.exit(1 if failures else 0)
