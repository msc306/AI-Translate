"""Speech input: record from the default microphone and turn the recording into text.

Standard library only. Recording uses the Windows multimedia API (winmm, MCI) through ctypes and
writes a 16 kHz mono WAV file. Recognition prefers whisper.cpp (`whisper-cli.exe` plus a ggml
model, both optional downloads); without it the speech recogniser built into Windows
(System.Speech, called through PowerShell) is used for the languages it has installed.
"""
import array
import base64
import ctypes
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path

from i18n import tr

NO_WINDOW = 0x08000000
MAX_SECONDS = 120          # a recording stops by itself after this long
SILENCE_RMS = 120          # 16-bit samples: below this the recording counts as silence
WHISPER_EXE = "whisper-cli.exe"
WHISPER_TIMEOUT = 300
SAPI_TIMEOUT = 120

# German source texts; tr() translates them when the error is raised.
MESSAGES = {
    "unsupported": "Spracheingabe gibt es nur unter Windows.",
    "busy": "Es läuft bereits eine Aufnahme.",
    "not_recording": "Es läuft keine Aufnahme.",
    "microphone": "Das Mikrofon lässt sich nicht öffnen: {detail}",
    "silence": "Es war nichts zu hören. Ist das richtige Mikrofon eingestellt und nicht stummgeschaltet?",
    "empty": "In der Aufnahme wurde kein Text erkannt.",
    "no_recogniser": "Für die Spracheingabe fehlt die Spracherkennung. In den Einstellungen unter "
                     "„Spracheingabe“ lassen sich whisper.cpp und ein Sprachmodell herunterladen.",
    "no_model": "Das gewählte Sprachmodell fehlt: {path}",
    "failed": "Die Spracherkennung ist fehlgeschlagen: {detail}",
}


class SpeechError(Exception):
    def __init__(self, code: str, **values):
        super().__init__(tr(MESSAGES[code], **values))
        self.code = code


# ---------------------------------------------------------------- recording


class Recorder:
    """One recording at a time. All MCI calls run on one worker thread, as MCI expects."""

    ALIAS = "aitranslate_rec"

    def __init__(self):
        self._jobs: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.recording = False
        self.started = 0.0
        self._timer: threading.Timer | None = None
        self.on_timeout = None  # called (without arguments) when MAX_SECONDS is reached

    # -- public --------------------------------------------------------------------------------

    def start(self) -> None:
        if os.name != "nt":
            raise SpeechError("unsupported")
        with self._lock:
            if self.recording:
                raise SpeechError("busy")
            self._call(self._mci_start)
            self.recording = True
            self.started = time.monotonic()
            self._timer = threading.Timer(MAX_SECONDS, self._timeout)
            self._timer.daemon = True
            self._timer.start()

    def stop(self) -> tuple[Path, float]:
        """End the recording; returns the WAV file (caller deletes it) and its length in seconds."""
        with self._lock:
            if not self.recording:
                raise SpeechError("not_recording")
            self._cancel_timer()
            self.recording = False
            seconds = time.monotonic() - self.started
            handle, name = tempfile.mkstemp(prefix="ai-translate-", suffix=".wav")
            os.close(handle)
            path = Path(name)
            try:
                self._call(self._mci_save, path)
            except Exception:
                path.unlink(missing_ok=True)
                raise
            return path, seconds

    def cancel(self) -> None:
        with self._lock:
            if not self.recording:
                return
            self._cancel_timer()
            self.recording = False
            try:
                self._call(self._mci_close)
            except SpeechError:
                pass

    # -- internals -----------------------------------------------------------------------------

    def _timeout(self) -> None:
        if self.recording and self.on_timeout:
            self.on_timeout()

    def _cancel_timer(self) -> None:
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _call(self, func, *args):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()
        done: queue.Queue = queue.Queue()
        self._jobs.put((func, args, done))
        ok, value = done.get()
        if not ok:
            raise value
        return value

    def _loop(self) -> None:
        while True:
            func, args, done = self._jobs.get()
            try:
                done.put((True, func(*args)))
            except Exception as err:  # handed back to the calling thread
                done.put((False, err))

    def _mci_start(self) -> None:
        _mci(f"close {self.ALIAS}", check=False)
        _mci(f"open new type waveaudio alias {self.ALIAS}")
        try:
            _mci(f"set {self.ALIAS} bitspersample 16 samplespersec 16000 channels 1 "
                 "alignment 2 bytespersec 32000")
            _mci(f"record {self.ALIAS}")
        except SpeechError:
            _mci(f"close {self.ALIAS}", check=False)
            raise

    def _mci_save(self, path: Path) -> None:
        try:
            _mci(f"stop {self.ALIAS}")
            _mci(f'save {self.ALIAS} "{path}"')
        finally:
            _mci(f"close {self.ALIAS}", check=False)

    def _mci_close(self) -> None:
        _mci(f"close {self.ALIAS}", check=False)


