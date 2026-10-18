from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from test_read_api import _fixture

from value_investment_agent.application.product.research_draft import (
    load_current_research_draft,
)


NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
DRAFT_PATH = "artifacts/current/test-draft/public-draft-v1.json"
ROOT = Path(__file__).resolve().parents[2]


def _draft() -> dict:
    return {
        "schema_version": "public-research-draft-v1",
        "action": "no_order",
        "symbol": "000333",
        "company_name": "美的集团",
        "run_id": "midea-draft-test",
        "research_version": "midea-draft-test-v1",
        "status": "RESEARCH_DRAFT_NOT_APPROVED",
        "research_as_of": "2026-10-16",
        "available_at": "2026-10-17T10:22:15+00:00",
        "financial_period": "2026-06-30",
        "summary": "条件性研究摘要",
        "valuation": {
            "model_type": "residual_income_or_equity_value",
            "model_version": "residual-income-equity-shared-dated-v2",
            "valuation_date": "2026-10-16",
            "status": "conditional_research_only",
            "confidence": "低",
            "currency": "CNY",
            "scope": "conditional",
            "scenarios": [
                {"scenario": "bear", "per_share_value": "36.01"},
                {"scenario": "base", "per_share_value": "45.74"},
                {"scenario": "bull", "per_share_value": "58.17"},
            ],
            "assumptions": [],
        },
        "model_validity": {"status": "UNKNOWN", "blockers": ["EVENT_MATERIALITY_PENDING"]},
        "quote_fact": {
            "quote_date": "2026-10-16",
            "current_price": "84.60",
            "currency": "CNY",
            "status": "VERIFIED_CLOSE_NOT_ADMITTED",
        },
        "price_bridge": {
            "status": "INVALID",
            "price_admitted": False,
            "margin_to_bear": None,
            "margin_to_base": None,
            "blockers": ["MODEL_VALIDITY_UNKNOWN"],
            "reason": "模型有效性尚未建立。",
            "needed_evidence": "完成公告材料性复核。",
        },
        "gates": {"results": {"G0_证据门": True, "G3_估值门": False}},
        "events": {"status": "PENDING_HUMAN_REVIEW", "pending_count": 1, "items": []},
        "counter_evidence": ["半年报利润下降"],
        "thesis_breakers": ["ROE持续低于门槛"],
        "next_events": ["下一期定期报告"],
        "reopen_triggers": ["完成公告复核"],
        "limitations": ["候选假设未经人工批准"],
        "boundary": "研究草稿不等于买卖建议，正式决策仍为待研究。",
        "evidence": [],
        "version_comparison": {
            "from": {"status": "INSUFFICIENT_PUBLIC_EVIDENCE", "research_version": "old-v5"},
            "to": {"status": "RESEARCH_DRAFT_NOT_APPROVED", "research_version": "new-v1"},
            "changed": ["共享剩余收益模型已执行"],
            "unchanged": ["正式G3仍未通过"],
        },
    }


def _publish(root, payload: dict | None = None, *, path: str = DRAFT_PATH) -> str:
    value = _draft() if payload is None else payload
    encoded = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encoded)
    digest = hashlib.sha256(encoded).hexdigest()
    pointer = root / "config/current-research-drafts.json"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(
        json.dumps(
            {
                "schema_version": "current-research-drafts-v1",
                "action": "no_order",
                "drafts": {"000333": {"path": path, "sha256": digest}},
            }
        ),
        encoding="utf-8",
    )
    return digest


def _snapshot_with_midea() -> dict:
    return {
        "opportunities": [
            {
                "symbol": "600741",
                "company_name": "Huayu",
                "action": "no_order",
                "valuation_status": {"code": "NOT_READY"},
                "why_now": "Research intake",
            },
            {
                "symbol": "000333",
                "company_name": "Midea",
                "action": "no_order",
                "valuation_status": {"code": "NOT_READY"},
                "why_now": "Conditional research draft",
            },
        ]
    }


