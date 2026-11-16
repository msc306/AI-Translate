"""Unit tests without GPU or network. Run: .venv\\Scripts\\python sidecar\\tests\\test_units.py

Options:  --vector   also test the ChromaDB index (downloads the embedding model on first run)
          --claude   also translate one sentence through the Claude subscription (needs a login)
"""
import csv
import json
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
import history
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
            expect("mcp initialize", hello["result"]["serverInfo"]["name"] == "turing-translate"
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


if __name__ == "__main__":
    test_ocr()
    test_downloads()
    test_languages()
    test_checks()
    test_phrases()
    test_prompting()
    test_config_and_direction()
    test_history_and_export()
    test_json_answers()
    test_modes()
    test_mcp()
    if "--vector" in sys.argv:
        test_vector()
    if "--claude" in sys.argv:
        test_claude_subscription()
    print(f"\n{len(failures)} failed" if failures else "\nall passed")
    sys.exit(1 if failures else 0)
