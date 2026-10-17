"""Cross-process exclusive lock for the private portfolio journal.

The lock is owned by the operating system, so a process that crashes or is
killed mid-transaction releases it automatically. That is why this replaces the
previous ``O_CREAT|O_EXCL`` lock file: a stale marker file could block the ledger
forever, and the previous code only held the lock while appending rather than
for the whole read-check-commit transaction.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from types import TracebackType

if os.name == "nt":  # pragma: no cover - selected by platform
    import msvcrt
else:  # pragma: no cover - selected by platform
    import fcntl


class LockTimeout(RuntimeError):
    """The journal lock could not be taken before the deadline."""


class InterProcessLock:
    """Re-entrant, thread-safe, OS-backed exclusive lock on one path."""

    def __init__(self, path: Path, *, timeout_seconds: float = 10.0) -> None:
        self.path = Path(path)
        self.timeout_seconds = timeout_seconds
        self._fd: int | None = None
        self._depth = 0
        self._owner: int | None = None

    def held_by_current_thread(self) -> bool:
        return self._depth > 0 and self._owner == threading.get_ident()

    def acquire(self) -> None:
        if self.held_by_current_thread():
            self._depth += 1
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + self.timeout_seconds
        try:
            while True:
                try:
                    self._lock_fd(fd)
                except OSError:
                    if time.monotonic() > deadline:
                        raise LockTimeout("私人流水被其他进程锁定，请稍后重试") from None
                    time.sleep(0.05)
                    continue
                break
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd
        self._depth = 1
        self._owner = threading.get_ident()

    def release(self) -> None:
        if self._depth == 0:
            return
        self._depth -= 1
        if self._depth > 0:
            return
        fd, self._fd = self._fd, None
        self._owner = None
        if fd is None:
            return
        try:
            self._unlock_fd(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _lock_fd(fd: int) -> None:
        if os.name == "nt":  # pragma: no cover - selected by platform
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:  # pragma: no cover - selected by platform
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock_fd(fd: int) -> None:
        if os.name == "nt":  # pragma: no cover - selected by platform
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:  # pragma: no cover - selected by platform
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass

    def __enter__(self) -> "InterProcessLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
