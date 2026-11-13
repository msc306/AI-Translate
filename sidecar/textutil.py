"""Language detection (DE/EN) and splitting of long texts into sections."""
from __future__ import annotations

import re

_DE = set(
    "der die das und ist nicht ich du er sie wir ihr ein eine einen einem einer mit auf fuer für von zu zum zur "
    "den dem des auch aber oder wenn dass weil wie was wer wo kann muss soll habe hat sind war wird werden "
    "mein dein sein kein keine noch schon nur sehr hier dort heute morgen bitte danke mir mich dir dich uns "
    "bin bist im am als nach bei aus über unter vor so doch mal ja nein glaub glaube".split()
)
_EN = set(
    "the and is not you he she we they a an with on for of to in at as by from this that these those it its "
    "but or if because how what who where can must should have has are was were will would be been do does "
    "my your his her our their no yet only very here there today tomorrow please thanks me him us am i'm "
    "it's don't i think about into out over under before so just yes".split()
)
_WORD = re.compile(r"[A-Za-zÄÖÜäöüß']+")


def detect_language(text: str) -> str:
    """Returns 'de' or 'en'. On a tie, 'de' (main direction DE -> EN)."""
    words = [w.lower() for w in _WORD.findall(text[:4000])]
    de = sum(w in _DE for w in words) + 2 * len(re.findall(r"[äöüßÄÖÜ]", text[:4000]))
    en = sum(w in _EN for w in words)
    return "en" if en > de else "de"


_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def _split_long(paragraph: str, limit: int) -> list[str]:
    parts, current = [], ""
    for sentence in _SENTENCE_END.split(paragraph):
        while len(sentence) > limit:  # Sentence without punctuation: hard-split at a space
            cut = sentence.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            if current:
                parts.append(current)
                current = ""
            parts.append(sentence[:cut])
            sentence = sentence[cut:].lstrip()
        if current and len(current) + 1 + len(sentence) > limit:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip() if current else sentence
    if current:
        parts.append(current)
    return parts


def chunk_text(text: str, limit: int = 1400) -> list[tuple[str, str]]:
    """Splits text into (section, separator) pairs.

    Paragraphs are preserved; the separator is the original whitespace after the
    section, so the output gets the same paragraph structure.
    """
    text = text.replace("\r\n", "\n").strip("\n")
    pieces = re.split(r"(\n\s*\n)", text)
    paragraphs = [(pieces[i], pieces[i + 1] if i + 1 < len(pieces) else "") for i in range(0, len(pieces), 2)]

    chunks: list[tuple[str, str]] = []
    current, current_sep = "", ""
    for para, sep in paragraphs:
        if not para.strip():
            continue
        if len(para) > limit:
            if current:
                chunks.append((current, current_sep))
                current = ""
            parts = _split_long(para, limit)
            for part in parts[:-1]:
                chunks.append((part, " "))
            chunks.append((parts[-1], sep))
            continue
        if current and len(current) + len(current_sep) + len(para) > limit:
            chunks.append((current, current_sep))
            current = ""
        current = f"{current}{current_sep}{para}" if current else para
        current_sep = sep
    if current:
        chunks.append((current, current_sep))
    if chunks:
        chunks[-1] = (chunks[-1][0], "")
    return chunks
