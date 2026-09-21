import importlib.util
from datetime import date, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_thesis", ROOT / "scripts/assess_moutai_current_thesis.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_current_thesis_is_dated_and_keeps_counterevidence():
    model, _ = MODULE.pinned_json(__import__('json').loads(MODULE.MODEL_POINTER.read_text(encoding='utf-8')))
    result = MODULE.build(datetime.fromisoformat(model['valuation_at']).date())
    assert result["thesis_intact"] is True
    assert result["status"] == "confirmed_with_counterevidence"
    assert result["evidence"]["issuer_interim_basis"]["source_id"] == "cninfo:1225475868"
    assert result["counterevidence"]
    assert result["trade_approved"] is False


def test_current_thesis_rejects_a_date_outside_its_evidence_scope():
    model, _ = MODULE.pinned_json(__import__('json').loads(MODULE.MODEL_POINTER.read_text(encoding='utf-8')))
    model_date = datetime.fromisoformat(model['valuation_at']).date()
    try:
        MODULE.build(date.fromordinal(model_date.toordinal() - 1))
    except ValueError as error:
        assert "limited" in str(error)
    else:
        raise AssertionError("Expected a dated-evidence rejection")
