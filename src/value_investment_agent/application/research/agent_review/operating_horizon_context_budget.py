"""Measure source context size without repeatedly charging identical provenance."""
from copy import deepcopy

from .task_execution_v1 import _bytes, _hash


def measure_compact_context_chars(context: dict) -> int:
    """Count a reversible representation of the complete, unchanged context.

    The compact representation is only a size measurement. Neither model
    requests nor source validation consume it.
    """
    packed = deepcopy(context)
    shared_receipts = []
    for row in packed["evidence"]:
        if "receipt_binding" in row:
            binding = row.pop("receipt_binding")
            if binding not in shared_receipts:
                shared_receipts.append(binding)
            row["receipt_binding"] = shared_receipts.index(binding)
        # Only a digest reproduced from exact text can use the compact marker.
        if "text_sha256" in row and row["text_sha256"] == _hash(row["text"].encode("utf-8")):
            row["text_sha256"] = True
    return len(_bytes([packed, shared_receipts]).decode("utf-8"))
