from __future__ import annotations

import copy

import pytest

from value_investment_agent.presentation.read_models.product_workbench import (
    ACTION_NO_ORDER,
    PRODUCT_WORKBENCH_SCHEMA_VERSION,
    product_workbench_from_payload,
)


SHA = "a" * 64


def _assessment(
    *,
    status: str,
    available: bool,
    value_text: str | None = None,
    reason: str | None = None,
    needed: str | None = None,
) -> dict:
    return {
        "status": status,
        "available": available,
        "value_text": value_text,
        "unavailable_reason": reason,
        "needed_evidence": needed,
        "evidence_refs": ["evidence-1"],
    }


def _payload() -> dict:
    return {
        "schema_version": PRODUCT_WORKBENCH_SCHEMA_VERSION,
        "generated_at": "2026-09-26T03:00:00+00:00",
        "as_of": "2026-09-25",
        "action": ACTION_NO_ORDER,
        "overview": {"pending_count": 2},
        "system_health": {
            "status": "EVIDENCE_INSUFFICIENT",
            "message": "部分输入仍待人工复核。",
        },
        "stages": {
            "m2": {"status": "PENDING_HUMAN_REVIEW", "detail": "等待人工复核。"},
            "m3": {"status": "PARTIAL", "detail": "研究资料仍在补齐。"},
            "m4": {
                "status": "PENDING_USER_PRIVATE_INPUT",
                "detail": "尚未收到真实组合输入。",
            },
            "m5": {"status": "PENDING_HUMAN_REVIEW", "detail": "有事件待复核。"},
            "m6": {
                "status": "PREFLIGHT_DONE",
                "detail": "真实监控尚未开始。",
            },
        },
        "audit": {
            "evidence": [
                {
                    "evidence_id": "evidence-1",
                    "title": "固定测试证据",
                    "artifact_type": "research_payload",
                    "path": "runtime/fixture.json",
                    "sha256": SHA,
                    "available_at": "2026-09-25",
                    "action": ACTION_NO_ORDER,
                }
            ]
        },
        "today_items": [
            {
                "category": "PRICE_WATCH",
                "company": "测试公司",
                "symbol": "600000",
                "what_happened": "价格进入预设关注范围。",
                "why_it_matters": "需要检查上游研究结论是否仍然有效。",
                "current_status": "等待人工复核。",
                "next_step": "核对最新价格与研究时点。",
                "evidence_refs": ["evidence-1"],
            }
        ],
        "opportunities": [
            {
                "symbol": "600000",
                "company_name": "测试公司",
                "why_now": "价格状态已变化。",
                "research_status": "WAIT_FOR_PRICE",
                "valuation_status": "AVAILABLE",
                "dividend_status": "INSUFFICIENT_EVIDENCE",
                "price_status": "IN_WATCH_RANGE",
                "main_risk": "价格变化不等于投资结论。",
                "next_trigger": "等待人工复核。",
                "evidence_refs": ["evidence-1"],
            }
        ],
        "companies": [
            {
                "symbol": "600000",
                "company_name": "测试公司",
                "research_status": "PARTIAL",
                "price": _assessment(
                    status="AVAILABLE",
                    available=True,
                    value_text="上游价格 10 元",
                ),
                "valuation": _assessment(
                    status="AVAILABLE",
                    available=True,
                    value_text="上游估值结果",
                ),
                "margin_of_safety": _assessment(
                    status="NOT_READY",
                    available=False,
                    reason="估值输入尚未复核。",
                    needed="同一时点估值输入。",
                ),
                "dividend": _assessment(
                    status="INSUFFICIENT_EVIDENCE",
                    available=False,
                    reason="股息证据不足。",
                    needed="多财年分配与现金流证据。",
                ),
                "sections": [
                    {
                        "key": key,
                        "status": "PARTIAL",
                        "summary": f"{key} 研究摘要。",
                        "evidence_refs": ["evidence-1"],
                    }
                    for key in (
                        "business_quality",
                        "financial_quality",
                        "capital_allocation",
                        "valuation",
                        "dividend",
                        "risks_counterevidence",
                    )
                ],
                "scenarios": [
                    {
                        "key": key,
                        "assessment": _assessment(
                            status="NOT_READY",
                            available=False,
                            reason=f"{key} 情景输入尚未复核。",
                            needed="同口径情景假设。",
                        ),
                    }
                    for key in ("bear", "base", "bull")
                ],
                "latest_change": "价格进入关注范围。",
                "next_trigger": "等待人工复核。",
                "original_thesis": "高质量经营与现金回报。",
                "thesis_change": "UNKNOWN",
                "evidence_refs": ["evidence-1"],
            }
        ],
        "portfolio": {
            "real_data_available": False,
            "status": "PENDING_USER_PRIVATE_INPUT",
            "connection_hint": "通过受保护的 M4 入口接入真实组合。",
            "summary": [],
            "positions": [],
            "action": ACTION_NO_ORDER,
        },
        "events": [
            {
                "event_id": "event-1",
                "event_type": "MATERIAL_REQUIRES_RECALCULATION",
                "company_name": "测试公司",
                "what_happened": "发生需要复核的重大事项。",
                "impact_area": "投资逻辑。",
                "current_conclusion": "等待人工判断。",
                "research_action": "REOPEN_RESEARCH",
                "next_step": "补充事件后证据。",
                "evidence_refs": ["evidence-1"],
            }
        ],
    }


