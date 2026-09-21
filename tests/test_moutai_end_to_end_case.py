import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_end_to_end_case", ROOT / "scripts" / "run_moutai_end_to_end_case.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_end_to_end_case_keeps_new_point_in_time_research_evidence_nontradeable():
    data, provenance = MODULE.load_inputs(ROOT)
    case = MODULE.build_case(data, provenance)
    chain = case["point_in_time_research_chain"]
    assert chain == {
        "annual_input_cases": 12,
        "decision_sessions": 2674,
        "input_timing_violations": 0,
        "experimental_valuation_sessions": 2603,
        "blocked_ledger_sessions": 2674,
        "blocked_ledger_orders": 0,
        "status": "年报输入、实验范围和逐日账本均为研究证据；没有正式历史价值、账户资金、成交或策略绩效。",
    }
    assert case["trade_approved"] is False
    assert case["decision"]["state"] == "research_only"


def test_main_accepts_project_relative_output_directory(monkeypatch):
    relative_output = Path("runtime/test-output/moutai-end-to-end-relative")
    absolute_output = ROOT / relative_output
    if absolute_output.exists():
        pytest.skip("The fixed regression output directory already exists")

    monkeypatch.setattr("sys.argv", ["run_moutai_end_to_end_case.py", "--output-dir", str(relative_output)])
    assert MODULE.main() == 0
    assert (absolute_output / "evidence.json").exists()
