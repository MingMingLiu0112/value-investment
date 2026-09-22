from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_daily_execution_preparation_requires_all_dated_evidence_steps():
    script = (ROOT / "scripts" / "prepare_moutai_current_execution_contract.py").read_text(encoding="utf-8")
    for name in ("assess_moutai_current_suspension.py", "archive_current_fee_sources.py",
                 "build_current_sse_fee_policy.py", "build_moutai_prior_liquidity_budget.py",
                 "build_moutai_current_execution_contract.py",
                 "build_moutai_daily_simulation_policy.py"):
        assert name in script
    assert 'contract.get("execution_ready") is not True' in script
    assert 'contract.get("trade_approved") is not False' in script
    assert 'strftime("%Y%m%dT%H%M%SZ")' in script
    assert 'current-sse-paper-fee-policy-{valid}-{run_id}' in script
    assert 'contract["output"]) / "evidence.json"' in script
    assert 'Daily simulation policy dates do not match' in script
