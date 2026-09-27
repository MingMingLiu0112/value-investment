from __future__ import annotations
import json
from pathlib import Path
import pytest
from value_investment_agent.application.product.prospective_baseline import build_prospective_baselines
ROOT = Path(__file__).resolve().parents[1]
def test_baselines_build_an_append_only_no_order_ledger(tmp_path: Path):
    root = tmp_path / "project"; (root / "config").mkdir(parents=True)
    source = root / "config" / "input.json"; source.write_text((ROOT / "config" / "prospective-baseline-input-v1.json").read_text(encoding="utf-8"), encoding="utf-8")
    result = build_prospective_baselines(root=root, input_path=source, output_path=root / "runtime" / "baseline.json")
    assert result["action"] == "no_order"
    assert {card["symbol"] for card in result["cards"]} == {"000333", "600887", "601088"}
    assert all(row["classification"] == "BASELINE_FACT" for row in result["observation_ledger"])
def test_future_fact_is_rejected(tmp_path: Path):
    root = tmp_path / "project"; (root / "config").mkdir(parents=True)
    data = json.loads((ROOT / "config" / "prospective-baseline-input-v1.json").read_text(encoding="utf-8")); data["cases"][1]["known_facts"][0]["available_at"] = "2026-10-01T00:00:00+08:00"
    source = root / "config" / "input.json"; source.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="future fact"):
        build_prospective_baselines(root=root, input_path=source, output_path=root / "runtime" / "baseline.json")
