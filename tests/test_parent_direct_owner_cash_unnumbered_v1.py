"""Evidence admission tests for the independent unnumbered source adapter."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research import parent_direct_owner_cash_unnumbered_v1 as adapter


def test_unnumbered_adapter_rejects_unbound_layout_and_cutoff(tmp_path, monkeypatch):
    now = datetime(2026, 11, 22, tzinfo=timezone.utc)
    args = dict(root=tmp_path, symbol="600887", issuer_name="某公司", evaluated_at=now)
    with pytest.raises(ValueError, match="SOURCE_CONTRACT_INVALID"):
        adapter.read_unnumbered_parent_cash(**args, sources=[
            {"period_end": "2025-12-31", "receipt_binding": {}, "layout": "fake"},
        ])
    monkeypatch.setattr(adapter, "_receipt_issuer_query", lambda **_: "某公司")
    monkeypatch.setattr(adapter, "load_retained_official_report", lambda **_: {
        "completed_at": "2026-11-23T00:00:00+00:00",
    })
    with pytest.raises(ValueError, match="ACQUISITION_AFTER_CUTOFF"):
        adapter.read_unnumbered_parent_cash(**args, sources=[
            {"period_end": "2025-12-31", "receipt_binding": {}},
        ])


def test_real_unnumbered_yili_reports(tmp_path):
    configured = os.environ.get("VALUE_UNNUMBERED_PARENT_REAL_ROOT")
    if not configured:
        pytest.skip("Explicit retained official originals required")
    root = Path(configured)
    case = json.loads((root / "config/current-operating-horizon-sources-v1.json").read_bytes())["cases"]["600887"]
    sources = [{"period_end": row["period"], "receipt_binding": row["receipt_binding"]}
               for row in case["parent_cash_observation_receipts"]]
    kwargs = dict(root=root, symbol="600887", issuer_name=case["issuer_name"],
                  sources=sources, evaluated_at=datetime.now(timezone.utc))
    result = adapter.read_unnumbered_parent_cash(**kwargs)
    annual, half_year = result["statements"]
    assert annual["cash_flow"]["closing_cash_and_equivalents_cny"]["current"] == "13404587376.75"
    assert half_year["cash_flow"]["opening_cash_and_equivalents_cny"]["current"] == "13404587376.75"
    assert annual["ordinary_shares_evidence"]["count"] == "6325360667"
    assert annual["cash_flow"]["supplier_cash_cny"]["current"] == "96773109786.96"
    assert half_year["cash_flow"]["customer_cash_cny"]["current"] == "58600086377.25"
    assert all(all(s["checks"].values()) for s in result["statements"])
    assert result["owner_cash_cny"] is None and result["action"] == "no_order"