def test_model_translates_internal_statuses_but_keeps_audit_code() -> None:
    model = product_workbench_from_payload(_payload())

    opportunity = model.opportunities[0]
    assert opportunity.research_status.code == "WAIT_FOR_PRICE"
    assert opportunity.research_status.user_label == "研究完成，等待价格"
    assert opportunity.dividend_status.user_label == "股息证据不足"
    assert model.stage_summaries[0].status.code == "PENDING_HUMAN_REVIEW"
    assert model.stage_summaries[1].status.user_label == "研究资料仍在补齐"
    assert model.action == ACTION_NO_ORDER


def test_execution_keys_fail_closed_at_any_depth() -> None:
    payload = _payload()
    payload["opportunities"][0]["position_size"] = 0

    with pytest.raises(ValueError, match="execution keys"):
        product_workbench_from_payload(payload)


def test_nested_actions_must_remain_no_order() -> None:
    payload = _payload()
    payload["portfolio"]["action"] = "buy"

    with pytest.raises(ValueError, match="no_order"):
        product_workbench_from_payload(payload)


def test_unavailable_valuation_cannot_carry_placeholder_value() -> None:
    payload = _payload()
    payload["companies"][0]["valuation"]["available"] = False
    payload["companies"][0]["valuation"]["value_text"] = "0"
    payload["companies"][0]["valuation"]["unavailable_reason"] = "估值输入未复核。"
    payload["companies"][0]["valuation"]["needed_evidence"] = "同一时点输入。"

    with pytest.raises(ValueError, match="cannot carry"):
        product_workbench_from_payload(payload)


def test_unavailable_valuation_keeps_reason_and_needed_evidence() -> None:
    model = product_workbench_from_payload(_payload())
    valuation = model.companies[0].scenarios[0].assessment

    assert valuation.value_text is None
    assert valuation.unavailable_reason == "bear 情景输入尚未复核。"
    assert valuation.needed_evidence == "同口径情景假设。"


def test_absent_portfolio_cannot_carry_simulated_metrics() -> None:
    payload = _payload()
    payload["portfolio"]["summary"] = [
        {"key": "total_assets", "value_text": "1,000,000"}
    ]

    with pytest.raises(ValueError, match="simulated or absent"):
        product_workbench_from_payload(payload)


