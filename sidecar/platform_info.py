"""Which machine the sidecar runs on: operating system, processor architecture and data folders.

Every platform decision in the sidecar goes through this module, so tests can monkeypatch
`SYSTEM` and `MACHINE` to exercise the macOS or Linux paths on a Windows PC.
"""
from __future__ import annotations

import os
import platform as _platform
import sys
from pathlib import Path

APP_FOLDER = "AITranslate"


def _detect_system() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _detect_machine() -> str:
    raw = (_platform.machine() or "").lower()
    if raw in ("arm64", "aarch64", "armv8", "armv8l"):
        return "arm64"
    if sys.platform == "darwin" and raw == "x86_64":
        # A Python built for x86_64 runs under Rosetta on Apple Silicon; report the real chip.
        try:
            import subprocess
            out = subprocess.run(["/usr/sbin/sysctl", "-n", "sysctl.proc_translated"], capture_output=True,
                                 text=True, timeout=5).stdout.strip()
            if out == "1":
                return "arm64"
        except Exception:  # noqa: BLE001 - detection must never fail
            pass
    return "x64"


SYSTEM = _detect_system()
MACHINE = _detect_machine()

OS_LABELS = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}


def system() -> str:
    """'windows', 'macos' or 'linux'."""
    return SYSTEM


def machine() -> str:
    """'arm64' or 'x64'."""
    return MACHINE


def is_windows(system_name: str | None = None) -> bool:
    return (system_name or SYSTEM) == "windows"


def is_mac(system_name: str | None = None) -> bool:
    return (system_name or SYSTEM) == "macos"


def describe(system_name: str | None = None, machine_name: str | None = None) -> dict:
    """{os, arch, label}, for example {"os": "macos", "arch": "arm64", "label": "macOS (Apple Silicon)"}."""
    os_name = system_name or SYSTEM
    arch = machine_name or MACHINE
    if os_name == "macos":
        arch_label = "Apple Silicon" if arch == "arm64" else "Intel"
    else:
        arch_label = "ARM64" if arch == "arm64" else "x64"
    return {"os": os_name, "arch": arch, "label": f"{OS_LABELS.get(os_name, os_name)} ({arch_label})"}


def exe_name(base: str, system_name: str | None = None) -> str:
    """Executable file name: 'llama-server.exe' on Windows, 'llama-server' elsewhere."""
    return base + ".exe" if is_windows(system_name) else base


def config_dir(system_name: str | None = None, env=None, home: Path | None = None) -> Path:
    """Folder for config.json (roaming data on Windows)."""
    env = os.environ if env is None else env
    home = home or Path.home()
    os_name = system_name or SYSTEM
    if os_name == "windows":
        return Path(env.get("APPDATA") or home) / APP_FOLDER
    if os_name == "macos":
        return home / "Library" / "Application Support" / APP_FOLDER
    return Path(env.get("XDG_CONFIG_HOME") or home / ".config") / APP_FOLDER


def data_dir(system_name: str | None = None, env=None, home: Path | None = None) -> Path:
    """Folder for runtimes, models and indexes; AI_TRANSLATE_DATA overrides it everywhere."""
    env = os.environ if env is None else env
    home = home or Path.home()
    if env.get("AI_TRANSLATE_DATA"):
        return Path(env["AI_TRANSLATE_DATA"])
    os_name = system_name or SYSTEM
    if os_name == "windows":
        return Path(env.get("LOCALAPPDATA") or home) / APP_FOLDER
    if os_name == "macos":
        return home / "Library" / "Application Support" / APP_FOLDER
    return Path(env.get("XDG_DATA_HOME") or home / ".local" / "share") / APP_FOLDER


def no_window_flag() -> int:
    """creationflags that hide the console window of a child process; 0 off Windows."""
    return 0x08000000 if SYSTEM == "windows" else 0


def tool_dirs(home: Path | None = None, system_name: str | None = None) -> list[Path]:
    """Extra folders to search for command-line tools; GUI apps on macOS get a minimal PATH."""
    home = home or Path.home()
    os_name = system_name or SYSTEM
    if os_name == "windows":
        return [home / ".local" / "bin", home / "AppData" / "Roaming" / "npm"]
    return [Path("/opt/homebrew/bin"), Path("/usr/local/bin"), home / ".local" / "bin",
            home / ".npm-global" / "bin", home / ".bun" / "bin", Path("/usr/bin")]


def which(command: str, extra: list[Path] | None = None) -> str | None:
    """shutil.which plus the tool folders above."""
    import shutil
    found = shutil.which(command)
    if found:
        return found
    suffixes = (".exe", ".cmd", "") if SYSTEM == "windows" else ("",)
    for folder in (extra or []) + tool_dirs():
        for suffix in suffixes:
            path = folder / (command + suffix)
            if path.is_file() and (SYSTEM == "windows" or os.access(path, os.X_OK)):
                return str(path)
    return None
