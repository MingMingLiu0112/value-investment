"""Freeze the shared three-company Excel-MVP research contract."""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path

from value_investment_agent.current_research_status import (
    CURRENT_DATA_PENDING_EXTERNAL_DATA,
    CURRENT_DATA_READY,
    ENGINEERING_READY,
    current_research_status_from_payloads,
)
from value_investment_agent.price_attractiveness import STATUS_NOT_ASSESSABLE


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_POINTER = ROOT / "runtime" / "excel-mvp-research-cases-latest.json"
VALUATION_POINTERS = {
    "600519": ROOT / "runtime" / "valuation-results" / "600519-current-equity-stage-b-latest.json",
    "000333": ROOT / "runtime" / "valuation-results" / "000333-fcff-stage-b-latest.json",
    "601088": ROOT / "runtime" / "valuation-results" / "601088-cyclical-stage-b-latest.json",
}
ASSUMPTION_POINTERS = {
    "600519": ROOT / "runtime" / "valuation-assumptions" / "600519-current-latest.json",
    "601088": ROOT / "runtime" / "valuation-assumptions" / "601088-normalized-latest.json",
}
MATERIALITY_POINTER = (
    ROOT / "runtime" / "company-research" / "000333-finance-materiality-latest.json"
)


def _pinned(pointer: Path) -> tuple[dict, Path]:
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    path = ROOT / str(pin["path"]).replace("\\", "/") / "evidence.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == pin["sha256"].lower()
    return json.loads(path.read_text(encoding="utf-8")), path


def _assert_pinned_ref(ref: dict) -> None:
    if not ref.get("path") or "sha256" not in ref:
        return
    path = ROOT / str(ref["path"]).replace("\\", "/")
    assert path.is_file(), f"evidence reference is missing: {ref.get( id)}"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == ref["sha256"].lower()


def _assert_no_execution_state(payload: dict) -> None:
    for key in ("target_weight", "proposed_entry", "filled_order", "order_quantity"):
        assert key not in payload


def test_unified_freeze_pins_exactly_three_research_cases():
    payload, _ = _pinned(RESEARCH_POINTER)
    assert payload["version"] == "excel-mvp-research-cases-v1"
    assert payload["formal_trade_instructions"] is False

    records = {record["case"]["symbol"]: record for record in payload["records"]}
    assert set(records) == {"600519", "000333", "601088"}
    expected_names = {
        "600519": "贵州茅台",
        "000333": "美的集团",
        "601088": "中国神华",
    }
    allowed_gate_conclusions = {"数据不足", "研究未完成", "估值未就绪"}

    for symbol, record in records.items():
        case, gate = record["case"], record["gate"]
        assert case["name"] == expected_names[symbol]
        assert case["thesis"] and case["return_driver"] and case["mispricing_hypothesis"]
        assert case["financial_summary"]
        assert case["positives"] and case["counter_evidence"]
        assert case["thesis_breakers"] and case["next_events"]
        assert case["evidence_refs"]
        assert case["valuation_status"] == "not_ready"
        assert case["quote_date"] is None
        assert case["missing_date_reasons"].get("quote_date")
        assert gate["conclusion"] in allowed_gate_conclusions
        assert gate["conclusion"] != "估值具备研究吸引力"
        for ref in case["evidence_refs"]:
            _assert_pinned_ref(ref)