def _mci(command: str, check: bool = True) -> str:
    winmm = ctypes.windll.winmm
    answer = ctypes.create_unicode_buffer(256)
    err = winmm.mciSendStringW(command, answer, 256, None)
    if err and check:
        text = ctypes.create_unicode_buffer(256)
        winmm.mciGetErrorStringW(err, text, 256)
        raise SpeechError("microphone", detail=text.value or f"MCI {err}")
    return answer.value


def loudness(path: Path) -> int:
    """Root mean square of a 16-bit WAV file, computed over its loudest second."""
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 2:
            return SILENCE_RMS  # unexpected format: do not block the recognition
        rate, channels = wav.getframerate(), wav.getnchannels()
        samples = array.array("h", wav.readframes(wav.getnframes()))
    step = max(1, rate * channels)
    best = 0
    for start in range(0, max(1, len(samples)), step):
        window = samples[start:start + step]
        if window:
            rms = int((sum(s * s for s in window) / len(window)) ** 0.5)
            best = max(best, rms)
    return best


# ---------------------------------------------------------------- recognition


def whisper_exe(data_dir: Path) -> Path | None:
    exe = Path(data_dir) / "whisper" / WHISPER_EXE
    return exe if exe.is_file() else None


def list_models(data_dir: Path) -> list[dict]:
    """whisper models (ggml-*.bin) in the data folder's models directory."""
    folder = Path(data_dir) / "models"
    found = []
    if folder.is_dir():
        for path in sorted(folder.glob("ggml-*.bin")):
            found.append({"path": str(path), "name": path.stem.removeprefix("ggml-"),
                          "size_mb": round(path.stat().st_size / 2**20)})
    return found


def resolve_model(configured: str, data_dir: Path) -> Path | None:
    """The chosen model file, or for "auto" the best one found (small before base before others)."""
    if configured and configured != "auto":
        path = Path(configured)
        if not path.is_file():
            raise SpeechError("no_model", path=configured)
        return path
    models = list_models(data_dir)
    for needle in ("large-v3-turbo", "small", "medium", "base"):
        for model in models:
            if needle in model["name"]:
                return Path(model["path"])
    return Path(models[0]["path"]) if models else None


_windows_cache: list[str] | None = None


def windows_languages() -> list[str]:
    """Culture names of the installed Windows speech recognisers, e.g. ["de-DE", "en-US"]."""
    global _windows_cache
    if _windows_cache is None:
        script = ("Add-Type -AssemblyName System.Speech; "
                  "[System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers() | "
                  "ForEach-Object { $_.Culture.Name }")
        try:
            done = _powershell(script, {}, 30)
            _windows_cache = [line.strip() for line in done.splitlines() if line.strip()]
        except SpeechError:
            _windows_cache = []
    return _windows_cache


