"""Direct replay of the acquired official issuer original; no model calls."""
from datetime import datetime, timezone
from pathlib import Path
import json

import pytest

from value_investment_agent.application.research.agent_review import issuer_dividend_plan_v2 as plan


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "artifacts/current/d2-issuer-dividend-plan-v2/receipt.json"
NOW = datetime(2026, 11, 11, 14, 0, tzinfo=timezone.utc)


def test_real_issuer_pdf_replay_has_exact_years_ratio_pages_and_pit():
    result = plan.read_issuer_dividend_plan(ROOT, RECEIPT, now=NOW)
    assert result["fiscal_years"] == [2024, 2025, 2026]
    assert result["minimum_ratios"] == ["0.75"] * 3
    assert result["profit_basis"] == "consolidated_parent_attributable"
    assert result["physical_pages"] == [1, 2]
    assert result["source_binding"]["sha256"] == "31a299d0d492960f3bd709822c27cce12e5364f8a9c6d7a551f4f48a479e8ae9"
    assert result["available_at"] >= result["fetched_at"]
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert "shareholder approval" in result["approval_condition"]
    assert "later years" in result["limitation"]


def test_future_acquisition_rejected():
    with pytest.raises(ValueError, match="NOT_YET_ACQUIRED"):
        plan.read_issuer_dividend_plan(ROOT, RECEIPT,
            now=datetime(2024, 8, 10, tzinfo=timezone.utc))


def test_changed_original_bytes_rejected(tmp_path):
    receipt_data = json.loads(RECEIPT.read_text(encoding="utf-8"))
    target = tmp_path / receipt_data["path"]
    target.parent.mkdir(parents=True)
    target.write_bytes((ROOT / receipt_data["path"]).read_bytes() + b"changed")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(receipt_data), encoding="utf-8")
    with pytest.raises(ValueError, match="PDF_HASH_CHANGED"):
        plan.read_issuer_dividend_plan(tmp_path, receipt, now=NOW)


@pytest.mark.parametrize("change", [
    {"symbol": "000568"}, {"source_url": "https://example.org/plan.pdf"},
    {"sha256": "0" * 64}, {"document_date": "2024-08-08"},
])
def test_changed_receipt_identity_or_bytes_rejected(tmp_path, change):
    source = json.loads(RECEIPT.read_text(encoding="utf-8"))
    source.update(change)
    # A copied original remains under the independent replay root.
    target = tmp_path / source["path"]
    target.parent.mkdir(parents=True)
    target.write_bytes((ROOT / source["path"]).read_bytes())
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(source), encoding="utf-8")
    with pytest.raises(ValueError, match="RECEIPT_IDENTITY_INVALID|PDF_HASH_CHANGED"):
        plan.read_issuer_dividend_plan(tmp_path, receipt, now=NOW)


@pytest.mark.parametrize("fragment", ["75%", "股东大会审议通过", "长期发展不受影响"])
def test_disclosure_or_condition_change_rejected(monkeypatch, fragment):
    pages = plan.extract_pages(ROOT / json.loads(RECEIPT.read_text(encoding="utf-8"))["path"])
    monkeypatch.setattr(plan, "extract_pages", lambda _: [
        plan._compact(page).replace(fragment, "已删除") for page in pages])
    with pytest.raises(ValueError, match="DISCLOSURE_TEXT_CHANGED"):
        plan.read_issuer_dividend_plan(ROOT, RECEIPT, now=NOW)
