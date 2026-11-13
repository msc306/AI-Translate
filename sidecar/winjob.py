"""Windows-Job-Objekt: Kindprozesse sterben garantiert mit, wenn der Sidecar endet.

Ohne das koennte ein hart beendeter Sidecar einen llama-server zuruecklassen,
der das Modell weiter im VRAM haelt.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_JOB = None


class _BASIC(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IO(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint64) for n in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _EXTENDED(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BASIC),
        ("IoInfo", _IO),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_KILL_ON_JOB_CLOSE = 0x2000
_EXTENDED_LIMIT_INFORMATION = 9


def _job():
    global _JOB
    if _JOB is None:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        handle = k32.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = _EXTENDED()
        info.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(handle, _EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        _JOB = (k32, handle)
    return _JOB


def bind_to_parent(proc) -> bool:
    """Haengt einen subprocess.Popen an das Job-Objekt. False, wenn das nicht moeglich war."""
    if sys.platform != "win32":
        return False
    try:
        k32, handle = _job()
        return bool(k32.AssignProcessToJobObject(handle, wintypes.HANDLE(int(proc._handle))))
    except OSError:
        return False
