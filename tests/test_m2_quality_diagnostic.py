import json
from pathlib import Path

import pytest

from value_investment_agent.application.product.m2_quality_diagnostic import diagnose_quality


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "runtime/m2-live-20261012-product-v1/receipt.json"


def test_real_quality_breakdown_is_receipt_bound():
    result = diagnose_quality(RECEIPT, ROOT)
    assert result["action"] == "no_order"
    assert result["quality_coverage_count"] == 5573
    assert result["status_counts"]["DATA_GAP"] == 4677
    assert result["status_counts"]["REJECTED"] == 775
    assert result["status_counts"]["UNSUPPORTED"] == 121
    assert result["status_counts"]["PASS"] == 0
    assert result["financial_symbol_count"] == 873


def test_fails_closed_on_coverage_mismatch(tmp_path):
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    receipt["channel_results"]["quality"]["coverage"]["rejected_count"] = 774
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="coverage mismatch"):
        diagnose_quality(path, ROOT)
