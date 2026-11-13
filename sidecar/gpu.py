"""VRAM query via nvidia-smi (no extra packages needed)."""
from __future__ import annotations

import subprocess

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


def vram_mb(gpu_index: int = 0) -> dict | None:
    """Returns {'free': MiB, 'used': MiB, 'total': MiB}, or None if no NVIDIA GPU can be queried."""
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
