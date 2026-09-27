from __future__ import annotations
import json
from pathlib import Path
from value_investment_agent.m5_event_watermark import watermark_ledger_from_payload
ROOT = Path(__file__).resolve().parents[1]
def test_prospective_watermarks_are_scoped_monotonic_and_no_order():
    payload = json.loads((ROOT / "config" / "prospective-public-event-watermarks-v1.json").read_text(encoding="utf-8"))
    ledger = watermark_ledger_from_payload(payload)
    assert {item.scope for item in ledger.watermarks()} == {"prospective:000333", "prospective:600887", "prospective:601088"}
    assert ledger.current(scope="prospective:600887", source="cninfo").coverage_status == "COMPLETE"
    assert ledger.current(scope="prospective:000333", source="cninfo").coverage_status == "INCOMPLETE"
