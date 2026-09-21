import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "chinabond_2014",
    ROOT / "scripts" / "inspect_moutai_historical_chinabond_government_2014.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_pinned_2014_government_curve_has_target_date_and_ten_year_point():
    result = MODULE.build()

    assert result["curve_identity"] == "中债国债收益率曲线(到期)"
    assert result["first_observation_date"] == "2014-01-02"
    assert result["last_observation_date"] == "2014-12-31"
    assert len(result["target_date_rows"]) == 21
    assert result["target_ten_year_yield_percent"] == 3.6219
    assert result["rate_input_status"] == "candidate_requires_tenor_and_publication_contract_review"
    assert result["valuation_approved"] is False
    assert result["trade_approved"] is False
