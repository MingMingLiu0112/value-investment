from datetime import datetime, timezone
import json

import pytest

from value_investment_agent.application.research.agent_review import horizon_queue_receipts_v2 as batch


@pytest.mark.parametrize("fault", ["conflict", "non_object", "broken_pin", "duplicate_period"])
def test_reads_both_registries_and_isolates_bad_entry(tmp_path, monkeypatch, fault):
    now = datetime(2026, 11, 16, tzinfo=timezone.utc)
    queue = {"sha256": "a" * 64}
    symbols = ["600001", "600002", "600003"]
    monkeypatch.setattr(batch, "read_sse_research_pool", lambda **_: {
        "status": "AVAILABLE", "queue_binding": queue,
        "items": [{"symbol": symbol} for symbol in symbols],
    })

    def entry(symbol, suffix=""):
        return {
            "issuer_name": symbol,
            "parent_cash_observation_receipts": [
                {"period": period, "receipt_binding": {"path": f"{symbol}-{period}{suffix}"}}
                for period in batch.legacy.REQUIRED_PERIODS
            ],
        }

    def write(relative, value):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    write(batch.legacy.horizon.CONFIG, {
        "schema_version": batch.legacy.horizon.VERSION, "action": "no_order",
        "cases": {symbol: entry(symbol) for symbol in symbols[:2]},
    })
    variants = {symbols[1]: entry(symbols[1], "-different"), symbols[2]: entry(symbols[2])}
    if fault == "non_object":
        variants[symbols[1]] = None
    elif fault == "broken_pin":
        variants[symbols[1]]["parent_cash_observation_receipts"] = [{"period": []}]
    elif fault == "duplicate_period":
        pins = variants[symbols[1]]["parent_cash_observation_receipts"]
        pins.append(pins[0])
    write(batch.alternate.CONFIG, variants)
    expected_reason = ("HORIZON_SELECTION_REGISTRY_CONFLICT" if fault == "conflict"
                       else "HORIZON_SELECTION_REGISTRY_ENTRY_INVALID")
    replayed = []

    def replay(*, symbol, **kwargs):
        replayed.append(symbol)
        return {"status": "SOURCE_REPLAYED_SELECTION_PROPOSAL", "evidence_ids": ["a"]}

    monkeypatch.setattr(batch.legacy, "prepare_receipt_selection", replay)
    receipt = batch.persist_current_queue_receipt_batch(
        queue_root=tmp_path, research_root=tmp_path, expected_queue=queue, budget=3, as_of=now,
    )
    assert replayed == [symbols[0], symbols[2]]
    assert receipt["result"]["items"][1]["reason"] == expected_reason
    view = batch.read_queue_receipt_batch(
        research_root=tmp_path, queue_binding=queue, as_of=now,
    )
    assert view["sha256"] == receipt["binding"]["sha256"]
    assert view["items"][1]["reason_code"] == expected_reason
    assert view["items"][2]["reason_code"] is None
    variants.pop(symbols[2])
    write(batch.alternate.CONFIG, variants)
    assert batch.read_queue_receipt_batch(research_root=tmp_path, queue_binding=queue, as_of=now) is None