def transcribe(wav: Path, lang: str, data_dir: Path, model: str = "auto", engine: str = "auto") -> dict:
    """Turn a WAV recording into text: {"text", "engine", "lang"}."""
    lang = "" if lang in ("", "auto") else lang
    if loudness(wav) < SILENCE_RMS:
        raise SpeechError("silence")
    exe = whisper_exe(data_dir)
    model_path = resolve_model(model, data_dir) if engine in ("auto", "whisper") else None
    if engine in ("auto", "whisper") and exe and model_path:
        text = _whisper(exe, model_path, wav, lang)
        used = "whisper"
    elif engine in ("auto", "windows"):
        culture = _pick_culture(lang, windows_languages())
        if not culture:
            raise SpeechError("no_recogniser")
        text = _sapi(wav, culture)
        used, lang = "windows", culture.split("-")[0]
    else:
        raise SpeechError("no_recogniser")
    text = clean_text(text)
    if not text:
        raise SpeechError("empty")
    return {"text": text, "engine": used, "lang": lang}


def clean_text(raw: str) -> str:
    """Join whisper's lines and drop its markers for non-speech such as [Musik] or (Lachen)."""
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or (line[0] in "[(" and line[-1] in "])"):
            continue
        lines.append(line)
    return " ".join(lines).strip()


def _pick_culture(lang: str, cultures: list[str]) -> str:
    if lang:
        for culture in cultures:
            if culture.lower().split("-")[0] == lang.lower():
                return culture
        return ""
    return cultures[0] if cultures else ""


def _whisper(exe: Path, model: Path, wav: Path, lang: str) -> str:
    threads = str(max(1, min(8, (os.cpu_count() or 4))))
    command = [str(exe), "-m", str(model), "-f", str(wav), "-l", lang or "auto", "-nt", "-np", "-t", threads]
    try:
        done = subprocess.run(command, capture_output=True, timeout=WHISPER_TIMEOUT,
                              creationflags=NO_WINDOW if os.name == "nt" else 0, cwd=str(exe.parent))
    except (OSError, subprocess.TimeoutExpired) as err:
        raise SpeechError("failed", detail=str(err)) from err
    if done.returncode != 0:
        detail = done.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or [f"exit {done.returncode}"]
        raise SpeechError("failed", detail=detail[0])
    return done.stdout.decode("utf-8", "replace")


SAPI_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$culture = [System.Globalization.CultureInfo]::new($env:AIT_SPEECH_CULTURE)
$engine = [System.Speech.Recognition.SpeechRecognitionEngine]::new($culture)
$engine.LoadGrammar([System.Speech.Recognition.DictationGrammar]::new())
$engine.SetInputToWaveFile($env:AIT_SPEECH_WAV)
$parts = @()
while ($true) {
  $result = $engine.Recognize()
  if ($null -eq $result) { break }
  $parts += $result.Text
}
$engine.Dispose()
$json = ConvertTo-Json @{ text = ($parts -join ' ') } -Compress
[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
"""


def _sapi(wav: Path, culture: str) -> str:
    out = _powershell(SAPI_SCRIPT, {"AIT_SPEECH_CULTURE": culture, "AIT_SPEECH_WAV": str(wav)}, SAPI_TIMEOUT)
    try:
        return json.loads(base64.b64decode(out.strip().splitlines()[-1]).decode("utf-8")).get("text", "")
    except (ValueError, IndexError) as err:
        raise SpeechError("failed", detail=str(err)) from err


def _powershell(script: str, env_extra: dict, timeout: int) -> str:
    if os.name != "nt":
        raise SpeechError("unsupported")
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    env = {**os.environ, **env_extra}
    try:
        done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                              capture_output=True, timeout=timeout, env=env, creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as err:
        raise SpeechError("failed", detail=str(err)) from err
    if done.returncode != 0:
        detail = done.stderr.decode("utf-8", "replace").strip().splitlines()[:1] or [f"exit {done.returncode}"]
        raise SpeechError("failed", detail=detail[0])
    return done.stdout.decode("utf-8", "replace")
