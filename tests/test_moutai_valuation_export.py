import importlib.util
import hashlib
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_valuation_export", ROOT / "scripts" / "build_moutai_valuation_result.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

REVIEW_SPEC = importlib.util.spec_from_file_location(
    "moutai_assumption_review", ROOT / "scripts" / "review_moutai_parent_equity_assumptions.py")
REVIEW = importlib.util.module_from_spec(REVIEW_SPEC)
sys.modules[REVIEW_SPEC.name] = REVIEW
REVIEW_SPEC.loader.exec_module(REVIEW)


def test_current_model_export_remains_conditional_and_low_confidence():
    payload = MODULE.build()
    result = payload["result"]
    assert result["status"] == "conditional_research_only"
    assert result["confidence"] == "低"
    assert result["current_price"] is None
    assert result["margin_to_base"] is None
    assert payload["trade_approved"] is False


def test_current_model_uses_a_retained_dated_policy_snapshot():
    pointer = json.loads((ROOT / "runtime/company-research/600519-consolidated-parent-equity-residual-income-current-latest.json").read_text(encoding="utf-8"))
    model_path = ROOT / pointer["path"] / "evidence.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
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
