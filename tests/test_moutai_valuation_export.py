import importlib.util
import hashlib
import json
from pathlib import Path
import sys

import pytest

from value_investment_agent.valuation_models.residual_income import QualityCompounderFacts
from value_investment_agent.valuation_router import ROUTE_SUPPORTED


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MODEL = (
    ROOT
    / "runtime/company-research"
    / "600519-consolidated-parent-equity-residual-income-current-20260921T124252Z"
    / "evidence.json"
)
FROZEN_ADMISSION = (
    ROOT
    / "runtime/company-research"
    / "600519-current-valuation-admission-20260921T124253Z"
    / "evidence.json"
)
FROZEN_DIAGNOSTIC = (
    ROOT
    / "runtime/company-research"
    / "600519-current-assumption-diagnostic-20260921T124253Z"
    / "evidence.json"
)
FROZEN_HASHES = {
    FROZEN_MODEL: "8ffe43ccf6acba184496eec12d7ed65082ec91d4ba38f7cfd5604a32fe648f30",
    FROZEN_ADMISSION: "443aeae6be01760bcbda512c7097d7882df5241d2c964d320938bdce4183b556",
    FROZEN_DIAGNOSTIC: "044c81d7224673f0765ad00059a6df40f2b68086f1138139a2818380c47fc1b2",
}
pytestmark = pytest.mark.skipif(
    not all(path.is_file() for path in FROZEN_HASHES),
    reason="frozen 2026-09-21 Moutai snapshots are not available in a clean checkout",
)
SPEC = importlib.util.spec_from_file_location("moutai_valuation_export", ROOT / "scripts" / "build_moutai_valuation_result.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

REVIEW_SPEC = importlib.util.spec_from_file_location(
    "moutai_assumption_review", ROOT / "scripts" / "review_moutai_parent_equity_assumptions.py")
REVIEW = importlib.util.module_from_spec(REVIEW_SPEC)
sys.modules[REVIEW_SPEC.name] = REVIEW
REVIEW_SPEC.loader.exec_module(REVIEW)


def _frozen_payload() -> dict:
    for path, expected in FROZEN_HASHES.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    return MODULE.build(
        FROZEN_DIAGNOSTIC,
        model_evidence=FROZEN_MODEL,
        admission_evidence=FROZEN_ADMISSION,
    )


def test_current_model_export_remains_conditional_and_low_confidence():
    payload = _frozen_payload()
    result = payload["result"]
    assert result["status"] == "conditional_research_only"
    assert result["confidence"] == "低"
    assert "current_price" not in result
    assert "margin_to_base" not in result
    assert payload["model_validity"]["status"] == "VALID"
    assert payload["price_bridge"]["bridge_status"] == "READY"
    assert payload["price_bridge"]["quote_date"] == "2026-09-21"
    assert payload["price_bridge"]["current_price"] == "1252.57"
    assert payload["price_bridge"]["quote_status"] == "verified_close"
    assert payload["trade_approved"] is False
    assert any("优势持续期已审计为有界假设" in blocker for blocker in result["blockers"])
    assert any("全年2026母公司可分配现金" in blocker for blocker in result["blockers"])
    assert not any("尚未独立验证" in blocker for blocker in result["blockers"])
    route = payload["valuation_route"]
    assert route["profile_id"] == "quality_compounder"
    assert route["status"] == ROUTE_SUPPORTED
    assert route["model_type"] == "residual_income_or_equity_value"
    assert route["model_factory"] == "ResidualIncomeEquityValuationModel"
    assert route["facts_contract"] == QualityCompounderFacts.__name__
    assert "symbol" not in route


def test_current_pointer_retains_the_dated_matched_close_bridge():
    payload = _frozen_payload()

    assert payload["price_bridge"]["bridge_status"] == "READY"
    assert payload["price_bridge"]["quote_date"] == "2026-09-21"
    assert payload["price_bridge"]["current_price"] == "1252.57"
    assert payload["price_bridge"]["quote_status"] == "verified_close"
    assert payload["trade_approved"] is False


def test_current_model_accepts_a_same_date_matched_close_bridge():
    payload = _frozen_payload()

    assert payload["result"]["status"] == "conditional_research_only"
    assert payload["price_bridge"]["bridge_status"] == "READY"
    assert payload["price_bridge"]["quote_date"] == "2026-09-21"
    assert payload["price_bridge"]["current_price"] == "1252.57"
    assert payload["price_bridge"]["quote_status"] == "verified_close"
    assert payload["trade_approved"] is False


def test_current_model_uses_a_retained_dated_policy_snapshot():
    assert hashlib.sha256(FROZEN_MODEL.read_bytes()).hexdigest() == FROZEN_HASHES[FROZEN_MODEL]
    model = json.loads(FROZEN_MODEL.read_text(encoding="utf-8"))
    policy_path = ROOT / model["policy"]["path"]
    assert policy_path.is_file()
    assert "runtime/company-research/600519-current-equity-policy-" in model["policy"]["path"].replace("\\", "/")
    assert hashlib.sha256(policy_path.read_bytes()).hexdigest() == model["policy"]["sha256"]
    assert model["model_policy"]["event_coverage_date"] == model["valuation_at"][:10]


def test_cross_date_diagnostic_cannot_be_attached_as_current_price():
    old = ROOT / "runtime/company-research/600519-current-assumption-diagnostic-20260917T014020Z/evidence.json"
    with pytest.raises(ValueError, match="current pinned model"):
        MODULE.build(old)


def test_archived_model_with_missing_exact_policy_refuses_replay():
    model = ROOT / "runtime/company-research/600519-consolidated-parent-equity-residual-income-current-20260914T115828Z/evidence.json"
    admission = ROOT / "runtime/company-research/600519-current-valuation-admission-20260914T105257Z/evidence.json"
    quote = ROOT / "runtime/quote-sessions/20260914T105221815291Z/report.json"
    assert admission.exists()
    with pytest.raises(ValueError, match="policy changed"):
        REVIEW.review_current(quote, model)
