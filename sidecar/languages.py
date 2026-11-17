"""Language catalog and a small dependency-free language guesser."""
import re

from i18n import tr

# code -> (English name used in prompts, German label for the UI; label() translates it)
CATALOG = {
    "de": ("German", "Deutsch"),
    "en": ("English", "Englisch"),
    "fr": ("French", "Französisch"),
    "es": ("Spanish", "Spanisch"),
    "it": ("Italian", "Italienisch"),
    "pt": ("Portuguese", "Portugiesisch"),
    "nl": ("Dutch", "Niederländisch"),
    "pl": ("Polish", "Polnisch"),
    "cs": ("Czech", "Tschechisch"),
    "sv": ("Swedish", "Schwedisch"),
    "da": ("Danish", "Dänisch"),
    "no": ("Norwegian", "Norwegisch"),
    "fi": ("Finnish", "Finnisch"),
    "tr": ("Turkish", "Türkisch"),
    "ro": ("Romanian", "Rumänisch"),
    "hu": ("Hungarian", "Ungarisch"),
    "lt": ("Lithuanian", "Litauisch"),
    "lv": ("Latvian", "Lettisch"),
    "el": ("Greek", "Griechisch"),
    "ru": ("Russian", "Russisch"),
    "uk": ("Ukrainian", "Ukrainisch"),
    "ar": ("Arabic", "Arabisch"),
    "he": ("Hebrew", "Hebräisch"),
    "zh": ("Chinese", "Chinesisch"),
    "ja": ("Japanese", "Japanisch"),
    "ko": ("Korean", "Koreanisch"),
}

_STOPWORDS = {
    "de": "der die das und ist nicht ich du wir sie ein eine mit auf für von zu den dem im auch es sich wie noch "
          "nur aber oder wenn dass war hat haben wird sind bei aus nach mir dir was kein schon mal er ihr ihn uns "
          "euch mich dich wer wann wo warum hatte wurde am zum zur",
    "en": "the and is not you we they a an with on for of to in it that this was are be have has but or if my "
          "your what do does at by from as will would can there just so i he she his her him its our their them "
          "who when where which how were been had did",
    "fr": "le la les et est pas je tu nous vous un une avec sur pour de du des en que qui dans ce il elle ne se "
          "au mais ou si mon ton sont être avoir plus tout très",
    "es": "el la los las y es no yo tú un una con por para de del en que se lo su pero o si mi muy está son como "
          "más este esta hay también",
    "it": "il lo la gli le e è non io tu noi un una con su per di del della in che si ma o se mio sono come più "
          "questo questa anche molto ci",
    "pt": "o a os as e é não eu tu você um uma com por para de do da em que se mas ou meu são como mais este "
          "esta também muito está isso",
    "nl": "de het een en is niet ik jij je wij we zij met op voor van te in dat die dit was zijn maar of als mijn "
          "ook nog wel naar bij er aan",
    "pl": "i w nie na to jest się z że do ja ty my ale lub jak co tak po za czy tylko już bardzo jego jej być "
          "są ma ten ta",
    "cs": "a je v na se to že s z do ne já ty my ale nebo jak co tak po za jen už velmi jsem jsou být ten ta když",
    "sv": "och är inte jag du vi de en ett med på för av till i det att den som var har men eller om min också "
          "kan så från nu här",
    "da": "og er ikke jeg du vi de en et med på for af til i det at den som var har men eller hvis min også kan "
          "så fra nu her",
    "no": "og er ikke jeg du vi de en et med på for av til i det at den som var har men eller hvis min også kan "
          "så fra nå her bare",
    "fi": "ja on ei minä sinä me he se että kun mutta tai jos niin myös vain oli ovat olla mitä tämä hän kanssa "
          "kuin nyt",
    "tr": "ve bir bu da de için ile ben sen biz o değil mi ama veya çok var yok ne gibi daha en şu her kadar",
    "ro": "și este nu eu tu noi un o cu pe pentru de la în că se dar sau dacă meu sunt ca mai acest foarte am fi",
    "hu": "a az és nem én te mi egy van hogy de vagy ha is csak már még mint ez azt meg volt nagyon el lesz",
    "lt": "ir yra ne aš tu mes jie kad su į iš bet ar taip kaip tai labai tik dar jau buvo kas mano tavo jis ji "
          "apie nuo iki čia dabar",
    "lv": "un ir nav es tu mēs viņi ka ar uz no bet vai jā kā tas ļoti tikai vēl jau bija kas mans tavs viņš "
          "viņa par pie šeit tagad",
}
# letters that occur in one language only decide between close relatives
_LETTERS = {
    "de": set("äöüßÄÖÜ"),
    "lt": set("ėįųĖĮŲ"),
    "lv": set("āēģīķļņĀĒĢĪĶĻŅ"),
}
_STOPWORDS = {code: set(words.split()) for code, words in _STOPWORDS.items()}

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

# (first code point, last code point, language)
_SCRIPTS = (
    (0x0370, 0x03FF, "el"),
    (0x0400, 0x04FF, "ru"),
    (0x0590, 0x05FF, "he"),
    (0x0600, 0x06FF, "ar"),
    (0x3040, 0x30FF, "ja"),
    (0x4E00, 0x9FFF, "zh"),
    (0xAC00, 0xD7AF, "ko"),
)
_UKRAINIAN = set("їєіґЇЄІҐ")
NO_SPACES = {"zh", "ja", "ko"}


def name(code: str) -> str:
    return CATALOG.get(code, (code, code))[0]


def label(code: str) -> str:
    """Name of the language in the language of the interface."""
    return tr(CATALOG[code][1]) if code in CATALOG else code


def _script_guess(text: str) -> str | None:
    counts: dict[str, int] = {}
    letters = 0
    for ch in text:
        if not ch.isalpha():
            continue
        letters += 1
        cp = ord(ch)
        for first, last, code in _SCRIPTS:
            if first <= cp <= last:
                counts[code] = counts.get(code, 0) + 1
                break
    if not counts or not letters:
        return None
    # Japanese text mixes kana with Chinese characters; kana decides.
    if counts.get("ja"):
        counts["ja"] += counts.pop("zh", 0)
    code, hits = max(counts.items(), key=lambda item: item[1])
    if hits / letters < 0.4:
        return None
    if code == "ru" and any(ch in _UKRAINIAN for ch in text):
        return "uk"
    return code


def guess(text: str, candidates: list[str] | None = None) -> tuple[str | None, float]:
    """Return (language code, confidence 0..1). The code is None when nothing matches."""
    candidates = list(candidates) if candidates else list(CATALOG)
    script = _script_guess(text)
    if script:
        return (script, 1.0) if script in candidates else (None, 0.0)

    words = [w.lower() for w in _WORD.findall(text)]
    if not words:
        return None, 0.0
    scores = {}
    for code in candidates:
        stop = _STOPWORDS.get(code)
        if stop:
            scores[code] = sum(1 for w in words if w in stop)
    for code, letters in _LETTERS.items():
        if code in scores:
            scores[code] += sum(1 for ch in text if ch in letters)
    if not scores:
        return None, 0.0
    ranked = sorted(scores.items(), key=lambda item: -item[1])
    best_code, best = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    if best == 0:
        return None, 0.0
    return best_code, min(1.0, (best - second) / max(len(words), 1) * 4)


def detect(text: str, candidates: list[str]) -> str:
    """Best guess among the candidates; falls back to the first candidate."""
    code, _ = guess(text, candidates)
    return code or candidates[0]
