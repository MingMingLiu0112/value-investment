"""Direct offline tests for the versioned annual cost evidence contract."""
from copy import deepcopy
import json

import pytest

from test_operating_horizon_draft_v2 import context, valid, NOW
from value_investment_agent.application.research.agent_review import operating_horizon_annual_v3 as mod


@pytest.fixture
def paired(context):
    context["evidence"] = [row for row in context["evidence"]
                           if row["field"] not in {"revenue", "cost"}]
    for period, basis, revenue, cost in (
        ("2024-12-31", "FY", "100", "8.07"),
        ("2025-12-31", "FY", "100", "8.82"),
        ("2025-06-30", "H1", "100", "8.70"),
        ("2026-06-30", "H1", "100", "10.45"),
    ):
        for field, value in (("revenue", revenue), ("cost", cost)):
            context["evidence"].append(dict(id=(f"test:{period}:{field}" if period != "2025-12-31" else f"test:{field}"),
                source_id=f"test:{period}", pdf_sha256="a" * 64,
                available_at="2026-07-01T00:00:00+08:00", period=period,
                period_basis=basis, scope="consolidated", unit="CNY",
                field=field, value=value, text=f"{field} {value}"))
    return context


def _response():
    value = valid()
    for path in value["years"]["2026"]["operating_paths"].values():
        path["unit_cost_case"] = dict(
            mechanism="条件性采购投入价格下降，仍需核对实际采购合同",
            source_anchor_ids=["test:cost"],
            contrary_evidence_ids=["test:2026-06-30:cost"],
            reopen_condition="若下期同口径营业成本率继续上升则重新估计")
    return value


def test_four_original_pairs_and_request(paired):
    rows = mod.cost_counterevidence(paired)
    assert [row["cost_to_revenue_ratio"] for row in rows] == [
        "0.0807", "0.0882", "0.087", "0.1045"]
    request = mod.build_request(paired, [2026])
    assert "not unit costs" in request.system
    assert json.loads(request.user)["historical_cost_counterevidence"] == rows
    assert "unit_cost_case" in request.output_schema["properties"]["years"]["properties"]["2026"]["properties"]["operating_paths"]["properties"]["bull"]["required"]


@pytest.mark.parametrize("change", ["missing", "scope", "basis", "source"])
def test_pair_fails_closed(paired, change):
    row = next(row for row in paired["evidence"] if row.get("id") == "test:2026-06-30:cost")
    if change == "missing":
        paired["evidence"].remove(row)
    elif change == "scope":
        row["scope"] = "parent"
    elif change == "basis":
        row["period_basis"] = "FY"
    else:
        row["pdf_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="V3_COST_PAIR"):
        mod.cost_counterevidence(paired)


def test_scenario_declaration_required_and_unpromoted(paired):
    proposal = _response()
    original = deepcopy(proposal)
    result = mod.validate_response(json.dumps(proposal, ensure_ascii=False), paired, [2026], NOW)
    assert proposal == original
    assert result["years"]["2026"]["unit_cost_cases"]["bull"]["contrary_evidence_ids"]
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["condition_price"] is None
    proposal["years"]["2026"]["operating_paths"]["bull"].pop("unit_cost_case")
    with pytest.raises(ValueError, match="V3_UNIT_COST_CASE_REQUIRED"):
        mod.validate_response(json.dumps(proposal), paired, [2026], NOW)


def test_unknown_citation_rejected(paired):
    proposal = _response()
    proposal["years"]["2026"]["operating_paths"]["bull"]["unit_cost_case"]["contrary_evidence_ids"] = ["unknown"]
    with pytest.raises(ValueError, match="V3_UNIT_COST_CASE_CITATION_INVALID"):
        mod.validate_response(json.dumps(proposal), paired, [2026], NOW)


def test_contrary_evidence_must_include_historical_cost_pair(paired):
    proposal = _response()
    proposal["years"]["2026"]["operating_paths"]["bull"]["unit_cost_case"]["contrary_evidence_ids"] = ["test:pre_tax_profit"]
    with pytest.raises(ValueError, match="V3_HISTORICAL_COST_COUNTEREVIDENCE_REQUIRED"):
        mod.validate_response(json.dumps(proposal), paired, [2026], NOW)
