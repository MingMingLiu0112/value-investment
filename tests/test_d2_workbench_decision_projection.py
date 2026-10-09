"""A security-level assessment may advance without private portfolio data."""
import pytest

from value_investment_agent.application.product import workbench


def test_current_workbench_rejects_unbound_positive_decision(tmp_path, monkeypatch):
    decision = {
        "recommendation_action": "BUY_CANDIDATE",
        "action": "no_order",
        "portfolio_input_status": "BLOCKED_PRIVATE_INPUT",
        "position_guidance": None,
    }
    outcome = {
        "status": "COMPLETED",
        "blockers": [],
        "current_status": {"status": "READY"},
        "valuation": {"status": "ready"},
        "price_bridge": {"bridge_status": "READY"},
        "price_attractiveness": {"status": "RESEARCH_ATTRACTIVE"},
        "pre_decision_eligibility": {"status": "ELIGIBLE"},
        "decision_recommendation": decision,
    }
    monkeypatch.setattr(
        workbench,
        "run_company_research_for_symbol",
        lambda **_: {"result": outcome, "receipt": {"input_sha256": {}}},
    )

    with pytest.raises(ValueError, match="replayable decision artifacts"):
        workbench.build_current_workbench_for_symbol(
            root=tmp_path,
            symbol="600887",
            output_path=tmp_path / "workbench.json",
        )
    assert not (tmp_path / "workbench.json").exists()


def test_workbench_forwards_explicit_research_dependencies(tmp_path, monkeypatch):
    """Workbenches cannot silently fall back to a package's old market snapshot."""
    expected = {
        "schedule_request": {"scope": "new-official-evidence"},
        "schedule_request_sha256": "e" * 64,
        "quote_path": tmp_path / "quote.json", "quote_sha256": "a" * 64,
        "event_path": tmp_path / "event.json", "event_sha256": "b" * 64,
        "reviews_path": tmp_path / "reviews.json", "reviews_sha256": "c" * 64,
    }
    captured = {}

    def research(**kwargs):
        captured.update(kwargs)
        raise ValueError("dependency-validation-sentinel")

    monkeypatch.setattr(workbench, "run_company_research_for_symbol", research)
    with pytest.raises(ValueError, match="dependency-validation-sentinel"):
        workbench.build_current_workbench_for_symbol(
            root=tmp_path, symbol="600887", package_path=tmp_path / "package.json",
            output_path=tmp_path / "result.json", **expected,
        )
    assert {key: captured[key] for key in expected} == expected
    assert not (tmp_path / "result.json").exists()


@pytest.mark.parametrize("inputs", [
    {"quote_path": "quote.json"}, {"event_sha256": "a" * 64},
    {"reviews_path": "reviews.json"}, {"schedule_request": {"symbol": "600887"}},
])
def test_existing_workbench_mode_rejects_fresh_inputs(tmp_path, inputs):
    with pytest.raises(ValueError, match="excludes schedule/market/review"):
        workbench.build_current_workbench_for_symbol(
            root=tmp_path, symbol="600887", output_path=tmp_path / "result.json",
            existing_manifest_path=tmp_path / "manifest.json",
            existing_manifest_sha256="b" * 64, **inputs,
        )
    assert not (tmp_path / "result.json").exists()
