import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_2012_comparative_nwc", ROOT / "scripts" / "recover_moutai_2012_comparative_nwc.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_extract_pair_handles_spaced_labels_and_requires_two_amounts():
    text = "应 付 职 工 薪 酬 （二十一） 260,284,491.74 269,657,755.58"
    assert MODULE.extract_pair(text, "应付职工薪酬") == ("260284491.74", "269657755.58")
    assert MODULE.extract_pair("应付票据", "应付票据") is None


def test_comparative_receipt_preserves_unknowns_and_never_promotes_a_trade():
    result = MODULE.build()
    assert result["source_id"] == "cninfo:63720184"
    assert result["comparative_period"] == "2012-12-31"
    assert result["fields"]["inventory"]["comparative_2012_cny"] == "9665727593.42"
    assert result["fields"]["notes_payable"]["comparative_2012_cny"] is None
    assert result["comparative_nwc_input_complete"] is False
    assert result["operating_nwc_approved"] is False
    assert result["formal_fair_value"] is None
    assert result["trade_approved"] is False
