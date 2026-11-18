"""Unit tests without GPU or network. Run: .venv\\Scripts\\python sidecar\\tests\\test_units.py

Options:  --vector   also test the ChromaDB index (downloads the embedding model on first run)
          --claude   also translate one sentence through the Claude subscription (needs a login)
"""
import ast
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import checks
import downloads
import history
import i18n
import languages
import main as sidecar_main
import ocr
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
        "lt": "Aš šiandien negaliu ateiti, nes mes dar turime daug darbo ir jau vėlu.",
        "lv": "Es šovakar nevaru atnākt, jo mums vēl ir ļoti daudz darba un jau ir vēls.",
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


def test_history_and_export():
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        log = history.History(work / "history.json", limit=3)
        first = log.add(source="de", target="en", engine="local", model="m", style="neutral",
                        source_text="Guten Morgen", output="Good morning")
        second = log.add(source="de", target="en", engine="local", model="m", style="neutral",
                         source_text="Das ist; ein \"Test\"", output="This is a test")
        expect("history lists newest first", [e["id"] for e in log.items()] == [second, first])
        expect("history search", [e["id"] for e in log.items(query="morgen")] == [first])
        expect("correction is stored", log.correct(second, "This is; a \"test\"")
               and log.get(second)["corrected"] == "This is; a \"test\"")
        expect("same text is no correction", log.correct(first, "Good morning") and not log.get(first)["corrected"])
        expect("filter corrected only", [e["id"] for e in log.items(corrected_only=True)] == [second])
        expect("history survives a restart",
               len(history.History(work / "history.json").items()) == 2)

        expect("csv export counts", log.export(work / "out.csv", "csv") == 2)
        with open(work / "out.csv", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        expect("csv keeps quotes and separators", len(rows) == 3 and "This is; a \"test\"" in rows[1], str(rows))
        expect("json export of corrections", log.export(work / "out.json", "json", corrected_only=True) == 1
               and "Das ist" in (work / "out.json").read_text(encoding="utf-8"))
        expect("markdown export", log.export(work / "out.md", "md") == 2
               and "Guten Morgen" in (work / "out.md").read_text(encoding="utf-8"))
        try:
            log.export(work / "out.xyz", "xyz")
            expect("unknown export format is refused", False)
        except ValueError:
            expect("unknown export format is refused", True)

        for n in range(3):
            log.add(source="de", target="en", engine="local", model="m", style="neutral",
                    source_text=f"Text {n}", output=f"Text {n}")
        expect("history is capped", len(log.items()) == 3 and log.get(first) is None)
        log.delete(log.items()[0]["id"])
        expect("history delete", len(log.items()) == 2)
        log.clear()
        expect("history clear", log.items() == [])

        # corrections saved as phrases can be exported as a pack and installed again
        book = phrases.PhraseBook({}, work / "phrases.json")
        try:
            book.export_pack(work / "empty.zip")
            expect("empty phrase export is refused", False)
        except ValueError:
            expect("empty phrase export is refused", True)
        book.save("de", "en", "Das ist ein Test", "This is a trial")
        expect("phrase export counts", book.export_pack(work / "mine.zip") == 1)
        pack_id = phrases.install_pack(work / "mine.zip", work / "packs")
        again = phrases.PhraseBook(phrases.load_packs((work / "packs", "user")), work / "other.json")
        hit = again.exact("das ist ein test", "de", "en")
        expect("exported pack installs and translates", bool(pack_id) and hit and hit[0] == "This is a trial", str(hit))


def test_json_answers():
    expect("plain json", prompting.parse_json('{"a": 1}') == {"a": 1})
    expect("json in a code fence", prompting.parse_json('```json\n{"a": 1}\n```') == {"a": 1})
    expect("json with text around it", prompting.parse_json('Sure:\n{"a": {"b": "}"}}\nDone.') == {"a": {"b": "}"}})
    expect("no json", prompting.parse_json("OK") is None)
    expect("a list is no answer", prompting.parse_json("[1, 2]") is None)
    system = prompting.build_messages("Bank", "German", "English", clarification="a bench to sit on")[0]["content"]
    expect("clarification reaches the prompt", "a bench to sit on" in system)
    expect("no clarification leaves no gap", "{" not in prompting.build_messages("x", "German", "English")[0]["content"])
    for messages in (prompting.clarify_messages("Bank", "German", "English"),
                     prompting.explain_messages("Bank", "bank", "German", "English"),
                     prompting.review_messages("Bank", "bank", "German", "English", "formal")):
        expect("helper prompt is complete", len(messages) == 2 and "Bank" in messages[1]["content"]
               and "{src" not in messages[0]["content"] and "{tgt" not in messages[0]["content"],
               messages[0]["content"][:120])


def test_openrouter():
    import providers
    rows = providers.parse_openrouter_models({"data": [
        {"id": "x/paid", "name": "Paid", "pricing": {"prompt": "0.000003", "completion": "0.000015"},
         "context_length": 200000},
        {"id": "x/free:free", "name": "Free", "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "x/odd", "pricing": {"prompt": "-1", "completion": "x"}},
        {"name": "no id"},
    ]})
    by_id = {r["id"]: r for r in rows}
    expect("openrouter rows parsed", sorted(by_id) == ["x/free:free", "x/odd", "x/paid"], str(sorted(by_id)))
    expect("price per million tokens", by_id["x/paid"]["price_in"] == 3.0 and by_id["x/paid"]["price_out"] == 15.0)
    expect("free model flagged", by_id["x/free:free"]["free"] and not by_id["x/paid"]["free"])
    expect("unknown price stays unknown", by_id["x/odd"]["price_in"] is None and not by_id["x/odd"]["free"])
    expect("remembered price", providers.openrouter_price("x/paid") == (3.0, 15.0))

    def fake_sse(url, headers, body, cancel, name):
        expect("openrouter address", url == "https://openrouter.ai/api/v1/chat/completions", url)
        expect("openrouter asks for usage", body.get("usage") == {"include": True})
        yield {"choices": [{"delta": {"content": "Hallo"}}]}
        yield {"choices": [], "usage": {"prompt_tokens": 1000, "completion_tokens": 100}}

    original = providers._sse
    providers._sse = fake_sse
    try:
        usage = providers.new_usage()
        cfg = {"key": "sk-or-test", "model": "x/paid"}
        text = "".join(providers.openrouter([], cfg, threading.Event(), usage))
        expect("openrouter streams text", text == "Hallo")
        expect("cost from the price list", usage["cost_known"] and abs(usage["cost_usd"] - 0.0045) < 1e-9,
               str(usage))

        def sse_with_cost(url, headers, body, cancel, name):
            yield {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.25}}
        providers._sse = sse_with_cost
        usage = providers.new_usage()
        list(providers.openrouter([], cfg, threading.Event(), usage))
        expect("cost reported by openrouter wins", usage["cost_usd"] == 0.25)
    finally:
        providers._sse = original

    reasons = {e["id"]: e["reason"] for e in providers.availability({"openrouter": {"enabled": True}})}
    expect("openrouter needs a key", reasons.get("openrouter") == "API-Schlüssel fehlt", str(reasons.get("openrouter")))
    reasons = {e["id"]: e["reason"] for e in providers.availability({"openrouter": {"enabled": True, "key": "k"}})}
    expect("openrouter needs a model", reasons.get("openrouter") == "Modell fehlt", str(reasons.get("openrouter")))


def test_word_list():
    import textutil
    expect("single word is a list", textutil.word_list("Bank") == ["Bank"])
    expect("lines are a list", textutil.word_list("- Bank\n- Schloss\n\n3. Leiter") == ["Bank", "Schloss", "Leiter"])
    expect("comma list", textutil.word_list("Bank, Schloss; Kiefer") == ["Bank", "Schloss", "Kiefer"])
    expect("short expression counts", textutil.word_list("auf jeden Fall") == ["auf jeden Fall"])
    expect("sentence is not a list", textutil.word_list("Ich gehe heute zur Bank.") is None)
    expect("short sentence with full stop is not a list", textutil.word_list("Komm her.") is None)
    expect("long list is not a word list", textutil.word_list("\n".join(f"Wort{i}" for i in range(20))) is None)
    expect("numbers alone are not words", textutil.word_list("42") is None)
    expect("duplicates removed", textutil.word_list("Bank\nBank") == ["Bank"])
    rows = sidecar_main.clean_senses({"words": [{"word": "bank", "senses": [{"translation": "x"}] * 6}]}, ["Bank"])
    expect("senses matched by name, capped at 4", rows and rows[0]["word"] == "Bank" and len(rows[0]["senses"]) == 4)
    broken = ('{"words": [{"word": "Schloss", "senses": [{"translation": "castle"}]}], '
              '[{"word": "Leiter", "senses": [{"translation": "ladder"}]}]}')
    rows = sidecar_main.clean_senses(sidecar_main.word_objects(broken), ["Schloss", "Leiter"])
    expect("word objects recovered from broken list", [r["word"] for r in rows] == ["Schloss", "Leiter"], str(rows))
    expect("broken senses answer gives nothing", sidecar_main.clean_senses({"words": "x"}, ["Bank"]) == []
           and sidecar_main.clean_senses(None, ["Bank"]) == [])


def run_fake(side, request, answers, method="translate"):
    """Run one request against scripted model answers; return (events, prompts seen by the model)."""
    events, prompts = [], []
    script = list(answers)

    def fake_stream(engine, messages, providers_cfg, cancel, usage):
        prompts.append(messages)
        yield script.pop(0)

    real_emit, real_stream = sidecar_main.emit, providers.stream
    sidecar_main.emit, providers.stream = events.append, fake_stream
    try:
        getattr(side, method)({"id": 1, "engine": "claude_sub", **request})
    finally:
        sidecar_main.emit, providers.stream = real_emit, real_stream
    return events, prompts


def test_modes():
    with tempfile.TemporaryDirectory() as work:
        config = Path(work) / "config.json"
        config.write_text(json.dumps({"memory": {"vector": False}}), encoding="utf-8")
        side = sidecar_main.Sidecar(APP_DIR, config)
        text = "Ich gehe heute Nachmittag noch schnell zur Bank."
        last = lambda events: events[-1]

        # clarifying question
        question = json.dumps({"ambiguous": True, "question": "Welche Bank?", "options": [
            {"label": "Geldinstitut", "meaning": "the financial institution"},
            {"label": "Sitzbank", "meaning": "a bench to sit on"}]})
        events, _ = run_fake(side, {"text": text, "clarify": True}, [question])
        expect("ambiguous text asks back", last(events)["event"] == "question"
               and len(last(events)["options"]) == 2, str(last(events)))
        expect("a question writes no history", side.history.items() == [])
        events, prompts = run_fake(side, {"text": text, "clarify": True, "clarification": "a bench to sit on"},
                                   ["I am quickly going to the bench this afternoon."])
        expect("answer is used without asking again", last(events)["event"] == "done" and len(prompts) == 1
               and "a bench to sit on" in prompts[0][0]["content"], str(last(events)))
        events, prompts = run_fake(side, {"text": text, "clarify": True},
                                   ['{"ambiguous": false}', "I am quickly going to the bank this afternoon."])
        expect("clear text is translated directly", last(events)["event"] == "done" and len(prompts) == 2)
        events, prompts = run_fake(side, {"text": text, "clarify": True},
                                   ["no idea", "I am quickly going to the bank this afternoon."])
        expect("unusable clarify answer does not block", last(events)["event"] == "done")
        events, prompts = run_fake(side, {"text": text}, ["I am quickly going to the bank this afternoon."])
        expect("no question unless switched on", len(prompts) == 1 and last(events)["event"] == "done")
        expect("short english sentence is recognised", side._direction({}, "She saw her duck.", ["de", "en"]) == ("en", "de")
               and side._direction({}, "Er sah ihn.", ["de", "en"]) == ("de", "en"))

        # thorough mode
        draft = "I become quickly to the bank this afternoon."
        fixed = "I am quickly going to the bank this afternoon."
        events, _ = run_fake(side, {"text": text, "thorough": True},
                             [draft, json.dumps({"issues": ["'become' is a false friend"], "improved": fixed})])
        done = last(events)
        replaced = [e["text"] for e in events if e["event"] == "replace"]
        expect("review corrects the draft", done.get("review") == {"changed": 1, "issues": ["'become' is a false friend"]}
               and replaced == [fixed], str(done))
        expect("history stores the corrected text", side.history.get(done["history_id"])["output"] == fixed)
        events, _ = run_fake(side, {"text": text, "thorough": True}, [fixed, json.dumps({"issues": [], "improved": fixed})])
        expect("review leaves a good draft alone", last(events)["review"] == {"changed": 0, "issues": []}
               and not [e for e in events if e["event"] == "replace"])
        events, _ = run_fake(side, {"text": text, "thorough": True},
                             [fixed, json.dumps({"issues": ["x"], "improved": "Ich gehe heute Nachmittag noch schnell zur Bank."})])
        expect("review cannot swap in an untranslated text", last(events)["review"]["changed"] == 0)
        events, _ = run_fake(side, {"text": text, "thorough": True}, [fixed, "not json"])
        expect("unusable review keeps the draft", last(events)["event"] == "done" and last(events)["review"]["changed"] == 0)

        # single words: meanings with examples
        senses = json.dumps({"words": [{"word": "Bank", "senses": [
            {"translation": "bank", "meaning": "Geldinstitut", "example": "Ich gehe zur Bank.",
             "example_translation": "I am going to the bank."},
            {"translation": "bench", "meaning": "Sitzbank", "example": "Wir sitzen auf der Bank.",
             "example_translation": "We are sitting on the bench."}, {"meaning": "no translation"}]}]})
        events, prompts = run_fake(side, {"text": "Bank", "source": "de", "target": "en"}, ["bank", senses])
        done = last(events)
        expect("single word gets meanings", done["event"] == "done" and len(prompts) == 2
               and [s["translation"] for s in done.get("senses", [{}])[0].get("senses", [])] == ["bank", "bench"],
               str(done))
        expect("meanings prompt lists the word as material", "<words>\nBank\n</words>" in prompts[1][1]["content"])
        events, prompts = run_fake(side, {"text": "Bank", "source": "de", "target": "en"}, ["bank", "nonsense"])
        expect("unusable meanings keep the translation", last(events)["event"] == "done"
               and "senses" not in last(events))
        events, prompts = run_fake(side, {"text": "Bank", "source": "de", "target": "en", "senses": False}, ["bank"])
        expect("meanings can be switched off", len(prompts) == 1 and "senses" not in last(events))
        events, prompts = run_fake(side, {"text": text}, [fixed])
        expect("a sentence gets no meanings step", len(prompts) == 1)

        # history switch per request (used by the MCP server)
        before = len(side.history.items())
        events, _ = run_fake(side, {"text": text, "history": False}, [fixed])
        expect("request can skip the history", "history_id" not in last(events) and len(side.history.items()) == before)

        # explain mode
        answer = json.dumps({"summary": "Passt.", "alternatives": [{"text": "I'm popping to the bank.", "note": "lockerer"}, {"note": "leer"}],
                             "notes": [{"source": "noch schnell", "note": "beiläufig"}]})
        events, prompts = run_fake(side, {"text": text, "translation": fixed, "source": "de", "target": "en"},
                                   [answer], method="explain")
        result = last(events)
        expect("explanation is returned", result["event"] == "explanation" and result["summary"] == "Passt."
               and len(result["alternatives"]) == 1 and result["notes"][0]["source"] == "noch schnell", str(result))
        expect("explain prompt holds both texts", text in prompts[0][1]["content"] and fixed in prompts[0][1]["content"])
        events, _ = run_fake(side, {"text": text, "translation": fixed}, ["blah"], method="explain")
        expect("unusable explanation is an error", last(events).get("code") == "explain_failed")
        events, _ = run_fake(side, {"text": "", "translation": ""}, [], method="explain")
        expect("nothing to explain", last(events).get("code") == "nothing_to_explain")

        # commands of the protocol
        def command(request):
            got = []
            real = sidecar_main.emit
            sidecar_main.emit = got.append
            try:
                side.handle({"id": 2, **request})
            finally:
                sidecar_main.emit = real
            return got[-1]
        listing = command({"cmd": "history"})
        entry = listing["items"][0]
        expect("history command lists", listing["event"] == "history" and listing["total"] == len(listing["items"]) > 0)
        fixed_by_user = command({"cmd": "history_correct", "entry_id": entry["id"], "text": "My own wording."})
        expect("history_correct stores", fixed_by_user["items"][0]["corrected"] == "My own wording.")
        out = Path(work) / "export.csv"
        exported = command({"cmd": "history_export", "path": str(out), "corrected_only": True})
        expect("history_export writes the file", exported["event"] == "exported" and exported["count"] == 1 and out.exists(),
               str(exported))
        bad = command({"cmd": "history_export", "path": str(Path(work) / "missing" / "x.csv")})
        expect("export into a missing folder is an error", bad.get("code") == "export_failed", str(bad))
        nothing = command({"cmd": "phrases_export", "path": str(Path(work) / "p.zip")})
        expect("phrase export without entries is an error", nothing.get("code") == "export_failed", str(nothing))
        command({"cmd": "phrase_save", "source": "de", "target": "en", "source_text": text, "target_text": "My own wording."})
        packed = command({"cmd": "phrases_export", "path": str(Path(work) / "p.zip")})
        expect("phrase export writes a pack", packed.get("count") == 1 and zipfile.is_zipfile(Path(work) / "p.zip"), str(packed))
        events, prompts = run_fake(side, {"text": text}, [])
        expect("saved correction answers next time", last(events)["engine"] == "phrasebook" and not prompts
               and [e["text"] for e in events if e["event"] == "delta"] == ["My own wording."], str(last(events)))
        expect("history_clear empties", command({"cmd": "history_clear"})["items"] == [])


def test_mcp():
    """Protocol of the MCP server without starting a model."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as work:
        config = Path(work) / "config.json"
        config.write_text(json.dumps({"memory": {"vector": False}}), encoding="utf-8")
        child = subprocess.Popen(
            [sys.executable, str(APP_DIR / "sidecar" / "mcp_server.py"), "--config", str(config)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, encoding="utf-8")

        def ask(method, params=None, msg_id=1):
            child.stdin.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}) + "\n")
            child.stdin.flush()
            return json.loads(child.stdout.readline())
        try:
            hello = ask("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                       "clientInfo": {"name": "test", "version": "0"}})
            expect("mcp initialize", hello["result"]["serverInfo"]["name"] == "ai-translate"
                   and hello["result"]["protocolVersion"] == "2025-06-18", str(hello))
            child.stdin.write('{"jsonrpc": "2.0", "method": "notifications/initialized"}\n')
            tools = ask("tools/list", msg_id=2)["result"]["tools"]
            expect("mcp lists its tools", [t["name"] for t in tools] == ["translate", "explain_translation", "list_languages"])
            listed = ask("tools/call", {"name": "list_languages", "arguments": {}}, 3)["result"]
            data = json.loads(listed["content"][0]["text"])
            expect("mcp list_languages", not listed["isError"] and {"de", "en"} <= {l["code"] for l in data["languages"]}
                   and "neutral" in data["styles"], str(listed))
            hit = ask("tools/call", {"name": "translate", "arguments": {"text": "Alles in Butter", "target": "en"}}, 4)["result"]
            expect("mcp translate answers from the phrase book", not hit["isError"]
                   and "phrasebook" in hit["content"][0]["text"], str(hit))
            empty = ask("tools/call", {"name": "translate", "arguments": {"text": " "}}, 5)["result"]
            expect("mcp reports tool errors", empty["isError"] is True)
            expect("mcp unknown method", ask("nope", msg_id=6)["error"]["code"] == -32601)
        finally:
            child.stdin.close()
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                child.kill()
                expect("mcp server exits when its input closes", False)


def test_downloads():
    """Downloader against a local HTTP server: checksum, resume, runtime unpacking, bad checksum."""
    import hashlib
    import http.server
    import io
    import downloads

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as work:
        work = Path(work)
        exe_zip = io.BytesIO()
        with zipfile.ZipFile(exe_zip, "w") as bundle:
            bundle.writestr("build/bin/llama-server.exe", b"exe")
            bundle.writestr("build/bin/ggml.dll", b"dll")
            bundle.writestr("../evil.txt", b"x")
        lib_zip = io.BytesIO()
        with zipfile.ZipFile(lib_zip, "w") as bundle:
            bundle.writestr("cudart64_12.dll", b"cuda")
        model = bytes(range(256)) * 9000
        files = {"/rt.zip": exe_zip.getvalue(), "/lib.zip": lib_zip.getvalue(), "/m.gguf": model,
                 "/slow.gguf": model}
        requests = []
        stalled = threading.Event()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = files.get(self.path)
                if body is None:
                    self.send_error(404)
                    return
                if self.path == "/slow.gguf" and not stalled.is_set():
                    # first request: answer the headers, then never send a byte
                    stalled.set()
                    requests.append(("stall", self.path, 0))
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.flush()
                    time.sleep(8)
                    return
                start = 0
                if self.headers.get("Range"):
                    start = int(self.headers["Range"].split("=")[1].rstrip("-"))
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{len(body) - 1}/{len(body)}")
                    requests.append(("range", self.path, start))
                else:
                    self.send_response(200)
                self.send_header("Content-Length", str(len(body) - start))
                self.end_headers()
                self.wfile.write(body[start:])

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}"

        def spec(name, path, data, sha=None):
            return {"name": name, "url": base + path, "sha256": sha or hashlib.sha256(data).hexdigest(), "size_mb": 1}

        catalog = {
            "runtime": {"kind": "runtime", "label": "rt", "size_mb": 1,
                        "files": [spec("rt.zip", "/rt.zip", files["/rt.zip"]), spec("lib.zip", "/lib.zip", files["/lib.zip"])]},
            "model_small": {"kind": "model", "label": "m", "size_mb": 1, "files": [spec("m.gguf", "/m.gguf", model)]},
            "broken": {"kind": "model", "label": "b", "size_mb": 1, "files": [spec("b.gguf", "/m.gguf", model, "0" * 64)]},
            "slow": {"kind": "model", "label": "s", "size_mb": 1, "files": [spec("s.gguf", "/slow.gguf", model)]},
        }
        events = []
        loader = downloads.Downloader(work / "data", events.append, catalog, allow_http=True)
        loader.stall_seconds = 2
        try:
            (work / "data" / "downloads").mkdir(parents=True)
            (work / "data" / "downloads" / "m.gguf.part").write_bytes(model[:1000])  # interrupted earlier
            for item in ("runtime", "model_small", "broken", "slow"):
                loader.start(item, item)
            loader.wait(30)
        finally:
            server.shutdown()
        final = {e["item"]: e for e in events if e["state"] in ("done", "error", "cancelled")}
        runtime = work / "data" / "runtime"
        expect("download unpacks the runtime flat", final["runtime"]["state"] == "done"
               and (runtime / "llama-server.exe").is_file() and (runtime / "ggml.dll").is_file()
               and (runtime / "cudart64_12.dll").is_file(), str(final.get("runtime")))
        expect("download skips unsafe archive paths", not (work / "data" / "evil.txt").exists()
               and not (runtime / "evil.txt").exists())
        target = work / "data" / "models" / "m.gguf"
        expect("download resumes and verifies the model", final["model_small"]["state"] == "done"
               and target.is_file() and target.read_bytes() == model, str(final.get("model_small")))
        expect("download resumes with a range request", ("range", "/m.gguf", 1000) in requests, str(requests))
        expect("download rejects a wrong checksum", final["broken"]["state"] == "error"
               and "Prüfsumme" in final["broken"]["message"] and not (work / "data" / "models" / "b.gguf").exists())
        if downloads.CURL.is_file():
            expect("download restarts a stalled transfer", final["slow"]["state"] == "done"
                   and (work / "data" / "models" / "s.gguf").read_bytes() == model, str(final.get("slow")))
        state = {s["item"]: s for s in loader.state()}
        expect("download state reports installed items", state["runtime"]["installed"] and state["model_small"]["installed"]
               and not state["broken"]["installed"])


def test_hardware():
    """Graphics card choice on Windows, also when the tests run on a Mac or Linux."""
    import local_engine
    import platform_info

    saved = (platform_info.SYSTEM, local_engine.SERVER_EXE)
    platform_info.SYSTEM, local_engine.SERVER_EXE = "windows", "llama-server.exe"
    try:
        _check_windows_hardware()
    finally:
        platform_info.SYSTEM, local_engine.SERVER_EXE = saved


def _check_windows_hardware():
    """Auto detection, backend, runtime lookup and llama-server arguments."""
    import gpu
    import local_engine

    nvidia = {"name": "NVIDIA GeForce RTX 5090", "vendor": "nvidia", "dedicated_mb": 32000, "integrated": False}
    intel = {"name": "Intel(R) UHD Graphics 770", "vendor": "intel", "dedicated_mb": 128, "integrated": True}
    amd = {"name": "AMD Radeon RX 7800 XT", "vendor": "amd", "dedicated_mb": 16000, "integrated": False}
    expect("auto picks the dedicated card", gpu.resolve("auto", [nvidia, intel])["backend"] == "cuda")
    expect("amd runs on vulkan", gpu.resolve("auto", [amd, intel])["vendor"] == "amd"
           and gpu.resolve("auto", [amd])["backend"] == "vulkan")
    expect("only an integrated intel card", gpu.resolve("auto", [intel])["backend"] == "vulkan")
    expect("no card means processor", gpu.resolve("auto", [])["backend"] == "cpu")
    chosen = gpu.resolve("intel", [nvidia, intel])
    expect("a chosen card wins", chosen["vendor"] == "intel" and chosen["card"]["name"] == intel["name"])
    expect("unknown choice falls back to auto", gpu.resolve("voodoo", [nvidia])["choice"] == "auto")
    windows_items = downloads.runtime_items("windows", "x64")
    expect("every windows backend has a runtime download",
           all(windows_items[gpu.BACKENDS[v]] in downloads.CATALOG for v in ("nvidia", "amd", "intel", "cpu")))
    expect("processor arguments keep the model off the card",
           local_engine.device_args("cpu") == ["-ngl", "0", "--device", "none"])
    expect("vulkan arguments pin the card", local_engine.device_args("vulkan", "Vulkan1")[-2:] == ["--device", "Vulkan1"]
           and local_engine.device_args("cuda") == ["-ngl", "999"])

    with tempfile.TemporaryDirectory() as work:
        app = Path(work)
        (app / "runtime-vulkan").mkdir()
        (app / "runtime-vulkan" / "llama-server.exe").write_bytes(b"")
        saved = {k: os.environ.get(k) for k in ("AI_TRANSLATE_LMSTUDIO", "AI_TRANSLATE_DATA")}
        os.environ["AI_TRANSLATE_LMSTUDIO"] = str(app / "no-lmstudio")  # no LM Studio backends in the way
        os.environ["AI_TRANSLATE_DATA"] = str(app / "data")
        try:
            exe, _ = local_engine.find_llama_server("auto", app, "vulkan")
            expect("vulkan runtime is found", exe.parent.name == "runtime-vulkan", str(exe))
            exe, _ = local_engine.find_llama_server("auto", app, "cpu")
            expect("processor falls back to a gpu build", exe.parent.name == "runtime-vulkan", str(exe))
            try:
                local_engine.find_llama_server("auto", app, "cuda")
                expect("cuda does not take the vulkan build", False)
            except local_engine.EngineError:
                pass
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def test_platform():
    """macOS and Linux paths with an injected platform: they cannot run on this Windows PC."""
    import gpu
    import local_engine
    import platform_info
    import speech
    import tarfile
    import io

    expect("describe apple silicon", platform_info.describe("macos", "arm64")
           == {"os": "macos", "arch": "arm64", "label": "macOS (Apple Silicon)"})
    expect("describe intel mac", platform_info.describe("macos", "x64")["label"] == "macOS (Intel)")
    expect("describe windows", platform_info.describe("windows", "x64")["label"] == "Windows (x64)")
    here = platform_info.describe()
    expect("describe this machine", here["os"] in ("windows", "macos", "linux") and here["arch"] in ("arm64", "x64"))
    expect("exe names", platform_info.exe_name("llama-server", "windows") == "llama-server.exe"
           and platform_info.exe_name("llama-server", "macos") == "llama-server")

    home = Path("/Users/test")
    mac_dir = home / "Library" / "Application Support" / "AITranslate"
    expect("mac config folder", platform_info.config_dir("macos", {}, home) == mac_dir)
    expect("mac data folder", platform_info.data_dir("macos", {}, home) == mac_dir)
    expect("data override wins on mac",
           platform_info.data_dir("macos", {"AI_TRANSLATE_DATA": "/x"}, home) == Path("/x"))
    expect("windows folders unchanged",
           platform_info.config_dir("windows", {"APPDATA": r"C:\R"}, home) == Path(r"C:\R") / "AITranslate"
           and platform_info.data_dir("windows", {"LOCALAPPDATA": r"C:\L"}, home) == Path(r"C:\L") / "AITranslate")
    expect("linux xdg folders",
           platform_info.config_dir("linux", {"XDG_CONFIG_HOME": "/c"}, home) == Path("/c/AITranslate")
           and platform_info.data_dir("linux", {}, home) == home / ".local" / "share" / "AITranslate")

    # graphics: an Apple Silicon Mac
    card = gpu.mac_card("Apple M3 Pro\n", str(36 * 2**30))
    expect("apple card", card["vendor"] == "apple" and card["name"] == "Apple M3 Pro" and card["dedicated_mb"] == 36864)
    on_mac = gpu.resolve("auto", [card], system="macos")
    expect("apple silicon uses metal", on_mac["vendor"] == "apple" and on_mac["backend"] == "metal")
    expect("nvidia on a mac falls back to auto", gpu.resolve("nvidia", [card], system="macos")["vendor"] == "apple")
    expect("intel mac runs on the processor", gpu.resolve("auto", [], system="macos")["backend"] == "cpu")
    expect("apple on windows falls back to auto", gpu.resolve("apple", [], system="windows")["choice"] == "auto")
    expect("processor can be chosen on a mac", gpu.resolve("cpu", [card], system="macos")["backend"] == "cpu")
    vm_stat = ("Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
               "Pages free:                               100000.\nPages active:  5.\n"
               "Pages inactive:                           50000.\n")
    state = gpu.mac_vram(32 * 2**30, vm_stat)
    expect("unified memory budget is 75 percent", state["total"] == 24576)
    expect("free memory from vm_stat", state["free"] == 150000 * 16384 // 2**20, str(state))
    expect("free memory capped at the budget", gpu.mac_vram(8 * 2**30, vm_stat.replace("100000", "9000000"))["free"] == 6144)
    expect("metal offloads every layer", local_engine.device_args("metal") == ["-ngl", "999"])

    # downloads per platform
    mac_arm = downloads.runtime_items("macos", "arm64")
    expect("apple silicon runtime", mac_arm == {"metal": "runtime_metal", "cpu": "runtime_metal"})
    expect("intel mac runtime", downloads.runtime_items("macos", "x64") == {"cpu": "runtime_mac_cpu"})
    arm_catalog = downloads.platform_catalog("macos", "arm64")
    expect("mac offers no windows downloads", not {"runtime", "runtime_vulkan", "runtime_cpu", "whisper"} & set(arm_catalog))
    expect("apple silicon offers metal only", "runtime_metal" in arm_catalog and "runtime_mac_cpu" not in arm_catalog)
    expect("mac keeps models", {"model_small", "speech_model"} <= set(arm_catalog))
    win_catalog = downloads.platform_catalog("windows", "x64")
    expect("windows offers no mac downloads", not {"runtime_metal", "runtime_mac_cpu"} & set(win_catalog)
           and {"runtime", "runtime_vulkan", "runtime_cpu", "whisper"} <= set(win_catalog))
    metal = downloads.CATALOG["runtime_metal"]["files"][0]
    expect("metal archive pinned", metal["sha256"].startswith("e815561e") and metal["name"].endswith("macos-arm64.tar.gz"))
    expect("mac runtimes have labels", all(i18n.CATALOG.get(downloads.CATALOG[k]["label"])
                                           for k in ("runtime_metal", "runtime_mac_cpu")))
    expect("mac backends search mac folders", local_engine.fallback_backends("cpu", "macos") == ["cpu", "metal"]
           and local_engine.fallback_backends("cpu", "windows") == ["cpu", "vulkan", "cuda"])

    # a macOS .tar.gz like llama.cpp's: flat folder, dylib symlinks, and hostile members
    def add(bundle, name, data=b"", mode=0o644, link=None, kind=tarfile.REGTYPE):
        info = tarfile.TarInfo(name)
        info.mode = mode
        info.type = kind
        if link is not None:
            info.linkname = link
        else:
            info.size = len(data)
        bundle.addfile(info, io.BytesIO(data) if link is None else None)

    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        archive = work / "llama-b12360-bin-macos-arm64.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            add(bundle, "llama-b12360/", kind=tarfile.DIRTYPE, mode=0o755)
            add(bundle, "llama-b12360/llama-server", b"#!binary", 0o755)
            add(bundle, "llama-b12360/libggml.1.0.0.dylib", b"DYLIB")
            add(bundle, "llama-b12360/libggml.1.dylib", link="libggml.1.0.0.dylib", kind=tarfile.SYMTYPE)
            add(bundle, "llama-b12360/libggml.dylib", link="libggml.1.dylib", kind=tarfile.SYMTYPE)
            add(bundle, "llama-b12360/evil.dylib", link="../../../etc/passwd", kind=tarfile.SYMTYPE)
            add(bundle, "llama-b12360/abs.dylib", link="/etc/passwd", kind=tarfile.SYMTYPE)
            add(bundle, "llama-b12360/../escape.txt", b"x")
            add(bundle, "llama-b12360/fifo", kind=tarfile.FIFOTYPE)
        target = work / "data" / "runtime-metal"
        downloads._install_runtime([archive], target, "llama-server")
        expect("tar: llama-server installed", (target / "llama-server").read_bytes() == b"#!binary")
        expect("tar: dylib chain usable", (target / "libggml.dylib").read_bytes() == b"DYLIB"
               and (target / "libggml.1.dylib").read_bytes() == b"DYLIB")
        expect("tar: escaping links skipped", not (target / "evil.dylib").exists() and not (target / "abs.dylib").exists())
        expect("tar: traversal skipped", not (work / "data" / "escape.txt").exists() and not (target / "fifo").exists())
        expect("tar: no staging left", not (work / "data" / "runtime-metal.new").exists())
        broken = work / "broken.tar.gz"
        with tarfile.open(broken, "w:gz") as bundle:
            add(bundle, "llama-b12360/libggml.dylib", b"x")
        try:
            downloads._install_runtime([broken], work / "data" / "runtime-x", "llama-server")
            expect("tar without llama-server fails", False)
        except downloads.DownloadError:
            expect("tar without llama-server fails", not (work / "data" / "runtime-x").exists())

    # speech input on a Mac
    found = {"ffmpeg": "/opt/homebrew/bin/ffmpeg"}
    command = speech.recorder_command(Path("/tmp/a.wav"), "macos", found.get)
    expect("mac records with ffmpeg avfoundation", command[0] == "/opt/homebrew/bin/ffmpeg"
           and command[command.index("-f") + 1] == "avfoundation" and "16000" in command)
    sox = speech.recorder_command(Path("/tmp/a.wav"), "macos", {"rec": "/usr/local/bin/rec"}.get)
    expect("mac falls back to sox", sox[0] == "/usr/local/bin/rec")
    expect("no recorder is reported", speech.recording_problem("macos", {}.get).startswith("Für die Aufnahme fehlt")
           and speech.recording_problem("windows") == "")

    # OCR boxes from Vision (normalized, origin bottom left) to pixels with origin top left
    box = ocr.vision_box({"bx": 0.1, "by": 0.8, "bw": 0.5, "bh": 0.1}, 1000, 500)
    expect("vision box to pixels", box == {"x": 100, "y": 50, "w": 500, "h": 50}, str(box))
    lines = ocr.mac_lines({"width": 1000, "height": 1000, "lines": [
        {"text": "First line", "bx": 0.1, "by": 0.85, "bw": 0.4, "bh": 0.05},
        {"text": "second line", "bx": 0.1, "by": 0.78, "bw": 0.4, "bh": 0.05}]})
    expect("vision lines keep reading order", lines[0]["y"] < lines[1]["y"]
           and "First line" in ocr.layout_text(lines, "en-US"))

    # status_info reports the platform
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as work:
        config = Path(work) / "config.json"
        config.write_text(json.dumps({"memory": {"vector": False}}), encoding="utf-8")
        saved = os.environ.get("AI_TRANSLATE_DATA")
        os.environ["AI_TRANSLATE_DATA"] = str(Path(work) / "data")
        try:
            car = sidecar_main.Sidecar(APP_DIR, config)
            info = car.status()
            expect("status_info has platform", info.get("platform") == platform_info.describe())
            expect("speech_info says whether it can record", "can_record" in info["speech"])
        finally:
            if saved is None:
                os.environ.pop("AI_TRANSLATE_DATA", None)
            else:
                os.environ["AI_TRANSLATE_DATA"] = saved


def test_ocr():
    """Layout of recognised lines, and the recogniser itself where Windows provides one."""
    import ocr

    def line(text, x, y, w, h=20):
        return {"text": text, "x": x, "y": y, "w": w, "h": h}

    prose = [line("This is a long line of prose that runs to the edge", 10, 10, 600),
             line("and goes on in the next line.", 10, 36, 300),
             line("A second paragraph starts here.", 10, 100, 320)]
    expect("ocr joins wrapped lines and keeps paragraphs", ocr.layout_text(prose, "en")
           == "This is a long line of prose that runs to the edge and goes on in the next line.\n\n"
              "A second paragraph starts here.", repr(ocr.layout_text(prose, "en")))
    menu = [line("File", 10, 10, 40), line("Edit", 10, 36, 40), line("View", 10, 62, 44)]
    expect("ocr keeps short lines apart", ocr.layout_text(menu, "en") == "File\nEdit\nView",
           repr(ocr.layout_text(menu, "en")))
    expect("ocr handles no lines", ocr.layout_text([], "en") == "")
    # the recogniser reports the labels of a list as a column of their own
    choices = [line("A.", 160, 240, 50, 40), line("B.", 160, 380, 50, 40),
               line("To serve as the engine", 350, 240, 900, 55), line("To manage the context", 350, 380, 900, 55)]
    expect("ocr puts labels beside their lines", ocr.layout_text(choices, "en")
           == "A. To serve as the engine\n\nB. To manage the context", repr(ocr.layout_text(choices, "en")))
    columns = [line("Left column of prose text", 10, 10, 600), line("Right column of prose text", 700, 10, 600)]
    expect("ocr leaves columns of prose apart", "\n" in ocr.layout_text(columns, "en"),
           repr(ocr.layout_text(columns, "en")))
    try:
        ocr.read_image(path=str(Path(tempfile.gettempdir()) / "tt-no-such-image.png"))
        expect("ocr reports a missing file", False)
    except ocr.OcrError as err:
        expect("ocr reports a missing file", err.code in ("no_file", "unsupported", "no_language"), err.code)

    events = []
    original = sidecar_main.emit
    sidecar_main.emit = events.append
    try:
        sidecar_main.Sidecar.read_image(None, {"id": 7, "path": "tt-no-such-image.png", "lang": "auto"})
    finally:
        sidecar_main.emit = original
    expect("ocr command answers with an error event", len(events) == 1 and events[0]["id"] == 7
           and events[0]["event"] == "error" and events[0]["code"].startswith("ocr_"), str(events))


def _placeholders(text):
    return sorted(set(re.findall(r"\{(\w*)\}", text)))


def test_i18n_catalog():
    for source, entry in i18n.CATALOG.items():
        missing = [code for code in ("en", "es", "fr") if not str(entry.get(code) or "").strip()]
        expect(f"catalog entry is complete: {source[:40]}", not missing, f"missing {missing}")
        wrong = [code for code in ("en", "es", "fr") if code in entry
                 and _placeholders(entry[code]) != _placeholders(source)]
        expect(f"catalog placeholders match: {source[:40]}", not wrong, f"differs in {wrong}")

    # Every German text the code passes to tr(), directly or from a module-level table, has an entry.
    sources = set(checks.MESSAGES.values()) | set(ocr.MESSAGES.values()) | set(providers.LABELS.values())
    sources |= {value[0] for value in prompting.STYLES.values()}
    sources |= {entry["label"] for entry in downloads.CATALOG.values()}
    sources |= {value[1] for value in languages.CATALOG.values()}
    calls = 0
    for path in sorted((APP_DIR / "sidecar").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "tr"
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                calls += 1
                sources.add(node.args[0].value)
                given = sorted(k.arg for k in node.keywords if k.arg)
                expect(f"tr() call fills its placeholders: {path.name}:{node.lineno}",
                       given == _placeholders(node.args[0].value), f"{given}")
        for reason in re.findall(r'reason = "([^"]+)"', path.read_text(encoding="utf-8")):
            sources.add(reason)
    unknown = sorted(s for s in sources if s not in i18n.CATALOG)
    expect("every text passed to tr() is in the catalog", calls > 50 and not unknown, f"{calls} calls, {unknown}")


def test_i18n_switch():
    expect("tests start in German", i18n.get_language() == "de")
    expect("german is the source text", i18n.tr("Unbekannter Befehl: {cmd}", cmd="x") == "Unbekannter Befehl: x")
    expect("text without an entry stays as it is", i18n.tr("Kein Eintrag {n}", n=3) == "Kein Eintrag 3")

    def engine_error():
        try:
            list(providers.stream("nope", [], {}, threading.Event(), {}))
        except sidecar_main.EngineError as err:
            return str(err)
        return ""

    def style_label():
        return i18n.tr(prompting.STYLES["formal"][0])

    def engine_label():
        return providers.availability({})[1]["label"]

    german = (engine_error(), style_label(), engine_label(), checks.warnings(["empty"])[0]["message"],
              str(ocr.OcrError("no_text")))
    expect("german error message", german[0] == "Unbekannter Anbieter: nope", german[0])
    expect("german labels", german[1] == "Förmlich" and german[2] == "Claude (API-Schlüssel)", str(german[1:3]))
    try:
        seen = {"de": german}
        for code, error, style, engine in (("en", "Unknown provider: nope", "Formal", "Claude (API key)"),
                                           ("es", "Proveedor desconocido: nope", "Formal", "Claude (clave de API)"),
                                           ("fr", "Fournisseur inconnu : nope", "Soutenu", "Claude (clé API)")):
            expect(f"set_language returns the code {code}", i18n.set_language(code) == code)
            got = (engine_error(), style_label(), engine_label(), checks.warnings(["empty"])[0]["message"],
                   str(ocr.OcrError("no_text")))
            seen[code] = got
            expect(f"error message in {code}", got[0] == error, got[0])
            expect(f"style and engine label in {code}", got[1:3] == (style, engine), str(got[1:3]))
            expect(f"check warning and ocr message follow the language {code}",
                   got[3] != german[3] and got[4] != german[4], str(got[3:]))
            reasons = {e["id"]: e["reason"] for e in providers.availability({})}
            expect(f"engine reason in {code}", reasons["claude_api"] not in ("", "API-Schlüssel fehlt"),
                   reasons["claude_api"])
            label = downloads.Downloader(Path(tempfile.gettempdir()) / "tt-no-such-dir", lambda m: None).state()
            expect(f"download label in {code}", "Laufzeit" not in json.dumps(label, ensure_ascii=False)
                   and downloads.LLAMA_TAG in json.dumps(label, ensure_ascii=False))
            expect(f"prompts name the answer language {code}",
                   i18n.language_name() in prompting.explain_messages("a", "b", "de", "en")[0]["content"]
                   and "German-speaking" not in prompting.explain_messages("a", "b", "de", "en")[0]["content"])
        expect("the four languages differ", len({seen[c][3] for c in seen}) == 4)

        expect("unknown language falls back to german", i18n.set_language("xx") == "de"
               and engine_error() == german[0])
        expect("empty and odd values fall back to german", i18n.set_language(None) == "de"
               and i18n.set_language(7) == "de" and i18n.normalize(["en"]) == "de")
        expect("region and case are ignored", i18n.set_language("EN-us") == "en" and i18n.set_language("fr_FR") == "fr")
    finally:
        i18n.set_language("de")
    expect("german prompts are unchanged", "to a German-speaking user" in
           prompting.explain_messages("a", "b", "de", "en")[0]["content"])

    with tempfile.TemporaryDirectory() as work:
        config = Path(work) / "config.json"
        config.write_text(json.dumps({"memory": {"vector": False}}), encoding="utf-8")
        try:
            side = sidecar_main.Sidecar(APP_DIR, config)
            expect("ui_language defaults to german", side.config()["ui_language"] == "de"
                   and side.status()["config"]["ui_language"] == "de")
            saved = side.save_config({"ui_language": "es"})
            status = side.status()
            expect("set_config switches the language", saved["ui_language"] == "es" and i18n.get_language() == "es"
                   and side.public_config()["ui_language"] == "es" and status["config"]["ui_language"] == "es")
            expect("status follows the language",
                   {s["id"]: s["label"] for s in status["styles"]}["literal"] == "Literal"
                   and status["engines"][0]["label"] == "Local (GPU)", str(status["styles"]))
            labels = {c["code"]: c["label"] for c in status["languages"]["catalog"]}
            expect("language labels follow the language", labels["en"] == "Inglés" and labels["de"] == "Alemán"
                   and languages.name("en") == "English", str(labels))
            side.save_config({"ui_language": "klingon"})
            expect("unknown ui_language falls back to german", side.config()["ui_language"] == "de"
                   and i18n.get_language() == "de")
            side.save_config({"ui_language": "fr"})
            i18n.set_language("de")
            sidecar_main.Sidecar(APP_DIR, config)
            expect("stored language is applied on start", i18n.get_language() == "fr")
        finally:
            i18n.set_language("de")


if __name__ == "__main__":
    tests = [test_hardware, test_platform, test_ocr, test_downloads, test_languages, test_word_list, test_checks, test_phrases,
             test_prompting, test_config_and_direction, test_history_and_export, test_json_answers, test_modes,
             test_mcp, test_openrouter, test_i18n_catalog, test_i18n_switch]
    if "--vector" in sys.argv:
        tests.append(test_vector)
    if "--claude" in sys.argv:
        tests.append(test_claude_subscription)
    for test in tests:
        i18n.set_language("de")  # the tests assert German texts
        test()
    print(f"\n{len(failures)} failed" if failures else "\nall passed")
    sys.exit(1 if failures else 0)
