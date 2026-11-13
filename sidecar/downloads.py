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

LLAMA_TAG = "b12360"
_LLAMA = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}/"
_GEMMA = ("https://huggingface.co/lmstudio-community/gemma-4-E2B-it-GGUF/resolve/"
          "eed445ccfb8aef2e279df1a97e133baf06e443b4/")

CATALOG = {
    "runtime": {
        "kind": "runtime",
        "label": f"llama.cpp-Laufzeit für NVIDIA-Grafikkarten ({LLAMA_TAG})",
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
}

CHUNK = 1 << 20
ATTEMPTS = 6
USER_AGENT = "TuringTranslate"
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
        self.jobs: dict[str, tuple[threading.Thread, threading.Event]] = {}
        self.lock = threading.Lock()

    # ---- state ---------------------------------------------------------------------------

    def target(self, item: str) -> Path:
        entry = self.catalog[item]
        if entry["kind"] == "runtime":
            return self.data_dir / "runtime" / "llama-server.exe"
        return self.data_dir / "models" / entry["files"][0]["name"]

    def state(self) -> list[dict]:
        with self.lock:
            running = {name for name, (thread, _) in self.jobs.items() if thread.is_alive()}
        return [
            {
                "item": name,
                "kind": entry["kind"],
                "label": entry["label"],
                "size_mb": entry["size_mb"],
                "installed": self.target(name).is_file(),
                "running": name in running,
            }
            for name, entry in self.catalog.items()
        ]

    # ---- control -------------------------------------------------------------------------

    def start(self, item: str, req_id=None) -> None:
        if item not in self.catalog:
            raise DownloadError(f"Unbekannter Download: {item}")
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
                self._report(item, req_id, "done", message="Bereits vorhanden.")
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
                    raise DownloadError(f"Die Prüfsumme von {spec['name']} stimmt nicht. Die Datei wurde verworfen.")
                parts.append(part)
                before_mb += spec["size_mb"]

            if entry["kind"] == "runtime":
                self._report(item, req_id, "extracting", done_mb=total_mb, total_mb=total_mb)
                _install_runtime(parts, self.data_dir / "runtime")
                for part in parts:
                    part.unlink(missing_ok=True)
            else:
                target = self.target(item)
                target.parent.mkdir(parents=True, exist_ok=True)
                parts[0].replace(target)
            self._report(item, req_id, "done", done_mb=total_mb, total_mb=total_mb)
        except Cancelled:
            self._report(item, req_id, "cancelled",
                         message="Abgebrochen. Der bereits geladene Teil bleibt für die Fortsetzung erhalten.")
        except DownloadError as err:
            self._report(item, req_id, "error", message=str(err))
        except (OSError, zipfile.BadZipFile) as err:
            self._report(item, req_id, "error", message=f"Download fehlgeschlagen: {err}")

    def _check_space(self, entry: dict, work: Path) -> None:
        have_mb = sum((work / (f["name"] + ".part")).stat().st_size // 2**20
                      for f in entry["files"] if (work / (f["name"] + ".part")).is_file())
        factor = 2.3 if entry["kind"] == "runtime" else 1.0  # archives are unpacked next to themselves
        need_mb = int(entry["size_mb"] * factor) - have_mb + 200
        free_mb = shutil.disk_usage(work).free // 2**20
        if free_mb < need_mb:
            raise DownloadError(f"Zu wenig Speicherplatz: {need_mb} MB nötig, {free_mb} MB frei ({work.anchor}).")

    def _fetch(self, item, req_id, spec, part: Path, cancel, before_mb: int, total_mb: int) -> None:
        url = spec["url"]
        if not (url.lower().startswith("https://") or self.allow_http):
            raise DownloadError("Downloads laufen nur über https://.")
        if CURL.is_file():
            self._fetch_curl(item, req_id, spec, part, cancel, before_mb, total_mb)
        else:
            self._fetch_urllib(item, req_id, spec, part, cancel, before_mb, total_mb)

    def _fetch_curl(self, item, req_id, spec, part: Path, cancel, before_mb: int, total_mb: int) -> None:
        """Windows' own curl uses the system TLS stack, which fetches missing root certificates on demand;
        Python's ssl module does not and fails on some hosts (seen with GitHub's release downloads)."""
        for attempt in (1, 2):
            code, error = self._run_curl(item, req_id, spec, part, cancel, before_mb, total_mb)
            if code == 0:
                return
            if code == 33 and attempt == 1:
                # The server refused to resume (or the .part file is already complete or too long):
                # start over; the checksum decides afterwards.
                part.unlink(missing_ok=True)
                continue
            raise DownloadError(f"Download von {spec['name']} fehlgeschlagen: {error or f'curl {code}'}")

    def _run_curl(self, item, req_id, spec, part: Path, cancel, before_mb: int, total_mb: int) -> tuple[int, str]:
        protocols = "=http,https" if self.allow_http else "=https"
        command = [str(CURL), "--silent", "--show-error", "--fail", "--location",
                   "--proto", protocols, "--proto-redir", protocols,
                   "--retry", str(ATTEMPTS), "--retry-all-errors", "--retry-max-time", "300",
                   "--connect-timeout", "30", "--speed-limit", "1024", "--speed-time", "60",
                   "--user-agent", USER_AGENT, "--continue-at", "-", "--output", str(part), spec["url"]]
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE, creationflags=NO_WINDOW)
        try:
            while process.poll() is None:
                if cancel.wait(0.5):
                    process.kill()
                    process.wait()
                    raise Cancelled()
                have = part.stat().st_size if part.is_file() else 0
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
                        raise DownloadError("Der Server leitet auf eine unsichere Adresse um.")
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
                        raise OSError("Verbindung vorzeitig beendet")
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
        raise DownloadError(f"Download von {spec['name']} fehlgeschlagen: {last_error}")


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


def _install_runtime(archives: list[Path], target: Path) -> None:
    """Unpacks all archives into one flat folder and swaps it in only when llama-server.exe is there."""
    staging = target.with_name(target.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        for archive in archives:
            with zipfile.ZipFile(archive) as bundle:
                names = [n for n in bundle.namelist() if not n.endswith("/")]
                exe = next((n for n in names if n.replace("\\", "/").split("/")[-1].lower() == "llama-server.exe"), None)
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
        if not (staging / "llama-server.exe").is_file():
            raise DownloadError("Im Archiv fehlt llama-server.exe.")
        shutil.rmtree(target, ignore_errors=True)
        staging.replace(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
