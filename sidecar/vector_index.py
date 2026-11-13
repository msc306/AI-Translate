"""Semantic search over the phrase memory with ChromaDB (optional).

The translator works without it: if chromadb or fastembed is missing, the state becomes
"unavailable" and only literal phrase matches are used. All heavy work runs in a background thread
so the sidecar starts instantly.
"""
import hashlib
import re
import threading
from pathlib import Path

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_CLAUSE = re.compile(r"[.!?;:\n]+|,\s")


def segments(text: str, limit: int = 16) -> list[str]:
    """The text itself (if short) plus its clauses; phrases usually hide inside one clause."""
    result = []
    stripped = text.strip()
    if stripped and len(stripped) <= 200:
        result.append(stripped)
    for part in _CLAUSE.split(text):
        part = part.strip()
        if len(part) >= 6 and part not in result:
            result.append(part)
    return result[:limit]


def _doc_id(entry_id: str, lang: str, text: str) -> str:
    return hashlib.sha1(f"{entry_id}\x1f{lang}\x1f{text}".encode("utf-8")).hexdigest()


class VectorIndex:
    def __init__(self, folder: Path, model: str = DEFAULT_MODEL):
        self.folder = folder
        self.model = model or DEFAULT_MODEL
        self.state = "off"  # off | loading | ready | unavailable
        self.error = ""
        self.count = 0
        self._collection = None
        self._embedder = None
        self._pending = None
        self._thread = None
        self._plan = threading.Lock()  # guards _pending/_thread
        self._work = threading.Lock()  # guards embedder and collection

    def info(self) -> dict:
        return {"state": self.state, "count": self.count, "error": self.error, "model": self.model}

    def sync(self, documents):
        """Bring the index in line with the given (entry id, language, text) rows, in the background."""
        with self._plan:
            self._pending = list(documents)
            if self._thread is None:
                if self.state == "off":
                    self.state = "loading"
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()

    def wait(self, timeout: float = 600.0) -> bool:
        """Block until the background work is done (tests and the eval runner use this)."""
        thread = self._thread
        if thread:
            thread.join(timeout)
        return self.state == "ready"

    def _run(self):
        while True:
            with self._plan:
                documents, self._pending = self._pending, None
                if documents is None:
                    self._thread = None
                    return
            try:
                with self._work:
                    self._sync(documents)
                self.state, self.error = "ready", ""
            except Exception as err:  # missing packages, no network for the model download, ...
                self.state, self.error = "unavailable", f"{type(err).__name__}: {err}"

    def _load(self):
        import os
        # Keep the model download quiet: nobody reads the sidecar's stderr.
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        import chromadb
        from chromadb.config import Settings
        from fastembed import TextEmbedding

        self.folder.mkdir(parents=True, exist_ok=True)
        self._embedder = TextEmbedding(model_name=self.model, cache_dir=str(self.folder / "embedding-model"))
        client = chromadb.PersistentClient(path=str(self.folder / "chroma"),
                                           settings=Settings(anonymized_telemetry=False))
        # One collection per embedding model: vectors of different models must never mix.
        name = "phrases-" + hashlib.sha1(self.model.encode("utf-8")).hexdigest()[:10]
        self._collection = client.get_or_create_collection(
            name=name, embedding_function=None, configuration={"hnsw": {"space": "cosine"}})

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._embedder.embed(texts)]

    def _sync(self, documents):
        if self._collection is None:
            self._load()
        wanted = {_doc_id(*row): row for row in documents}
        existing = set(self._collection.get(include=[])["ids"])
        stale = sorted(existing - set(wanted))
        if stale:
            self._collection.delete(ids=stale)
        missing = sorted(set(wanted) - existing)
        for start in range(0, len(missing), 64):
            ids = missing[start:start + 64]
            rows = [wanted[i] for i in ids]
            self._collection.upsert(
                ids=ids,
                documents=[row[2] for row in rows],
                embeddings=self._embed([row[2] for row in rows]),
                metadatas=[{"entry": row[0], "lang": row[1]} for row in rows])
        self.count = len(wanted)

    def query(self, text: str, lang: str, limit: int = 4, min_similarity: float = 0.6) -> list[dict]:
        """Phrases in `lang` that resemble the text or one of its clauses, best first."""
        if self.state != "ready" or not self.count:
            return []
        parts = segments(text)
        if not parts:
            return []
        try:
            with self._work:
                result = self._collection.query(
                    query_embeddings=self._embed(parts), n_results=min(3, self.count),
                    where={"lang": lang}, include=["documents", "metadatas", "distances"])
        except Exception as err:
            self.error = f"{type(err).__name__}: {err}"
            return []
        best = {}
        for part, docs, metas, distances in zip(parts, result["documents"], result["metadatas"],
                                                result["distances"]):
            for doc, meta, distance in zip(docs, metas, distances):
                similarity = 1.0 - float(distance)
                entry = meta["entry"]
                if similarity >= min_similarity and similarity > best.get(entry, {}).get("similarity", 0):
                    best[entry] = {"id": entry, "text": doc, "similarity": round(similarity, 3), "clause": part}
        return sorted(best.values(), key=lambda hit: -hit["similarity"])[:limit]
