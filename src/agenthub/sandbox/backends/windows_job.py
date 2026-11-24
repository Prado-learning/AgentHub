"""Manage Windows CLI descendants without relying on taskkill.exe.

The job object does two jobs for the sandbox backend:

* **Containment** — ``KILL_ON_JOB_CLOSE`` means closing our
  non-inheritable handle terminates every member process, so a
  cancelled or finished run never leaves an orphaned CLI tree behind.
* **Resource ceilings** — when a
  :class:`~agenthub.sandbox.spec.ResourceLimits` is supplied, total CPU
  time, per-process memory and the active process count are enforced by
  the kernel rather than by polling.

It is process lifecycle and resource management. It grants no
permissions and restricts no filesystem or network access.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from agenthub.sandbox.spec import ResourceLimits

_JOB_OBJECT_LIMIT_JOB_TIME = 0x00000004
_JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
_JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

_100NS_PER_SECOND = 10_000_000


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        (field, ctypes.c_ulonglong)
        for field in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class WindowsJob:
    """Closing our non-inherited job handle terminates every member process."""

    def __init__(self, limits: ResourceLimits | None = None):
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        for name, arguments, result in (
            ("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            (
                "SetInformationJobObject",
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
                wintypes.BOOL,
            ),
            (
                "AssignProcessToJobObject",
                [wintypes.HANDLE, wintypes.HANDLE],
                wintypes.BOOL,
            ),
            ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
        ):
            function = getattr(api, name)
            function.argtypes = arguments
            function.restype = result
        self._api = api
        self._handle = api.CreateJobObjectW(None, None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        extended = _ExtendedLimits()
        flags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if limits is not None:
            if limits.cpu_seconds is not None:
                extended.BasicLimitInformation.PerJobUserTimeLimit = (
                    limits.cpu_seconds * _100NS_PER_SECOND
                )
                flags |= _JOB_OBJECT_LIMIT_JOB_TIME
            if limits.max_processes is not None:
                extended.BasicLimitInformation.ActiveProcessLimit = (
                    limits.max_processes
                )
                flags |= _JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            if limits.memory_mb is not None:
                extended.ProcessMemoryLimit = limits.memory_mb * 1024 * 1024
                flags |= _JOB_OBJECT_LIMIT_PROCESS_MEMORY
        extended.BasicLimitInformation.LimitFlags = flags
        if not api.SetInformationJobObject(
            self._handle, 9, ctypes.byref(extended), ctypes.sizeof(extended)
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process):
        if not self._api.AssignProcessToJobObject(self._handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self._handle:
            if not self._api.CloseHandle(self._handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self._handle = None


# This isolated base-Python process cannot start the requested CLI until the
# parent has assigned it to the job and sent the envelope over stdin. Using the
# base executable avoids the extra child created by Windows venv launchers.
BOOTSTRAP = """
import json, subprocess, sys
request = json.loads(sys.stdin.buffer.read().decode('utf-8'))
try:
    result = subprocess.run(request['command'], input=request['prompt'].encode('utf-8'))
except OSError as error:
    sys.stderr.buffer.write(('CLI failed to start: ' + str(error)).encode('utf-8'))
    sys.exit(127)
sys.exit(result.returncode)
"""
