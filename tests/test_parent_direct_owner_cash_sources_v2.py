from datetime import datetime, timezone
from pathlib import Path
import hashlib
import os

import pytest

from value_investment_agent.application.research.parent_direct_owner_cash_sources_v2 import (
    LAYOUT, VERSION, read_parent_direct_owner_cash_sources_v2,
)


def _sources(root):
    result = []
    for period, folder in (("2025-12-31", "fy2025"), ("2026-06-30", "h12026")):
        relative = f"runtime/value-d2-000568-20261110/{folder}/receipt.json"
        result.append(dict(period_end=period, layout=dict(LAYOUT), receipt_binding=dict(
            path=relative, sha256=hashlib.sha256((root / relative).read_bytes()).hexdigest())))
    return result


def _read(root, sources, **overrides):
    args = dict(root=root, symbol="000568", issuer_name="泸州老窖股份有限公司",
                sources=sources, evaluated_at=datetime.now(timezone.utc))
    args.update(overrides)
    return read_parent_direct_owner_cash_sources_v2(**args)


def test_real_numbered_receipts_and_fail_closed():
    root = Path(os.environ.get("VALUE_REAL_SOURCE_ROOT", Path(__file__).resolve().parents[1]))
    if not (root / "runtime/value-d2-000568-20261110/fy2025/original.pdf").exists():
        pytest.skip("Retained official originals unavailable")
    sources = _sources(root)
    result = _read(root, sources)
    assert result["schema_version"] == VERSION
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert [s["period_end"] for s in result["statements"]] == ["2025-12-31", "2026-06-30"]
    for statement in result["statements"]:
        assert statement["balance_sheet"]["monetary_funds_cny"]["source_refs"]["sha256"]
        assert statement["income"]["parent_net_profit_cny"]["source_refs"]["physical_page"]
        for field in ("revenue", "cost"):
            assert statement["income"][field]["current"]
            assert statement["income"][field]["comparative"]
        for field in ("cfo_cny", "customer_cash_cny", "supplier_cash_cny"):
            assert statement["cash_flow"][field]["source_refs"]["excerpt"]
    with pytest.raises(ValueError):
        _read(root, sources, symbol="000569")
    with pytest.raises(ValueError):
        _read(root, sources, issuer_name="另一股份有限公司")
    bad = [dict(s) for s in sources]
    bad[0]["receipt_binding"] = dict(bad[0]["receipt_binding"], sha256="0" * 64)
    with pytest.raises(ValueError):
        _read(root, bad)
    bad = [dict(s) for s in sources]
    bad[0]["period_end"] = "2024-12-31"
    with pytest.raises(ValueError):
        _read(root, bad)
    bad = [dict(s) for s in sources]
    bad[1]["layout"] = dict(LAYOUT, income="UNKNOWN")
    with pytest.raises(ValueError, match="LAYOUT_UNSUPPORTED"):
        _read(root, bad)
