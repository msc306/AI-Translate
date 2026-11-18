"""Graphics card detection and VRAM queries (standard library only).

Cards are found through DXGI, which every Windows graphics driver provides, so NVIDIA, AMD and
Intel are all seen the same way. Free memory comes from nvidia-smi for NVIDIA (exact, covers all
processes) and from the DXGI memory budget otherwise.
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
from ctypes import wintypes

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW

VENDORS = {0x10DE: "nvidia", 0x1002: "amd", 0x1022: "amd", 0x8086: "intel"}
VENDOR_NAMES = {"nvidia": "NVIDIA", "amd": "AMD", "intel": "Intel"}
# Which llama.cpp build fits which card. Vulkan runs on every current AMD and Intel card.
BACKENDS = {"nvidia": "cuda", "amd": "vulkan", "intel": "vulkan", "cpu": "cpu"}
CHOICES = ("auto", "nvidia", "amd", "intel", "cpu")
INTEGRATED_BELOW_MB = 1024   # less dedicated memory than this: graphics built into the processor

_DXGI_SOFTWARE = 2


class _LUID(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.LONG)]


class _AdapterDesc1(ctypes.Structure):
    _fields_ = [
        ("description", wintypes.WCHAR * 128),
        ("vendor_id", wintypes.UINT),
        ("device_id", wintypes.UINT),
        ("subsys_id", wintypes.UINT),
        ("revision", wintypes.UINT),
        ("dedicated_video", ctypes.c_size_t),
        ("dedicated_system", ctypes.c_size_t),
        ("shared_system", ctypes.c_size_t),
        ("luid", _LUID),
        ("flags", wintypes.UINT),
    ]


class _MemoryInfo(ctypes.Structure):
    _fields_ = [
        ("budget", ctypes.c_uint64),
        ("current_usage", ctypes.c_uint64),
        ("available_for_reservation", ctypes.c_uint64),
        ("current_reservation", ctypes.c_uint64),
    ]


class _GUID(ctypes.Structure):
    _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]

    def __init__(self, text: str):
        super().__init__()
        parts = text.split("-")
        self.d1, self.d2, self.d3 = int(parts[0], 16), int(parts[1], 16), int(parts[2], 16)
        rest = bytes.fromhex(parts[3] + parts[4])
        self.d4[:] = list(rest)


_IID_FACTORY1 = "770aae78-f26f-4dba-a829-253c83d1b387"
_IID_ADAPTER3 = "645967a4-1392-4310-a798-8053ce3e93fd"


def _method(obj: ctypes.c_void_p, index: int, restype, *argtypes):
    """Function at position `index` of a COM object's vtable."""
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtable[index])


def _release(obj: ctypes.c_void_p) -> None:
    if obj:
        _method(obj, 2, wintypes.ULONG)(obj)


