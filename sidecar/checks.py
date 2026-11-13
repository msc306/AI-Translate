"""Cheap plausibility checks on a finished translation (no model call)."""
import languages
from phrases import normalize

MESSAGES = {
    "empty": "Die Übersetzung ist leer.",
    "untranslated": "Der Text wurde offenbar nicht übersetzt.",
    "wrong_language": "Die Ausgabe scheint nicht in der Zielsprache zu sein.",
    "too_short": "Die Übersetzung ist auffällig kurz – möglicherweise fehlt ein Teil.",
    "too_long": "Die Übersetzung ist auffällig lang – möglicherweise wurde etwas hinzugefügt.",
}

# What the model is told when a failed check triggers the single retry.
RETRY_NOTES = {
    "empty": "Your previous attempt was empty.",
    "untranslated": "Your previous attempt repeated the source text instead of translating it.",
    "wrong_language": "Your previous attempt was not written in the target language.",
    "too_short": "Your previous attempt left out part of the text.",
    "too_long": "Your previous attempt added content that is not in the source text.",
}


def check(source_text: str, output: str, source: str, target: str) -> list[str]:
    """Return the codes of all failed checks (empty list = fine)."""
    src = source_text.strip()
    out = output.strip()
    if not src:
        return []
    if not out:
        return ["empty"]

    problems = []
    words = len(src.split())
    if source != target and words > 3:
        if normalize(src) == normalize(out):
            problems.append("untranslated")
        else:
            code, confidence = languages.guess(out, [source, target])
            if code == source and confidence >= 0.3:
                problems.append("wrong_language")

    spaced = source not in languages.NO_SPACES and target not in languages.NO_SPACES
    if spaced and len(src) >= 40:
        ratio = len(out) / len(src)
        if ratio < 0.4:
            problems.append("too_short")
        elif ratio > 2.8:
            problems.append("too_long")
    return problems


def warnings(codes: list[str]) -> list[dict]:
    return [{"code": code, "message": MESSAGES.get(code, code)} for code in codes]
