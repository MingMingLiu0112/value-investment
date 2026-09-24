"""Storage-neutral persistence contracts for offline M5 run state.

The store is deliberately separate from the domain coordinator. Public callers
can use an in-memory implementation for tests or an atomic JSON store for local
offline runs. Both enforce revision and digest compare-and-swap semantics.

The JSON store protects against concurrent writers and partial process writes;
it is not an external monotonic trust anchor and does not claim signed or
power-loss-proof rollback resistance.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Iterator, Protocol, runtime_checkable

from .m5_event_core import _required_int, _required_text
from .m5_event_run_state import M5EventRunState, m5_event_run_state_from_payload


class M5StateStoreConflict(RuntimeError):
    """Raised when a state commit no longer matches the persisted revision."""


@runtime_checkable
class M5EventRunStateStore(Protocol):
    """Minimal compare-and-swap contract for M5 run state."""

    def load(self, *, state_key: str) -> M5EventRunState | None:
        ...

    def commit(
        self,
        *,
        expected_revision: int,
        expected_sha256: str | None,
        state: M5EventRunState,
    ) -> None:
        ...


def _validate_expected(
    *,
    expected_revision: object,
    expected_sha256: object,
    current: M5EventRunState | None,
) -> tuple[int, str | None]:
    revision = _required_int(expected_revision, "expected_revision")
    if revision < 0:
        raise ValueError("expected_revision cannot be negative")
    digest = (
        None
        if expected_sha256 is None
        else _required_text(expected_sha256, "expected_sha256").lower()
    )
    if digest is not None and len(digest) != 64:
        raise ValueError("expected_sha256 must be a SHA-256 hex digest")
    if current is None:
        if revision != 0 or digest is not None:
            raise M5StateStoreConflict("No stored state exists for this state_key")
        return revision, digest
    if revision != current.revision:
        raise M5StateStoreConflict("M5 state revision changed since load")
    if digest is None or digest != current.state_sha256():
        raise M5StateStoreConflict("M5 state digest changed since load")
    return revision, digest


def _validate_next_state(
    *,
    current: M5EventRunState | None,
    expected_revision: int,
    state: M5EventRunState,
) -> None:
    if not isinstance(state, M5EventRunState):
        raise ValueError("state must be an M5EventRunState")
    if current is None:
        if state.revision not in {0, 1}:
            raise M5StateStoreConflict("Initial state revision must be 0 or 1")
        if any(record.state_revision != 1 for record in state.batch_records):
            raise M5StateStoreConflict("Initial persisted state is inconsistent")
        if state.outbox_revision != 0 or state.outbox_transitions:
            raise M5StateStoreConflict(
                "Initial persisted state cannot contain outbox transitions"
            )
        return
    if state.state_key != current.state_key:
        raise ValueError("Stored state_key cannot change")
    if state.revision == expected_revision:
        if state.state_sha256() == current.state_sha256():
            return
        if state.is_outbox_transition_successor_of(current):
            return
        raise M5StateStoreConflict(
            "Same revision cannot replace a different state digest"
        )
    if state.revision == expected_revision + 1:
        if not state.is_event_batch_successor_of(current):
            raise M5StateStoreConflict(
                "Event batch successor cannot change outbox history"
            )
        return
    raise M5StateStoreConflict("State revision must advance by exactly one")


def _round_trip_state(state: M5EventRunState) -> M5EventRunState:
    """Return a validated snapshot before any state is persisted."""
    if not isinstance(state, M5EventRunState):
        raise ValueError("state must be an M5EventRunState")
    try:
        payload = json.loads(state.to_json())
        snapshot = m5_event_run_state_from_payload(payload)
    except (TypeError, ValueError, KeyError) as error:
        raise M5StateStoreConflict(
            "M5 state failed round-trip validation"
        ) from error
    if snapshot.state_sha256() != state.state_sha256():
        raise M5StateStoreConflict("M5 state digest changed during round-trip")
    if not _same_semantic_state(state, snapshot):
        raise M5StateStoreConflict(
            "M5 state changed semantically during round-trip"
        )
    return snapshot


def _same_semantic_state(
    original: M5EventRunState,
    snapshot: M5EventRunState,
) -> bool:
    return (
        original.state_key == snapshot.state_key
        and original.namespace == snapshot.namespace
        and original.revision == snapshot.revision
        and original.action == snapshot.action
        and original.event_ledger.events() == snapshot.event_ledger.events()
        and original.watermarks.watermarks() == snapshot.watermarks.watermarks()
        and original.checkpoints.checkpoints() == snapshot.checkpoints.checkpoints()
        and original.outbox.alerts() == snapshot.outbox.alerts()
        and original.outbox_revision == snapshot.outbox_revision
        and original.outbox_transitions == snapshot.outbox_transitions
        and original.batch_records == snapshot.batch_records
    )


class InMemoryM5EventRunStateStore:
    """Thread-safe in-memory store used by offline tests and local callers."""

    def __init__(self) -> None:
        self._states: dict[str, M5EventRunState] = {}
        self._lock = threading.RLock()

    def load(self, *, state_key: str) -> M5EventRunState | None:
        key = _required_text(state_key, "state_key")
        with self._lock:
            state = self._states.get(key)
            return state.clone() if state is not None else None

    def commit(
        self,
        *,
        expected_revision: int,
        expected_sha256: str | None,
        state: M5EventRunState,
    ) -> None:
        if not isinstance(state, M5EventRunState):
            raise ValueError("state must be an M5EventRunState")
        snapshot = _round_trip_state(state)
        with self._lock:
            current = self._states.get(snapshot.state_key)
            _, digest = _validate_expected(
                expected_revision=expected_revision,
                expected_sha256=expected_sha256,
                current=current,
            )
            _validate_next_state(
                current=current,
                expected_revision=expected_revision,
                state=snapshot,
            )
            if current is not None and snapshot.state_sha256() == current.state_sha256():
                return
            self._states[snapshot.state_key] = snapshot


@contextmanager
def _exclusive_file_lock(lock_path: Path) -> Iterator[None]:
    """Serialize store access across threads and local processes."""
    with lock_path.open("r+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class JsonM5EventRunStateStore:
    """Local one-file-per-state store with atomic replace and CAS writes."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock_path = self.root / ".m5-event-state-store.lock"
        descriptor = os.open(
            self._lock_path,
            os.O_CREAT | os.O_RDWR,
            0o600,
        )
        try:
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self._thread_lock = threading.RLock()

    def _state_path(self, state_key: str) -> Path:
        digest = hashlib.sha256(state_key.encode("utf-8")).hexdigest()
        return self.root / f"m5-state-{digest}.json"

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self._thread_lock:
            with _exclusive_file_lock(self._lock_path):
                yield

    def _load_unlocked(self, state_key: str) -> M5EventRunState | None:
        path = self._state_path(state_key)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        state = m5_event_run_state_from_payload(payload)
        if state.state_key != state_key:
            raise ValueError("Stored M5 state does not match the requested state_key")
        return state

    def load(self, *, state_key: str) -> M5EventRunState | None:
        key = _required_text(state_key, "state_key")
        with self._locked():
            state = self._load_unlocked(key)
            return state.clone() if state is not None else None

    def _write_unlocked(self, state: M5EventRunState) -> None:
        path = self._state_path(state.state_key)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=path.stem + ".",
            suffix=".tmp",
            dir=self.root,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(state.to_json())
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def commit(
        self,
        *,
        expected_revision: int,
        expected_sha256: str | None,
        state: M5EventRunState,
    ) -> None:
        if not isinstance(state, M5EventRunState):
            raise ValueError("state must be an M5EventRunState")
        snapshot = _round_trip_state(state)
        with self._locked():
            current = self._load_unlocked(snapshot.state_key)
            _, digest = _validate_expected(
                expected_revision=expected_revision,
                expected_sha256=expected_sha256,
                current=current,
            )
            _validate_next_state(
                current=current,
                expected_revision=expected_revision,
                state=snapshot,
            )
            if current is not None and snapshot.state_sha256() == current.state_sha256():
                return
            self._write_unlocked(snapshot)