def test_real_portfolio_values_are_displayed_verbatim() -> None:
    payload = _payload()
    metric_labels = {
        "total_assets": "上游总资产",
        "cash": "上游现金",
        "holdings": "上游持仓",
        "industry_exposure": "上游行业暴露",
        "single_stock_concentration": "上游集中度",
        "cyclical_exposure": "上游周期暴露",
        "estimated_annual_dividend": "上游预计股息",
        "normalized_annual_dividend": "上游正常化股息",
        "stock_position": "上游股票仓位",
        "portfolio_risk": "上游风险表述",
    }
    payload["portfolio"] = {
        "real_data_available": True,
        "portfolio_provenance": {
            "confirmation_receipt_fingerprint": {
                "schema_version": "m4-portfolio-confirmation-fingerprint-v1",
                "action": ACTION_NO_ORDER,
                "receipt_schema_version": "m4-portfolio-confirmation-receipt-v1",
                "receipt_sha256": SHA,
                "sensitivity": "PUBLIC_FINGERPRINT_ONLY",
            },
            "reconciled": True,
        },
        "status": "REAL_DATA_AVAILABLE",
        "connection_hint": "真实组合已接入。",
        "summary": [
            {"key": key, "value_text": value}
            for key, value in metric_labels.items()
        ],
        "positions": [
            {
                "symbol": "600000",
                "company_name": "测试公司",
                "current_position_text": "上游当前仓位",
                "allowed_capacity_text": "上游容量结论：12%",
                "current_risk_text": "上游风险结论",
                "continuation_review": "ALLOWED",
                "reason": "上游给出的继续复核理由。",
                "evidence_refs": ["evidence-1"],
                "action": ACTION_NO_ORDER,
            }
        ],
        "action": ACTION_NO_ORDER,
    }

    model = product_workbench_from_payload(payload)

    assert model.portfolio.positions[0].allowed_capacity_text == "上游容量结论：12%"
    assert model.portfolio.positions[0].continuation_review.user_label == "允许进入继续复核"


def test_real_portfolio_without_confirmation_provenance_is_refused() -> None:
    payload = _payload()
    payload["portfolio"] = {
        "real_data_available": True,
        "status": "REAL_DATA_AVAILABLE",
        "connection_hint": "真实组合已接入。",
        "summary": [
            {"key": "total_assets", "value_text": "1,000,000"},
            {"key": "stock_position", "value_text": "12%"},
        ],
        "positions": [
            {
                "symbol": "600000",
                "company_name": "测试公司",
                "current_position_text": "12%",
                "allowed_capacity_text": "8%",
                "current_risk_text": "上游风险结论。",
                "continuation_review": "ALLOWED",
                "reason": "上游给出的继续复核理由。",
                "evidence_refs": ["evidence-1"],
                "action": ACTION_NO_ORDER,
            }
        ],
        "action": ACTION_NO_ORDER,
    }

    model = product_workbench_from_payload(payload)

    assert model.portfolio.real_data_available is False
    assert model.portfolio.status.code == "PENDING_USER_PRIVATE_INPUT"
    assert model.portfolio.status.user_label == "尚未接入真实组合"
    assert model.portfolio.summary == ()
    assert model.portfolio.positions == ()
    assert "1,000,000" not in model.portfolio.connection_hint
    assert "12%" not in model.portfolio.connection_hint


def test_unknown_internal_status_fails_closed() -> None:
    payload = _payload()
    payload["opportunities"][0]["research_status"] = "M2_VERIFIED"

    with pytest.raises(ValueError, match="Unknown opportunity.research_status"):
        product_workbench_from_payload(payload)


def test_missing_evidence_reference_fails_closed() -> None:
    payload = _payload()
    payload["events"][0]["evidence_refs"] = ["missing-evidence"]

    with pytest.raises(ValueError, match="missing audit evidence"):
        product_workbench_from_payload(payload)


def test_all_wait_empty_candidate_is_legal() -> None:
    payload = _payload()
    payload["today_items"] = []
    payload["opportunities"] = []
    payload["companies"] = []
    payload["events"] = []
    payload["audit"]["evidence"] = []
    payload["stages"] = {
        key: {"status": "WAIT", "detail": f"{key} 等待输入。"}
        for key in ("m2", "m3", "m4", "m5", "m6")
    }
    payload["portfolio"] = {
        "real_data_available": False,
        "status": "NOT_STARTED",
        "connection_hint": "尚未接入真实组合。",
        "summary": [],
        "positions": [],
        "action": ACTION_NO_ORDER,
    }

    model = product_workbench_from_payload(copy.deepcopy(payload))

    assert model.today_items == ()
    assert model.opportunities == ()
    assert model.companies == ()
    assert model.events == ()
    assert model.audit_evidence == ()
    assert model.portfolio.summary == ()
    assert all(stage.status.code == "WAIT" for stage in model.stage_summaries)
