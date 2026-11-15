from decimal import Decimal

import pytest

from value_investment_agent.infrastructure.filings.parent_working_capital_cash import (
    read_parent_working_capital_cash,
)


NOTE = """（三）母公司现金流量表补充资料
补充资料 本期数 上年同期数
1. 将净利润调节为经营活动现金流量：
存货的减少（增加以“－”号填列） 20.00 -30.00
经营性应收项目的减少（增加以“－”号填
列） -80.00 100.00
经营性应付项目的增加（减少以“－”号填列） 70.00 -90.00
经营活动产生的现金流量净额 100.00 120.00
"""
CFO = (Decimal("100.00"), Decimal("120.00"))


def test_exact_parent_note_reconciles_signed_periods():
    result = read_parent_working_capital_cash(["cover", NOTE], verified_parent_cfo_cny=CFO)
    assert result["physical_page"] == 2
    assert result["cash_impact_cny"] == ["10.00", "-20.00"]
    assert result["field"] == "working_capital_cash_component"
    assert result["action"] == "no_order"


@pytest.mark.parametrize(("note", "cfo"), [
    (NOTE.replace("母公司", "合并"), CFO),
    (NOTE.replace(" 20.00 -30.00", " 20.00"), CFO),
    (NOTE, CFO[::-1]),
    (NOTE + NOTE, CFO),
])
def test_group_missing_duplicate_or_mismatched_periods_fail_closed(note, cfo):
    with pytest.raises(ValueError):
        read_parent_working_capital_cash([note], verified_parent_cfo_cny=cfo)

def test_source_overlay_rejects_changed_file_and_checks_direct_statement(tmp_path, monkeypatch):
    from hashlib import sha256
    from value_investment_agent.application.research.agent_review import (
        operating_horizon_sources_parent_wc as source,
    )

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    pdf = runtime / "source.pdf"
    pdf.write_bytes(b"TEST_ONLY")
    digest = sha256(pdf.read_bytes()).hexdigest()
    record = {
        "path": "runtime/source.pdf", "sha256": digest, "source_id": "TEST_ONLY",
        "period": "2025-12-31", "available_at": "2026-04-01T00:00:00+00:00",
        "receipt_binding": {"sha256": "b" * 64},
    }
    context = {"symbol": "600001", "issuer_name": "测试", "supplemental_sources": [record]}
    monkeypatch.setattr(source.base.legacy.pdf_text, "extract_pages", lambda _: [NOTE])
    monkeypatch.setattr(source.parent_cash, "observe_parent_cash_rows", lambda **_: {
        "rows": {"cfo_cny": {"columns": [{"value": str(c)} for c in CFO]}},
    })
    evidence, = source._cash_rows(tmp_path, context)
    assert evidence["pdf_sha256"] == digest and evidence["receipt_binding"] == record["receipt_binding"]
    assert evidence["field"] == "working_capital_cash_component" and evidence["value"] == "10.00"
    assert evidence["scope"] == "ISSUER_PARENT_STANDALONE"
    pdf.write_bytes(b"TEST_ONLY_CHANGED")
    with pytest.raises(ValueError, match="PARENT_WC_ORIGINAL_HASH_MISMATCH"):
        source._cash_rows(tmp_path, context)
