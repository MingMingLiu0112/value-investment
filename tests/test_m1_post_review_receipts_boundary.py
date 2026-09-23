"""Keep the one-off M1 receipt generator out of production paths."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_PATHS = (
    ROOT / "src" / "value_investment_agent" / "research_application.py",
    ROOT / "src" / "value_investment_agent" / "research_batch.py",
    ROOT / "src" / "value_investment_agent" / "research_gate.py",
    ROOT / "src" / "value_investment_agent" / "valuation_router.py",
    ROOT / "src" / "value_investment_agent" / "price_attractiveness.py",
    ROOT / "src" / "value_investment_agent" / "pre_decision_eligibility.py",
)


def test_one_off_receipt_builder_is_not_imported_by_production_paths():
    forbidden = "build_m1_post_review_receipts"
    offenders = [
        path.relative_to(ROOT)
        for path in PRODUCTION_PATHS
        if forbidden in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
