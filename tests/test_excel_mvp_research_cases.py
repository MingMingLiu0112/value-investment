import hashlib
import json
from pathlib import Path

from openpyxl import Workbook

from value_investment_agent.workbook_simple_overview import _mvp_research_card


ROOT = Path(__file__).resolve().parents[1]


def test_stage_a_cases_are_pinned_complete_and_not_promoted_to_valuation():
    pointer = json.loads((ROOT / "runtime/excel-mvp-research-cases-latest.json").read_text(encoding="utf-8"))
    evidence = ROOT / pointer["path"] / "evidence.json"
    assert hashlib.sha256(evidence.read_bytes()).hexdigest() == pointer["sha256"]
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["formal_trade_instructions"] is False
    records = {record["case"]["symbol"]: record for record in payload["records"]}
    assert set(records) == {"600519", "000333", "601088"}
    for record in records.values():
        case, gate = record["case"], record["gate"]
        assert case["financial_summary"]
        assert case["thesis"] and case["return_driver"] and case["mispricing_hypothesis"]
        assert case["positives"] and case["counter_evidence"]
        assert case["thesis_breakers"] and case["next_events"]
        assert case["evidence_refs"]
        assert case["valuation_status"] == "not_ready"
        assert gate["conclusion"] == "估值未就绪"
        assert gate["blockers"]


def test_stage_a_case_evidence_references_are_hash_addressable():
    payload = json.loads((ROOT / "runtime/excel-mvp-research-cases/evidence.json").read_text(encoding="utf-8"))
    for record in payload["records"]:
        for ref in record["case"]["evidence_refs"]:
            target = ROOT / ref["path"]
            assert target.exists(), ref
            assert hashlib.sha256(target.read_bytes()).hexdigest() == ref["sha256"]


def test_mvp_card_displays_same_day_research_margins_without_trade_promotion():
    workbook = Workbook()
    sheet = workbook.active
    record = {
        "case": {
            "name": "贵州茅台", "symbol": "600519", "industry": "高端白酒",
            "investment_path": "成熟优质复利", "research_status": "financial_scope_approved",
            "thesis": "测试论点", "return_driver": "测试回报", "mispricing_hypothesis": "未证明",
            "financial_summary": {"period_end": "2026-06-30"}, "financial_period": "2026-06-30",
            "positives": [], "counter_evidence": [], "thesis_breakers": [], "next_events": [],
            "evidence_status": "verified", "evidence_refs": [],
        },
        "gate": {"conclusion": "估值未就绪", "blockers": ["G3_估值模型通过"]},
    }
    valuation = {
        "bear_value": "400", "base_value": "500", "bull_value": "600", "valuation_date": "2026-09-21",
        "confidence": "低", "current_price": "550", "margin_to_bear": "-0.375", "margin_to_base": "-0.1",
        "blockers": ["低置信度不得升级为研究吸引力"], "status": "conditional_research_only",
        "assumptions": {"reverse_valuation": {"quote_date": "2026-09-21", "quote_price_cny": "550"}},
    }
    _mvp_research_card(sheet, 1, record, valuation)
    text = "\n".join(str(cell.value) for row in sheet.iter_rows() for cell in row if cell.value)
    assert "同日绑定价格：550.00 元/股；相对熊/基准情景：-37.5% / -10.0%。" in text
    assert "条件研究（非交易）" in text
    assert "financial_scope_approved" not in text
    assert "财务范围已核验" in text
    assert "买入" not in text
    assert "订单" in text


def test_mvp_card_displays_unified_unready_valuation_without_values():
    workbook = Workbook()
    sheet = workbook.active
    record = {
        "case": {"name": "美的集团", "symbol": "000333", "industry": "家电",
                 "investment_path": "成长价值", "research_status": "financial_scope_blocked",
                 "thesis": "测试论点", "return_driver": "测试回报", "mispricing_hypothesis": "未证明",
                 "financial_summary": {}, "financial_period": "2025-09-30", "positives": [],
                 "counter_evidence": [], "thesis_breakers": [], "next_events": [],
                 "evidence_status": "partial", "evidence_refs": []},
        "gate": {"conclusion": "估值未就绪", "blockers": ["G3_估值模型通过"]},
    }
    valuation = {"symbol": "000333", "model_type": "FCFF", "valuation_date": "2025-09-30",
                 "bear_value": None, "base_value": None, "bull_value": None, "confidence": "低",
                 "blockers": ["ordinary_shares_not_verified"], "status": "not_ready"}

    _mvp_research_card(sheet, 1, record, valuation)

    text = "\n".join(str(cell.value) for row in sheet.iter_rows() for cell in row if cell.value)
    assert "模型：FCFF；估值未就绪。" in text
    assert "ordinary_shares_not_verified" in text
    assert "买入" not in text
