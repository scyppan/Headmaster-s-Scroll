from __future__ import annotations

import errno
import os
import re
import sys
import time
from pathlib import Path

from .errors import DataLockError


class FileLock:
    MALFORMED_STALE_AFTER_SECONDS = 30.0

    def __init__(self, target: Path, timeout: float = 5.0, poll_interval: float = 0.05):
        self.path = target.with_suffix(target.suffix + ".lock")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._fd: int | None = None

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self._fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(
                    self._fd,
                    (
                        f"pid={os.getpid()}\n"
                        f"created_at={time.time():.6f}\n"
                    ).encode("ascii"),
                )
                return self
            except FileExistsError:
                if self._clear_stale_lock():
                    continue
                if time.monotonic() >= deadline:
                    raise DataLockError(f"Timed out waiting for {self.path.name}")
                time.sleep(self.poll_interval)

    @staticmethod
    def _process_is_running(pid: int) -> bool:
        if pid <= 0:
            return False
        if pid == os.getpid():
            return True
        if sys.platform == "win32":
            # os.kill(pid, 0) is not a harmless existence probe on Windows.
            # Query a process handle without requesting terminate/write rights.
            try:
                import ctypes

                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                handle = kernel32.OpenProcess(0x1000, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                # Access denied also means that the process exists.
                return ctypes.get_last_error() == 5
            except (AttributeError, OSError, ValueError):
                return True
        try:
            os.kill(pid, 0)
            return True
        except OSError as error:
            if error.errno == errno.ESRCH:
                return False
            return True

    def _clear_stale_lock(self) -> bool:
        """Remove only a lock whose recorded owner has definitely exited."""

        try:
            before = self.path.stat()
            contents = self.path.read_text(encoding="ascii", errors="replace")
        except FileNotFoundError:
            return True
        except OSError:
            return False
        match = re.search(r"(?m)^pid=(\d+)\s*$", contents)
        if match:
            if self._process_is_running(int(match.group(1))):
                return False
        elif time.time() - before.st_mtime < self.MALFORMED_STALE_AFTER_SECONDS:
            # A new owner may be between exclusive creation and writing its
            # PID.  Preserve fresh malformed/empty locks until the timeout.
            return False
        try:
            current = self.path.stat()
            if (
                current.st_mtime_ns != before.st_mtime_ns
                or current.st_size != before.st_size
            ):
                return False
            self.path.unlink()
            return True
        except FileNotFoundError:
            return True
        except OSError:
            return False

    def __exit__(self, exc_type, exc_value, traceback):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