def test_three_valuation_envelopes_share_fail_closed_boundaries():
    expected = {
        "600519": {
            "version": "moutai-stage-b-valuation-result-v2",
            "model_type": "归母权益剩余收益 / 分配能力",
            "status": "conditional_research_only",
            "bridge": "READY",
            "bridge_validity": "VALID",
        },
        "000333": {
            "version": "unified-company-valuation-result-v1",
            "model_type": "FCFF",
            "status": "not_ready",
            "bridge": "PENDING_EXTERNAL_DATA",
            "bridge_validity": "UNKNOWN",
        },
        "601088": {
            "version": "unified-company-valuation-result-v1",
            "model_type": "cyclical_normalized",
            "status": "not_ready",
            "bridge": "PENDING_EXTERNAL_DATA",
            "bridge_validity": "UNKNOWN",
        },
    }
    for symbol, pointer in VALUATION_POINTERS.items():
        payload, _ = _pinned(pointer)
        contract = expected[symbol]
        result, bridge = payload["result"], payload["price_bridge"]
        assert payload["version"] == contract["version"]
        assert result["symbol"] == symbol
        assert result["model_type"] == contract["model_type"]
        assert result["status"] == contract["status"]
        assert result["confidence"] == "低"
        assert bridge["symbol"] == symbol
        assert bridge["bridge_status"] == contract["bridge"]
        assert bridge["model_validity_status"] == contract["bridge_validity"]
        assert payload["formal_fair_value"] is None
        assert payload.get("valuation_approved", False) is False
        assert payload["trade_approved"] is False
        assert payload["live_eligible"] is False
        _assert_no_execution_state(payload)
        for ref in [
            *result["evidence_refs"],
            *bridge["evidence_refs"],
            *(payload.get("model_validity") or {}).get("evidence_refs", []),
        ]:
            _assert_pinned_ref(ref)

    moutai, _ = _pinned(VALUATION_POINTERS["600519"])
    values = [
        Decimal(moutai["result"][name])
        for name in ("bear_value", "base_value", "bull_value")
    ]
    assert values[0] < values[1] < values[2]
    assert moutai["price_bridge"]["quote_date"] == "2026-09-21"
    assert moutai["price_bridge"]["current_price"] == "1252.57"
    assert moutai["model_validity"]["status"] == "VALID"
    assert moutai["valuation_route"]["profile_id"] == "quality_compounder"
    assert moutai["valuation_route"]["status"] == "SUPPORTED"

    midea, _ = _pinned(VALUATION_POINTERS["000333"])
    assert midea["valuation_route"]["profile_id"] == "mature_manufacturing"
    assert midea["valuation_route"]["status"] == "SUPPORTED"
    assert midea["valuation_applicability"]["policy"]["symbol"] == "000333"
    research_pin = json.loads(RESEARCH_POINTER.read_text(encoding="utf-8"))
    assert midea["research_case_ref"]["sha256"] == research_pin["sha256"]

    shenhua, _ = _pinned(VALUATION_POINTERS["601088"])
    assert (shenhua["result"]["bear_value"], shenhua["result"]["base_value"],
            shenhua["result"]["bull_value"]) == (None, None, None)
    assert shenhua["price_bridge"]["current_price"] is None
    assert shenhua["price_bridge"]["margin_to_base"] is None


def test_assumptions_materiality_and_shared_status_never_unlock_trading():
    moutai_assumptions, _ = _pinned(ASSUMPTION_POINTERS["600519"])
    assert moutai_assumptions["symbol"] == "600519"
    assert moutai_assumptions["mapping_only"] is True
    assert moutai_assumptions["parameters_changed"] is False
    assert moutai_assumptions["valuation_recalculated"] is False
    assert moutai_assumptions["assumption_set"]["status"] == "READY"
    assert moutai_assumptions["trade_approved"] is False

    shenhua_assumptions, _ = _pinned(ASSUMPTION_POINTERS["601088"])
    assert shenhua_assumptions["symbol"] == "601088"
    assert shenhua_assumptions["assumption_set"]["status"] == "PARTIAL"
    assert shenhua_assumptions["registered_model_inputs"] is False
    assert shenhua_assumptions["valuation_recalculated"] is False
    assert shenhua_assumptions["formal_fair_value"] is None
    assert shenhua_assumptions["trade_approved"] is False

    materiality, _ = _pinned(MATERIALITY_POINTER)
    assert materiality["symbol"] == "000333"
    assert materiality["assessment"]["materiality"] == "LOW"
    assert materiality["industrial_fcff_carve_out"] == "MODEL_NOT_APPLICABLE"
    assert materiality["applicability_effect"]["model_unlocked"] is False
    assert materiality["trade_approved"] is False

    research_payload, _ = _pinned(RESEARCH_POINTER)
    cases = {
        record["case"]["symbol"]: record
        for record in research_payload["records"]
    }
    expected = {
        "600519": ("估值未就绪", CURRENT_DATA_READY),
        "000333": ("数据不足", CURRENT_DATA_PENDING_EXTERNAL_DATA),
        "601088": ("研究未完成", CURRENT_DATA_PENDING_EXTERNAL_DATA),
    }
    for symbol, (conclusion, data_status) in expected.items():
        payload, _ = _pinned(VALUATION_POINTERS[symbol])
        status = current_research_status_from_payloads(
            cases[symbol]["gate"],
            payload["result"],
            payload["price_bridge"],
        )
        assert status.symbol == symbol
        assert status.engineering_status == ENGINEERING_READY
        assert status.research_conclusion == conclusion
        assert status.current_data_status.status == data_status
        assert status.price_attractiveness.status == STATUS_NOT_ASSESSABLE
        assert "估值具备研究吸引力" not in status.display_text
        policy = status.as_policy()
        for key in ("trade", "order", "position", "target_weight", "shares"):
            assert key not in policy
