"""Downloads the llama.cpp runtime and a recommended model into the user's data folder.

Standard library only. Every file is pinned to a fixed release and checked against its SHA-256,
so nothing unverified is ever unpacked or started. A broken download resumes from its .part file.
"""
import hashlib
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from i18n import tr

LLAMA_TAG = "b12360"
_LLAMA = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}/"
_GEMMA = ("https://huggingface.co/lmstudio-community/gemma-4-E2B-it-GGUF/resolve/"
          "eed445ccfb8aef2e279df1a97e133baf06e443b4/")
WHISPER_TAG = "b5454"
_WHISPER_MODELS = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"

# "label" is the German source text; state() translates it, filling in "label_values".
CATALOG = {
    "runtime": {
        "kind": "runtime",
        "label": "llama.cpp-Laufzeit für NVIDIA-Grafikkarten ({tag})",
        "label_values": {"tag": LLAMA_TAG},
        "size_mb": 677,
        "files": [
            {
                "name": f"llama-{LLAMA_TAG}-bin-win-cuda-12.4-x64.zip",
                "url": _LLAMA + f"llama-{LLAMA_TAG}-bin-win-cuda-12.4-x64.zip",
                "sha256": "70c0a244acf39f2f3fd8975a8447884e03fd35f499bf7dc284113845e894c382",
                "size_mb": 304,
            },
            {
                "name": "cudart-llama-bin-win-cuda-12.4-x64.zip",
                "url": _LLAMA + "cudart-llama-bin-win-cuda-12.4-x64.zip",
                "sha256": "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6",
                "size_mb": 373,
            },
        ],
    },
    "runtime_vulkan": {
        "kind": "runtime",
        "folder": "runtime-vulkan",
        "label": "llama.cpp-Laufzeit für AMD- und Intel-Grafikkarten, Vulkan ({tag})",
        "label_values": {"tag": LLAMA_TAG},
        "size_mb": 37,
        "files": [
            {
                "name": f"llama-{LLAMA_TAG}-bin-win-vulkan-x64.zip",
                "url": _LLAMA + f"llama-{LLAMA_TAG}-bin-win-vulkan-x64.zip",
                "sha256": "42a6f9df608b99c1c83fcaf77284a516e3f167b32a4690f4e4e364c377547055",
                "size_mb": 37,
            },
        ],
    },
    "runtime_cpu": {
        "kind": "runtime",
        "folder": "runtime-cpu",
        "label": "llama.cpp-Laufzeit nur für den Prozessor ({tag})",
        "label_values": {"tag": LLAMA_TAG},
        "size_mb": 24,
        "files": [
            {
                "name": f"llama-{LLAMA_TAG}-bin-win-cpu-x64.zip",
                "url": _LLAMA + f"llama-{LLAMA_TAG}-bin-win-cpu-x64.zip",
                "sha256": "eae1726047e0eaa707b1302929d196c999b96c2f243b21aea6e93bcebacc4e17",
                "size_mb": 24,
            },
        ],
    },
    "model_small": {
        "kind": "model",
        "label": "Gemma 4 E2B (kleines Modell, Apache-2.0)",
        "size_mb": 3269,
        "files": [
            {
                "name": "gemma-4-E2B-it-Q4_K_M.gguf",
                "url": _GEMMA + "gemma-4-E2B-it-Q4_K_M.gguf",
                "sha256": "71e6e8cb64a76da1a734fb8f6ba389d2784950d9902f5e87244fca0a15190c94",
                "size_mb": 3269,
            },
        ],
    },
    "whisper": {
        "kind": "runtime",
        "folder": "whisper",
        "exe": "whisper-cli.exe",
        "label": "whisper.cpp-Spracherkennung ({tag})",
        "label_values": {"tag": WHISPER_TAG},
        "size_mb": 9,
        "files": [
            {
                "name": f"whisper-{WHISPER_TAG}-bin-x64.zip",
                "url": f"https://github.com/ggml-org/whisper.cpp/releases/download/{WHISPER_TAG}/whisper-bin-x64.zip",
                "sha256": "6ba69e3482d7826214f90a6a9c84ca07782aec1e1d0c6a7c30c994fd5d816ccb",
                "size_mb": 9,
            },
        ],
    },
    "speech_model": {
        "kind": "model",
        "label": "Whisper small (Sprachmodell, MIT)",
        "size_mb": 182,
        "files": [
            {
                "name": "ggml-small-q5_1.bin",
                "url": _WHISPER_MODELS + "ggml-small-q5_1.bin",
                "sha256": "ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb",
                "size_mb": 182,
            },
        ],
    },
}

