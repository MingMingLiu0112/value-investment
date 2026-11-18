"""Reuse an independently verified successor within one synchronous read."""

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path

from .parent_owner_distribution_successor_v2 import (
    replay_parent_owner_distribution_successor as _cold_replay,
)


_verified_results = ContextVar("verified_owner_distribution_results", default=None)


@contextmanager
def owner_distribution_read_scope():
    """Discard all verified candidates on success or failure of the request."""
    token = _verified_results.set({})
    try:
        yield
    finally:
        _verified_results.reset(token)


def replay_parent_owner_distribution_successor(*, root, receipt_binding, now):
    results = _verified_results.get()
    if results is None:
        return _cold_replay(root=root, receipt_binding=receipt_binding, now=now)
    # Invalid bindings must follow the same validation path as independent reads.
    if (set(receipt_binding) != {"path", "sha256"}
            or not all(isinstance(value, str) for value in receipt_binding.values())
            or now.utcoffset() is None):
        return _cold_replay(root=root, receipt_binding=receipt_binding, now=now)
    key = (Path(root).resolve(), receipt_binding["path"], receipt_binding["sha256"], now)
    if key not in results:
        results[key] = _cold_replay(root=root, receipt_binding=receipt_binding, now=now)
    return deepcopy(results[key])
