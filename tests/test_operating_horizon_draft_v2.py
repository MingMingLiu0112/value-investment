from copy import deepcopy
import json
import pytest
from test_operating_horizon_draft_v1 import context, payload, NOW
from value_investment_agent.application.research.agent_review import operating_horizon_draft_v2 as mod


def valid():
    p=payload([2026])
    for path in p["years"]["2026"]["operating_paths"].values():
        path["unit_cost_mechanism"]="UNRESOLVED_SENSITIVITY"
        path["drivers"]["other_pretax_cny"]["evidence_ids"]=["test:pre_tax_profit"]
    return p


def test_separate_cost_mechanism_and_residual_anchor(context):
    p=valid();original=deepcopy(p)
    out=mod.validate_response(json.dumps(p),context,[2026],NOW)
    assert p==original
    assert out["quantification_status"].startswith("CONDITIONAL_SENSITIVITY")
    assert out["years"]["2026"]["unit_cost_mechanisms"]["base"]=="UNRESOLVED_SENSITIVITY"
    assert out["formal_eligibility"] is False

@pytest.mark.parametrize("change,code",[("parent","PARENT_CASH"),("missing","RESIDUAL_ANCHOR"),("scale","COST_MECHANISM")])
def test_cash_scope_and_scale_cannot_become_residual_or_extra_efficiency(context,change,code):
    p=valid();path=p["years"]["2026"]["operating_paths"]["base"]
    if change=="scale":path["unit_cost_mechanism"]="FIXED_COST_DILUTION"
    elif change=="missing":path["drivers"]["other_pretax_cny"]["evidence_ids"]=["test:revenue"]
    else:
        row=deepcopy(context["evidence"][0]);row.update(id="test:parent_cash",scope="parent",field="parent_investment_cash")
        context["evidence"].append(row)
        path["drivers"]["other_pretax_cny"]["evidence_ids"].append(row["id"])
    with pytest.raises(ValueError,match=code):mod.validate_response(json.dumps(p),context,[2026],NOW)


def test_prompt_requires_official_interim_and_disallows_double_count(context):
    req=mod.build_request(context,[2026])
    assert "never count scale dilution again" in req.system
    assert "unit=not_quantified" in req.system


def test_residual_anchor_must_match_actual_baseline_not_another_period(context):
    p=valid()
    row=deepcopy(context["evidence"][-1])
    row.update(id="test:interim_pbt",period="2026-06-30",period_basis="H1")
    context["evidence"].append(row)
    p["years"]["2026"]["operating_paths"]["base"]["drivers"]["other_pretax_cny"]["evidence_ids"]=[row["id"]]
    with pytest.raises(ValueError,match="RESIDUAL_ANCHOR"):
        mod.validate_response(json.dumps(p),context,[2026],NOW)
    p["years"]["2026"]["operating_paths"]["base"]["drivers"]["other_pretax_cny"]["evidence_ids"].append("test:pre_tax_profit")
    assert mod.validate_response(json.dumps(p),context,[2026],NOW)["action"]=="no_order"
