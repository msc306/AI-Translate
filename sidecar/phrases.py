"""Phrase memory: read-only language packs plus the user's own entries and corrections."""
import json
import re
import uuid
import zipfile
from pathlib import Path

from i18n import tr

_PUNCT = re.compile(r"[^\w\s']", re.UNICODE)
_SPACE = re.compile(r"\s+")
_PACK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
MAX_PACK_BYTES = 20 * 1024 * 1024


def normalize(text: str) -> str:
    return _SPACE.sub(" ", _PUNCT.sub(" ", text.lower())).strip()


def _variants(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


class PackError(Exception):
    pass


class Pack:
    """A folder with manifest.json and phrases.json. Never written to."""

    def __init__(self, folder: Path, origin: str):
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        self.folder = folder
        self.origin = origin  # "app" or "user"
        self.id = str(manifest.get("id") or folder.name)
        self.name = str(manifest.get("name") or self.id)
        self.version = str(manifest.get("version") or "")
        self.languages = [l for l in manifest.get("languages", []) if isinstance(l, dict) and l.get("code")]
        self.codes = [l["code"] for l in self.languages]
        self.style_notes = str(manifest.get("style_notes") or "")
        self.entries = []
        phrases_file = folder / "phrases.json"
        if phrases_file.is_file():
            data = json.loads(phrases_file.read_text(encoding="utf-8"))
            for raw in data.get("phrases", []):
                texts = {code: _variants(raw.get(code)) for code in self.codes}
                texts = {code: v for code, v in texts.items() if v}
                if len(texts) >= 2:
                    self.entries.append(texts)

    def info(self) -> dict:
        return {"id": self.id, "name": self.name, "version": self.version, "origin": self.origin,
                "languages": self.codes, "phrases": len(self.entries)}


def load_packs(*sources) -> dict[str, Pack]:
    """sources: (folder, origin) pairs; later sources win on the same pack id."""
    packs = {}
    for folder, origin in sources:
        if not folder.is_dir():
            continue
        for child in sorted(folder.iterdir()):
            if (child / "manifest.json").is_file():
                try:
                    pack = Pack(child, origin)
                except (OSError, ValueError, AttributeError):
                    continue
                packs[pack.id] = pack
    return packs


def install_pack(source: Path, target_dir: Path) -> str:
    """Install a pack from a .zip file or a folder into target_dir. Returns the pack id."""
    if source.is_dir():
        files = {name: (source / name).read_bytes() for name in ("manifest.json", "phrases.json")
                 if (source / name).is_file()}
    elif zipfile.is_zipfile(source):
        files = {}
        with zipfile.ZipFile(source) as archive:
            for item in archive.infolist():
                name = Path(item.filename).name
                if name in ("manifest.json", "phrases.json") and not item.is_dir():
                    if item.file_size > MAX_PACK_BYTES:
                        raise PackError(tr("Das Sprachpaket ist zu groß."))
                    files[name] = archive.read(item)
    else:
        raise PackError(tr("Kein Sprachpaket: erwartet wird eine .zip-Datei oder ein Ordner mit manifest.json."))
    if "manifest.json" not in files:
        raise PackError(tr("Im Sprachpaket fehlt die Datei manifest.json."))
    try:
        manifest = json.loads(files["manifest.json"].decode("utf-8"))
        pack_id = str(manifest["id"])
        codes = [l["code"] for l in manifest["languages"]]
        if "phrases.json" in files:
            json.loads(files["phrases.json"].decode("utf-8"))["phrases"]
    except (ValueError, KeyError, TypeError):
        raise PackError(tr("Das Sprachpaket ist beschädigt (manifest.json oder phrases.json ungültig)."))
    if not _PACK_ID.match(pack_id) or len(codes) < 2:
        raise PackError(tr("Das Sprachpaket hat keine gültige Kennung oder weniger als zwei Sprachen."))
    folder = target_dir / pack_id
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (folder / name).write_bytes(content)
    return pack_id


class PhraseBook:
    """All visible phrases: pack entries, minus hidden ones, plus user entries (which win)."""

    def __init__(self, packs: dict[str, Pack], user_file: Path):
        self.user_file = user_file
        self.user_entries = []  # [{"id": "user:...", "texts": {code: [variants]}}]
        self.hidden = set()
        if user_file.is_file():
            try:
                data = json.loads(user_file.read_text(encoding="utf-8"))
                for raw in data.get("entries", []):
                    texts = {c: _variants(v) for c, v in (raw.get("texts") or {}).items()}
                    texts = {c: v for c, v in texts.items() if v}
                    if raw.get("id") and len(texts) >= 2:
                        self.user_entries.append({"id": str(raw["id"]), "texts": texts})
                self.hidden = set(map(str, data.get("hidden", [])))
            except (OSError, ValueError, AttributeError):
                pass
        self.revision = 0
        self.set_packs(packs)

    def set_packs(self, packs: dict[str, Pack]):
        self.packs = packs
        self._build()

    def _build(self):
        self.items = {}   # id -> {"id", "texts", "origin"}
        self._index = {}  # code -> {normalized variant: (id, variant)}
        for pack in self.packs.values():
            for texts in pack.entries:
                first = next(code for code in pack.codes if code in texts)
                entry_id = f"{pack.id}:{normalize(texts[first][0])}"
                if entry_id not in self.hidden:
                    self._add({"id": entry_id, "texts": texts, "origin": pack.id})
        for entry in self.user_entries:
            self._add({"id": entry["id"], "texts": entry["texts"], "origin": "user"})
        self.revision += 1

    def _add(self, item):
        self.items[item["id"]] = item
        for code, variants in item["texts"].items():
            index = self._index.setdefault(code, {})
            for variant in variants:
                key = normalize(variant)
                if key:
                    index[key] = (item["id"], variant)

    def _store(self):
        self.user_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"entries": self.user_entries, "hidden": sorted(self.hidden)}
        temp = self.user_file.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.user_file)

    # ------------------------------------------------------------ lookups

    def _live(self, hit, target):
        """The item behind an index hit, if it is still current and has the target language."""
        item = self.items.get(hit[0])
        return item if item and item["texts"].get(target) else None

    def exact(self, text: str, source: str, target: str):
        """Return (translation, item) when the whole text is a known phrase."""
        hit = self._index.get(source, {}).get(normalize(text))
        item = self._live(hit, target) if hit else None
        return (item["texts"][target][0], item) if item else None

    def language_of(self, text: str, candidates) -> str | None:
        """Language of the longest known phrase that makes up at least half of the text.

        Short idioms ("Alles in Butter") carry too few common words for the detector.
        """
        norm = normalize(text)
        padded = f" {norm} "
        best_len, best = 0, None
        for lang in candidates:
            for key in self._index.get(lang, {}):
                if len(key) > best_len and f" {key} " in padded:
                    best_len, best = len(key), lang
        return best if best_len * 2 >= len(norm) > 0 else None

    def hints(self, text: str, source: str, target: str, limit: int = 12) -> list[dict]:
        """Known phrases that occur literally inside the text."""
        padded = f" {normalize(text)} "
        found = {}
        for key, hit in self._index.get(source, {}).items():
            if f" {key} " in padded and hit[0] not in found:
                item = self._live(hit, target)
                if item:
                    found[hit[0]] = {"id": hit[0], "source": hit[1], "target": item["texts"][target][0],
                                     "origin": item["origin"], "match": "exact"}
        return sorted(found.values(), key=lambda h: -len(h["source"]))[:limit]

    def describe(self, entry_id: str, source: str, target: str, matched: str = "") -> dict | None:
        item = self.items.get(entry_id)
        if not item or not item["texts"].get(source) or not item["texts"].get(target):
            return None
        return {"id": entry_id, "source": matched or item["texts"][source][0],
                "target": item["texts"][target][0], "origin": item["origin"]}

    def pairs(self, source: str, target: str) -> list[dict]:
        rows = [{"id": item["id"], "source": item["texts"][source], "target": item["texts"][target][0],
                 "origin": item["origin"]}
                for item in self.items.values() if item["texts"].get(source) and item["texts"].get(target)]
        return sorted(rows, key=lambda row: normalize(row["source"][0]))

    def documents(self) -> list[tuple[str, str, str]]:
        """(entry id, language, text) for every visible variant; input for the vector index."""
        return [(item["id"], code, variant)
                for item in self.items.values() for code, variants in item["texts"].items()
                for variant in variants]

    # ------------------------------------------------------------ changes

    def save(self, source: str, target: str, source_text, target_text: str, entry_id: str = "") -> str:
        """Create or change a user entry. Changing a pack entry creates an overriding user entry."""
        if isinstance(source_text, str):
            source_text = source_text.split("|")
        new_source = _variants(source_text)
        new_target = _variants(target_text)
        if not new_source or not new_target or source == target:
            raise ValueError(tr("Ausgangs- und Zieltext dürfen nicht leer sein."))
        existing = next((e for e in self.user_entries if e["id"] == entry_id), None)
        if existing is None and not entry_id:
            # Same source phrase saved again (a correction): update instead of duplicating.
            hit = self._index.get(source, {}).get(normalize(new_source[0]))
            if hit:
                existing = next((e for e in self.user_entries if e["id"] == hit[0]), None)
                entry_id = "" if existing else hit[0]
        if existing:
            existing["texts"][source] = new_source
            existing["texts"][target] = new_target
            result = existing["id"]
        else:
            texts = {}
            if entry_id in self.items:  # pack entry: keep its other languages, hide the original
                texts = {c: list(v) for c, v in self.items[entry_id]["texts"].items()}
                self.hidden.add(entry_id)
            texts[source] = new_source
            texts[target] = new_target
            result = "user:" + uuid.uuid4().hex[:12]
            self.user_entries.append({"id": result, "texts": texts})
        self._store()
        self._build()
        return result

    def delete(self, entry_id: str) -> bool:
        before = len(self.user_entries)
        self.user_entries = [e for e in self.user_entries if e["id"] != entry_id]
        if len(self.user_entries) == before:
            if entry_id not in self.items:
                return False
            self.hidden.add(entry_id)
        self._store()
        self._build()
        return True

    def export_pack(self, path: Path, name: str = "") -> int:
        """Write the user's own entries as a language pack (zip) that others can install."""
        name = name or tr("Eigene Phrasen")
        entries = [e["texts"] for e in self.user_entries if len(e.get("texts") or {}) >= 2]
        if not entries:
            raise ValueError(tr("Es gibt noch keine eigenen Einträge."))
        codes = sorted({code for texts in entries for code in texts})
        pack_id = re.sub(r"[^a-z0-9-]", "-", path.stem.lower()).strip("-")[:40]
        if len(pack_id) < 2 or not pack_id[0].isalnum():
            pack_id = "eigene-phrasen"
        manifest = {"id": pack_id, "name": name, "version": "1.0.0", "languages": [{"code": c} for c in codes]}
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            archive.writestr("phrases.json", json.dumps({"phrases": entries}, ensure_ascii=False, indent=2))
        return len(entries)