def test_valid_draft_loads_only_from_approved_artifacts(tmp_path):
    _publish(tmp_path)
    loaded = load_current_research_draft(tmp_path, "000333", now=NOW)
    assert loaded is not None
    assert loaded["valuation"]["model_version"] == "residual-income-equity-shared-dated-v2"
    assert loaded["price_bridge"]["price_admitted"] is False


def test_historical_midea_draft_is_preserved_and_readable(tmp_path):
    historical = json.loads((ROOT / "artifacts/current/midea-draft-20261017/public-draft-v2.json").read_text(encoding="utf-8"))
    _publish(tmp_path, historical)
    loaded = load_current_research_draft(tmp_path, "000333", now=datetime.now(timezone.utc))
    assert loaded is not None
    assert loaded["run_id"] == "midea-draft-20261017-v2"
    assert loaded["status"] == "RESEARCH_DRAFT_NOT_APPROVED"
    assert loaded["model_validity"]["status"] == "UNKNOWN"
    assert loaded["price_bridge"]["price_admitted"] is False
    assert loaded["quote_fact"]["current_price"] == "84.60"
    assert len(loaded["events"]["items"]) == 4
    assert loaded["version_comparison"]["from"]["research_version"] == "midea-draft-20261016-v1"
    assert loaded["version_comparison"]["to"]["research_version"] == "midea-draft-20261017-v2"
    assert {row["scenario"] for row in loaded["valuation"]["scenarios"]} == {
        "bear",
        "base",
        "bull",
    }


def test_path_outside_approved_artifacts_fails_closed(tmp_path):
    _publish(tmp_path, path="runtime/research-drafts/000333/v1.json")
    assert load_current_research_draft(tmp_path, "000333", now=NOW) is None


def test_hash_symbol_future_and_forbidden_fields_all_fail_closed(tmp_path):
    _publish(tmp_path)
    target = tmp_path / DRAFT_PATH
    target.write_text(target.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert load_current_research_draft(tmp_path, "000333", now=NOW) is None

    mismatch = _draft()
    mismatch["symbol"] = "600519"
    _publish(tmp_path, mismatch)
    assert load_current_research_draft(tmp_path, "000333", now=NOW) is None

    future = _draft()
    future["available_at"] = "2026-10-18T00:00:00+00:00"
    _publish(tmp_path, future)
    assert load_current_research_draft(tmp_path, "000333", now=NOW) is None

    execution = _draft()
    execution["position_guidance"] = None
    _publish(tmp_path, execution)
    assert load_current_research_draft(tmp_path, "000333", now=NOW) is None

    g3_open = deepcopy(_draft())
    g3_open["gates"]["results"]["G3_估值门"] = True
    _publish(tmp_path, g3_open)
    assert load_current_research_draft(tmp_path, "000333", now=NOW) is None


def test_draft_is_a_separate_api_field_and_never_changes_formal_decision(tmp_path):
    client = _fixture(tmp_path, snapshot_overrides=_snapshot_with_midea())
    before = client.get("/api/v1/decisions/000333").json()
    assert before["status"] == "PENDING_RESEARCH"
    assert before["decision"]["status"] == "PENDING_RESEARCH"
    assert "research_draft" not in before

    _publish(tmp_path)
    after = client.get("/api/v1/decisions/000333").json()
    assert after["status"] == "PENDING_RESEARCH"
    assert after["decision"] == before["decision"]
    assert after["publication"]["publication_id"] == before["publication"]["publication_id"]
    assert after["research_draft"]["status"] == "RESEARCH_DRAFT_NOT_APPROVED"
    assert after["research_draft"]["action"] == "no_order"
    assert after["research_draft"]["price_bridge"]["price_admitted"] is False


def test_broken_draft_does_not_break_the_formal_decision_page(tmp_path):
    client = _fixture(tmp_path, snapshot_overrides=_snapshot_with_midea())
    _publish(tmp_path)
    target = tmp_path / DRAFT_PATH
    target.write_bytes(target.read_bytes() + b"corrupt")
    response = client.get("/api/v1/decisions/000333")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PENDING_RESEARCH"
    assert body["decision"]["status"] == "PENDING_RESEARCH"
    assert "research_draft" not in body
