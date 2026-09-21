import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_conditional_inputs", ROOT / "scripts" / "build_moutai_historical_conditional_inputs.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def frozen_rows():
    return json.loads(MODULE.INPUT.read_text(encoding="utf-8"))


def test_conditional_inputs_do_not_create_approved_values_or_trades():
    package = MODULE.build(frozen_rows())
    assert package["case_count"] == 12
    assert package["formal_fair_value"] is None
    assert package["trade_approved"] is False
    for case in package["input_cases"]:
        assert case["conditional_value"] is None
        assert case["formal_fair_value"] is None
        assert case["trade_approved"] is False
        assert case["source"]["source_url"].startswith("https://static.cninfo.com.cn/")
        assert case["source"]["annual_report_document_hash"]


def test_inputs_are_point_in_time_and_preserve_denominator_blocker():
    package = MODULE.build(frozen_rows())
    for case in package["input_cases"]:
        assert case["available_at"].endswith("+08:00")
        assert any(row["status"].startswith("blocked_") for row in case["sensitivity_dimensions"]["share_denominator"])
        assert "treasury_and_distribution_denominator_unresolved" in case["blockers"]


def test_same_frozen_input_reproduces_identical_package():
    assert MODULE.build(frozen_rows()) == MODULE.build(frozen_rows())


def test_latest_package_is_research_only_when_present():
    pointer = ROOT / "runtime/strategy-validation/moutai-historical-conditional-inputs-latest.json"
    assert pointer.exists()
    reference = json.loads(pointer.read_text(encoding="utf-8"))
    package = json.loads((ROOT / reference["path"] / "evidence.json").read_text(encoding="utf-8"))
    assert package["formal_fair_value"] is None
    assert package["trade_approved"] is False