def _dxgi_adapters() -> list[dict]:
    """Hardware adapters in DXGI order: name, vendor, dedicated memory and current budget."""
    if sys.platform != "win32":
        return []
    try:
        create = ctypes.windll.dxgi.CreateDXGIFactory1
    except (OSError, AttributeError):
        return []
    factory = ctypes.c_void_p()
    if create(ctypes.byref(_GUID(_IID_FACTORY1)), ctypes.byref(factory)) != 0:
        return []
    found = []
    try:
        enum = _method(factory, 12, ctypes.c_long, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))
        index = 0
        while index < 16:
            adapter = ctypes.c_void_p()
            if enum(factory, index, ctypes.byref(adapter)) != 0:
                break
            index += 1
            try:
                desc = _AdapterDesc1()
                if _method(adapter, 10, ctypes.c_long, ctypes.POINTER(_AdapterDesc1))(adapter, ctypes.byref(desc)) != 0:
                    continue
                if desc.flags & _DXGI_SOFTWARE or desc.vendor_id == 0x1414:  # Microsoft Basic Render Driver
                    continue
                entry = {
                    "name": desc.description.strip(),
                    "vendor": VENDORS.get(desc.vendor_id, "other"),
                    "dedicated_mb": desc.dedicated_video // 2**20,
                    "shared_mb": desc.shared_system // 2**20,
                    "budget_mb": None,
                    "used_mb": None,
                }
                adapter3 = ctypes.c_void_p()
                query = _method(adapter, 0, ctypes.c_long, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p))
                if query(adapter, ctypes.byref(_GUID(_IID_ADAPTER3)), ctypes.byref(adapter3)) == 0:
                    try:
                        info = _MemoryInfo()
                        memory = _method(adapter3, 14, ctypes.c_long, wintypes.UINT, ctypes.c_int,
                                         ctypes.POINTER(_MemoryInfo))
                        if memory(adapter3, 0, 0, ctypes.byref(info)) == 0:   # node 0, local memory
                            entry["budget_mb"] = info.budget // 2**20
                            entry["used_mb"] = info.current_usage // 2**20
                    finally:
                        _release(adapter3)
                found.append(entry)
            finally:
                _release(adapter)
    finally:
        _release(factory)
    return found


def detect() -> list[dict]:
    """All graphics cards: [{name, vendor, dedicated_mb, integrated}], dedicated cards first."""
    cards = []
    for card in _dxgi_adapters():
        cards.append({
            "name": card["name"],
            "vendor": card["vendor"],
            "dedicated_mb": card["dedicated_mb"],
            "integrated": card["dedicated_mb"] < INTEGRATED_BELOW_MB,
        })
    cards.sort(key=lambda c: (c["integrated"], -c["dedicated_mb"]))
    return cards


def auto_vendor(cards: list[dict] | None = None) -> str:
    """The vendor of the best usable card, or "cpu" when there is none."""
    for card in detect() if cards is None else cards:
        if card["vendor"] in BACKENDS:
            return card["vendor"]
    return "cpu"


def resolve(choice: str, cards: list[dict] | None = None) -> dict:
    """Effective setting for a configured choice: {choice, vendor, backend, card}."""
    cards = detect() if cards is None else cards
    choice = choice if choice in CHOICES else "auto"
    vendor = auto_vendor(cards) if choice == "auto" else choice
    card = next((c for c in cards if c["vendor"] == vendor), None)
    return {"choice": choice, "vendor": vendor, "backend": BACKENDS[vendor], "card": card}


def _nvidia_smi(gpu_index: int) -> dict | None:
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                f"--id={gpu_index}",
                "--query-gpu=memory.free,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            stdin=subprocess.DEVNULL,  # never inherit the sidecar's own stdin: that can block on Windows
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        free, used, total = (int(x.strip()) for x in out.stdout.strip().splitlines()[0].split(","))
    except (ValueError, IndexError):
        return None
    return {"free": free, "used": used, "total": total}


def vram_mb(gpu_index: int = 0, vendor: str = "nvidia") -> dict | None:
    """{'free', 'used', 'total'} in MiB for the chosen card, or None if it cannot be queried.

    For an integrated card the memory shared with the processor counts, so "total" is that budget.
    """
    if vendor == "cpu":
        return None
    if vendor == "nvidia":
        state = _nvidia_smi(gpu_index)
        if state:
            return state
    matching = [a for a in _dxgi_adapters() if a["vendor"] == vendor]
    if not matching:
        return None
    card = matching[min(gpu_index, len(matching) - 1)]
    total = card["dedicated_mb"]
    if total < INTEGRATED_BELOW_MB:
        total = card["shared_mb"]
    if card["budget_mb"] is None:
        return {"free": total, "used": 0, "total": total}
    # DXGI reports the budget this process may use; what the system holds elsewhere is the rest.
    free = max(0, min(card["budget_mb"], total))
    return {"free": free, "used": max(0, total - free), "total": total}
