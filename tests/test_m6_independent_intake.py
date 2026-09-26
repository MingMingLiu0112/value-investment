from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime
import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from value_investment_agent.m6_independent_intake import (
    PURPOSE, VERSION, verify_independent_intake_chain,
)


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _fixture(raws=(b"session-receipt-1", b"session-receipt-2")):
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()
    deployment = "a" * 64
    records = []
    previous = None
    for sequence, raw in enumerate(raws, 1):
        payload = {
            "action": "no_order", "intake_id": "independent-intake-1",
            "key_epoch": "2026-q3", "deployment_sha256": deployment,
            "receipt_sha256": hashlib.sha256(raw).hexdigest(),
            "received_at": f"2026-09-24T15:{10 + sequence}:00+08:00",
            "sequence": sequence, "previous_record_sha256": previous,
        }
        envelope = {"version": VERSION, "payload": payload,
                    "signature": key.sign(PURPOSE + _bytes(payload)).hex()}
        previous = hashlib.sha256(_bytes(envelope)).hexdigest()
        records.append({"receipt_raw_base64": base64.b64encode(raw).decode(), "record": envelope})
    trust = {"intake_id": "independent-intake-1", "intake_public_key": public,
             "key_epoch": "2026-q3", "deployment_sha256": deployment}
    head = {"record_sha256": previous, "sequence": 2,
            "pinned_at": "2026-09-24T15:13:00+08:00"}
    cutoff = datetime.fromisoformat("2026-09-24T15:15:00+08:00")
    return records, trust, head, cutoff


def test_independent_intake_binds_raw_receipts_chain_and_external_head():
    records, trust, head, cutoff = _fixture()
    verified = verify_independent_intake_chain(records, trust, head, cutoff=cutoff)
    assert set(verified) == {
        hashlib.sha256(b"session-receipt-1").hexdigest(),
        hashlib.sha256(b"session-receipt-2").hexdigest(),
    }


def test_re_signed_duplicate_raw_receipt_still_fails_single_chain_use():
    records, trust, head, cutoff = _fixture((b"same-receipt", b"same-receipt"))
    with pytest.raises(ValueError, match="repeats receipt bytes"):
        verify_independent_intake_chain(records, trust, head, cutoff=cutoff)


@pytest.mark.parametrize("change", ["raw", "sequence", "deployment", "head", "time", "key_epoch"])
def test_independent_intake_fails_closed_for_rewrite_or_wrong_scope(change):
    records, trust, head, cutoff = _fixture()
    records, trust, head = deepcopy(records), dict(trust), dict(head)
    if change == "raw":
        records[0]["receipt_raw_base64"] = base64.b64encode(b"swapped").decode()
    elif change == "sequence":
        records[1]["record"]["payload"]["sequence"] = 3
    elif change == "deployment":
        trust["deployment_sha256"] = "b" * 64
    elif change == "head":
        head["record_sha256"] = "c" * 64
    elif change == "time":
        head["pinned_at"] = "2026-09-24T16:00:00+08:00"
    else:
        trust["key_epoch"] = "wrong"
    with pytest.raises(ValueError):
        verify_independent_intake_chain(records, trust, head, cutoff=cutoff)