CHUNK = 1 << 20
ATTEMPTS = 6
USER_AGENT = "AITranslate"
# Which runtime download fits which llama.cpp backend (see gpu.BACKENDS).
RUNTIME_ITEMS = {"cuda": "runtime", "vulkan": "runtime_vulkan", "cpu": "runtime_cpu"}
STALLED = -1            # pseudo exit code: the .part file stopped growing
STALL_SECONDS = 90      # no new byte for this long counts as a stalled transfer
STALL_RESTARTS = 5
NO_WINDOW = 0x08000000
CURL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "curl.exe"


class DownloadError(Exception):
    pass


class Cancelled(Exception):
    pass


class Downloader:
    """Runs one background thread per catalog item and reports through `emit`."""

    def __init__(self, data_dir: Path, emit, catalog: dict | None = None, allow_http: bool = False):
        self.data_dir = Path(data_dir)
        self.emit = emit
        self.catalog = catalog or CATALOG
        self.allow_http = allow_http  # tests only: a local server without TLS
        self.stall_seconds = STALL_SECONDS
        self.jobs: dict[str, tuple[threading.Thread, threading.Event]] = {}
        self.lock = threading.Lock()

    # ---- state ---------------------------------------------------------------------------

    def target(self, item: str) -> Path:
        entry = self.catalog[item]
        if entry["kind"] == "runtime":
            return self.data_dir / entry.get("folder", "runtime") / entry.get("exe", "llama-server.exe")
        return self.data_dir / "models" / entry["files"][0]["name"]

    def state(self) -> list[dict]:
        with self.lock:
            running = {name for name, (thread, _) in self.jobs.items() if thread.is_alive()}
        return [
            {
                "item": name,
                "kind": entry["kind"],
                "label": tr(entry["label"], **entry.get("label_values", {})),
                "size_mb": entry["size_mb"],
                "installed": self.target(name).is_file(),
                "running": name in running,
            }
            for name, entry in self.catalog.items()
        ]

    # ---- control -------------------------------------------------------------------------

    def start(self, item: str, req_id=None) -> None:
        if item not in self.catalog:
            raise DownloadError(tr("Unbekannter Download: {item}", item=item))
        with self.lock:
            job = self.jobs.get(item)
            if job and job[0].is_alive():
                return
            cancel = threading.Event()
            thread = threading.Thread(target=self._run, args=(item, req_id, cancel), daemon=True)
            self.jobs[item] = (thread, cancel)
        thread.start()

    def cancel(self, item: str | None = None) -> None:
        with self.lock:
            jobs = [job for name, job in self.jobs.items() if item in (None, name)]
        for _, cancel in jobs:
            cancel.set()

    def wait(self, timeout: float | None = None) -> None:
        with self.lock:
            threads = [thread for thread, _ in self.jobs.values()]
        for thread in threads:
            thread.join(timeout)

    # ---- work ----------------------------------------------------------------------------

    def _report(self, item: str, req_id, state: str, **extra) -> None:
        self.emit({"id": req_id, "event": "download", "item": item, "state": state, **extra})

    def _run(self, item: str, req_id, cancel: threading.Event) -> None:
        entry = self.catalog[item]
        try:
            if self.target(item).is_file():
                self._report(item, req_id, "done", message=tr("Bereits vorhanden."))
                return
            work = self.data_dir / "downloads"
            work.mkdir(parents=True, exist_ok=True)
            self._check_space(entry, work)

            total_mb = sum(f["size_mb"] for f in entry["files"])
            before_mb = 0
            parts = []
            for spec in entry["files"]:
                part = work / (spec["name"] + ".part")
                self._fetch(item, req_id, spec, part, cancel, before_mb, total_mb)
                self._report(item, req_id, "verifying", done_mb=before_mb + spec["size_mb"], total_mb=total_mb)
                if _sha256(part, cancel) != spec["sha256"]:
                    part.unlink(missing_ok=True)
                    raise DownloadError(tr("Die Prüfsumme von {name} stimmt nicht. Die Datei wurde verworfen.",
                                           name=spec["name"]))
                parts.append(part)
                before_mb += spec["size_mb"]

            if entry["kind"] == "runtime":
                self._report(item, req_id, "extracting", done_mb=total_mb, total_mb=total_mb)
                _install_runtime(parts, self.data_dir / entry.get("folder", "runtime"),
                                 entry.get("exe", "llama-server.exe"))
                for part in parts:
                    part.unlink(missing_ok=True)
            else:
                target = self.target(item)
                target.parent.mkdir(parents=True, exist_ok=True)
                parts[0].replace(target)
            self._report(item, req_id, "done", done_mb=total_mb, total_mb=total_mb)
        except Cancelled:
            self._report(item, req_id, "cancelled",
                         message=tr("Abgebrochen. Der bereits geladene Teil bleibt für die Fortsetzung erhalten."))
        except DownloadError as err:
            self._report(item, req_id, "error", message=str(err))
        except (OSError, zipfile.BadZipFile) as err:
            self._report(item, req_id, "error", message=tr("Download fehlgeschlagen: {error}", error=err))

    def _check_space(self, entry: dict, work: Path) -> None:
        have_mb = sum((work / (f["name"] + ".part")).stat().st_size // 2**20
                      for f in entry["files"] if (work / (f["name"] + ".part")).is_file())
        factor = 2.3 if entry["kind"] == "runtime" else 1.0  # archives are unpacked next to themselves
        need_mb = int(entry["size_mb"] * factor) - have_mb + 200
        free_mb = shutil.disk_usage(work).free // 2**20
        if free_mb < need_mb:
            raise DownloadError(tr("Zu wenig Speicherplatz: {need} MB nötig, {free} MB frei ({drive}).",
                                   need=need_mb, free=free_mb, drive=work.anchor))

    def _fetch(self, item, req_id, spec, part: Path, cancel, before_mb: int, total_mb: int) -> None:
        url = spec["url"]
        if not (url.lower().startswith("https://") or self.allow_http):
            raise DownloadError(tr("Downloads laufen nur über https://."))
        if CURL.is_file():
            self._fetch_curl(item, req_id, spec, part, cancel, before_mb, total_mb)
        else:
            self._fetch_urllib(item, req_id, spec, part, cancel, before_mb, total_mb)

    def _fetch_curl(self, item, req_id, spec, part: Path, cancel, before_mb: int, total_mb: int) -> None:
        """Windows' own curl uses the system TLS stack, which fetches missing root certificates on demand;
        Python's ssl module does not and fails on some hosts (seen with GitHub's release downloads)."""
        restarted = stalls = 0
        while True:
            code, error = self._run_curl(item, req_id, spec, part, cancel, before_mb, total_mb)
            if code == 0:
                return
            if code == STALLED and stalls < STALL_RESTARTS:
                # curl's own low-speed limit does not catch a connection that never sends a byte;
                # start curl again, it resumes from the .part file.
                stalls += 1
                continue
            if code == 33 and not restarted:
                # The server refused to resume (or the .part file is already complete or too long):
                # start over; the checksum decides afterwards.
                restarted = 1
                part.unlink(missing_ok=True)
                continue
            if code == STALLED:
                error = tr("Der Server sendet keine Daten mehr.")
            raise DownloadError(tr("Download von {name} fehlgeschlagen: {error}",
                                   name=spec["name"], error=error or f"curl {code}"))

    def _run_curl(self, item, req_id, spec, part: Path, cancel, before_mb: int, total_mb: int) -> tuple[int, str]:
        protocols = "=http,https" if self.allow_http else "=https"
        command = [str(CURL), "--silent", "--show-error", "--fail", "--location",
                   "--proto", protocols, "--proto-redir", protocols,
                   "--retry", str(ATTEMPTS), "--retry-all-errors", "--retry-max-time", "300",
                   "--connect-timeout", "30", "--speed-limit", "1024", "--speed-time", "60",
                   "--user-agent", USER_AGENT, "--continue-at", "-", "--output", str(part), spec["url"]]
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE, creationflags=NO_WINDOW)
        last_size, last_growth = -1, time.monotonic()
        try:
            while process.poll() is None:
                if cancel.wait(0.5):
                    process.kill()
                    process.wait()
                    raise Cancelled()
                have = part.stat().st_size if part.is_file() else 0
                now = time.monotonic()
                if have != last_size:
                    last_size, last_growth = have, now
                elif now - last_growth > self.stall_seconds:
                    process.kill()
                    process.wait()
                    return STALLED, ""
                self._report(item, req_id, "running", file=spec["name"],
                             done_mb=before_mb + have // 2**20, total_mb=total_mb)
            error = process.stderr.read().decode("utf-8", "replace").strip()
        finally:
            if process.poll() is None:
                process.kill()
            process.stderr.close()
        return process.returncode, error

    def _fetch_urllib(self, item, req_id, spec, part: Path, cancel, before_mb: int, total_mb: int) -> None:
        url = spec["url"]
        last_error = None
        for attempt in range(ATTEMPTS):
            if cancel.is_set():
                raise Cancelled()
            have = part.stat().st_size if part.is_file() else 0
            headers = {"User-Agent": USER_AGENT}
            if have:
                headers["Range"] = f"bytes={have}-"
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as resp:
                    if not (resp.geturl().lower().startswith("https://") or self.allow_http):
                        raise DownloadError(tr("Der Server leitet auf eine unsichere Adresse um."))
                    resumed = resp.status == 206
                    if have and not resumed:
                        have = 0  # the server sent the whole file again
                    last_report = 0.0
                    with open(part, "ab" if resumed else "wb") as out:
                        while True:
                            if cancel.is_set():
                                raise Cancelled()
                            chunk = resp.read(CHUNK)
                            if not chunk:
                                break
                            out.write(chunk)
                            have += len(chunk)
                            now = time.monotonic()
                            if now - last_report >= 0.5:
                                last_report = now
                                self._report(item, req_id, "running", file=spec["name"],
                                             done_mb=before_mb + have // 2**20, total_mb=total_mb)
                    length = resp.headers.get("Content-Length")
                    if length is not None and not resumed and have < int(length):
                        raise OSError(tr("Verbindung vorzeitig beendet"))
                return
            except urllib.error.HTTPError as err:
                if err.code == 416:  # the .part file is already complete (or too long): let the checksum decide
                    return
                last_error = err
                if err.code in (401, 403, 404):
                    break
            except (OSError, ValueError) as err:
                last_error = err
            if cancel.wait(min(2 * (attempt + 1), 10)):
                raise Cancelled()
        raise DownloadError(tr("Download von {name} fehlgeschlagen: {error}", name=spec["name"], error=last_error))


def _sha256(path: Path, cancel: threading.Event | None = None) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            chunk = handle.read(CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _install_runtime(archives: list[Path], target: Path, exe_name: str = "llama-server.exe") -> None:
    """Unpacks all archives into one flat folder and swaps it in only when `exe_name` is there."""
    staging = target.with_name(target.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        for archive in archives:
            with zipfile.ZipFile(archive) as bundle:
                names = [n for n in bundle.namelist() if not n.endswith("/")]
                exe = next((n for n in names if n.replace("\\", "/").split("/")[-1].lower() == exe_name), None)
                prefix = exe.replace("\\", "/").rsplit("/", 1)[0] + "/" if exe and "/" in exe.replace("\\", "/") else ""
                for name in names:
                    clean = name.replace("\\", "/")
                    if exe is None:
                        relative = clean.split("/")[-1]  # library archives: everything next to the exe
                    elif clean.startswith(prefix):
                        relative = clean[len(prefix):]
                    else:
                        continue
                    parts = [p for p in relative.split("/") if p]
                    if not parts or any(p in ("..", ".") or ":" in p for p in parts):
                        continue
                    destination = staging.joinpath(*parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(name) as source, open(destination, "wb") as out:
                        shutil.copyfileobj(source, out, CHUNK)
        if not (staging / exe_name).is_file():
            raise DownloadError(tr("Im Archiv fehlt {name}.", name=exe_name))
        shutil.rmtree(target, ignore_errors=True)
        staging.replace(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
