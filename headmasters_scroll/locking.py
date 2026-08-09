from __future__ import annotations

import os
import time
from pathlib import Path

from .errors import DataLockError


class FileLock:
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
                os.write(self._fd, f"pid={os.getpid()}\n".encode("ascii"))
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise DataLockError(f"Timed out waiting for {self.path.name}")
                time.sleep(self.poll_interval)

    def __exit__(self, exc_type, exc_value, traceback):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

