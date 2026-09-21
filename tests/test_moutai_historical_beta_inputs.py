from pathlib import Path

from scripts.audit_moutai_historical_beta_inputs import build


def test_beta_audit_keeps_complete_company_prices_separate_from_benchmark_admission():
    result = build()
    company = result["company_close_input"]
    assert company["sessions"] == 2674
    assert company["unadjusted_secondary_coverage_sessions"] == 2674
    assert company["unexplained_peer_dates"] == 0
    assert result["benchmark_input_status"] == "rejected_total_return_not_point_in_time"
    assert result["predecision_company_return_window"]["status"] == "secondary_unadjusted_candidate_crosschecked_research_only"
    assert result["predecision_company_return_window"]["sessions"] == 245
    assert result["beta_policy_status"] == "blocked_missing_frozen_beta_policy_and_matched_point_in_time_benchmark"
    assert result["beta_estimated"] is False
    assert result["historical_replay_eligible"] is False
    assert result["trade_approved"] is False
