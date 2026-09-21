from decimal import Decimal

from scripts.build_moutai_2015_price_return_beta_candidate import build


def test_price_return_beta_candidate_is_bounded_research_only():
    result = build()
    assert result["method"]["return_observations"] == 244
    assert result["method"]["minimum_observations"] == 120
    assert result["method"]["return_type"] == "unadjusted_close_to_close_price_return"
    assert Decimal(result["research_beta"]) > 0
    assert result["formal_beta_approved"] is False
    assert result["cost_of_equity_approved"] is False
    assert result["historical_replay_eligible"] is False
    assert result["trade_approved"] is False
