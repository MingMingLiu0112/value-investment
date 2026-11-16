"""Synthetic model/codec tests; no current research, market price or approval."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal as D, localcontext
import json

import pytest

from test_direct_parent_owner_cash_v1 import inputs
from test_residual_income_equity_valuation import case, complete_facts, confidence_evidence
from value_investment_agent.domain.valuation.direct_parent_owner_cash_v1 import compile_direct_owner_cash_path
from value_investment_agent.valuation_models import direct_owner_cash_v1 as model
from value_investment_agent.valuation_models.residual_income import ResidualIncomeValuationTiming
from value_investment_agent.valuation_models.residual_income_path_v2 import ResidualIncomePathScenarioInputs


def scenario(cost="0.08", *, data=None):
    data = deepcopy(data if data is not None else inputs())
    data["cost_of_equity"] = cost
    result = compile_direct_owner_cash_path(**data)
    return model.DirectOwnerCashScenario(
        symbol="600519", opening=data["opening"], years=data["years"], terminal=data["terminal"],
        ordinary_shares=D(data["ordinary_shares"]), cost_of_equity=D(cost),
        forecast_roes=tuple(D(row["roe_assumption"]) for row in result["annual_rows"]),
        forecast_retentions=tuple(D(row["retention_assumption"]) for row in result["annual_rows"]),
    )


def facts(**changes):
    return complete_facts(**(dict(
        operating_inputs=dict(start_book_equity=D(1000), ordinary_shares=D(100), opening_cash=D(20)),
        scenario_inputs={name: scenario(cost) for name, cost in zip(model.SCENARIOS, (".10", ".08", ".06"))},
    ) | changes))


def test_model_delegates_exactly_and_preserves_inputs(monkeypatch):
    f, c = facts(confidence_evidence=confidence_evidence()), case()
    before = deepcopy((f, c))
    calls = []
    original = model.compile_direct_owner_cash_path

    def observed(**kwargs):
        result = original(**kwargs)
        calls.append(result)
        return result

    monkeypatch.setattr(model, "compile_direct_owner_cash_path", observed)
    value = model.DirectOwnerCashValuationModel().value(f, c)
    assert value.model_version == "direct-owner-cash-equity-v1"
    assert value.status == "conditional_research_only"
    assert value.confidence == "高"
    assert value.base_value == 10
    assert value.bear_value < value.base_value < value.bull_value
    assert list(value.assumptions["scenario_calculations"].values()) == calls
    assert len(calls) == 3
    assert value.assumptions["action"] == "no_order"
    assert value.assumptions["working_capital_cash_component"] is None
    assert not value.assumptions["legal_distribution_capacity_certified"]
    assert not value.assumptions["formal_eligibility"]
    assert (f, c) == before


def test_annual_cash_retention_is_not_averaged():
    data = inputs()
    data["years"][0]["policy"]["operating_cash"] = "50"
    data["years"].append(dict(year=2028, policy=deepcopy(data["terminal"]["policy"])))
    s = scenario(data=data)
    assert isinstance(s, ResidualIncomePathScenarioInputs)
    result = model.scenario_calculation(facts(), s)
    assert s.forecast_retentions == (D(".625"), D(0))
    assert [D(row["conditional_distribution_cny"]) for row in result["annual_rows"]] == [30, 80]
    assert abs(D(result["crosscheck_difference_cny"])) < D("1e-30")
    with pytest.raises(ValueError, match="ANNUAL_VECTOR_MISMATCH"):
        model.scenario_calculation(facts(), replace(s, forecast_retentions=(D(".3125"),) * 2))
    with pytest.raises(ValueError, match="ANNUAL_VECTOR_MISMATCH"):
        model.scenario_calculation(facts(), replace(s, forecast_roes=(D(".08"),) * 2))


@pytest.mark.parametrize("changes", [
    {"verified": False}, {"blockers": ["unresolved"]}, {"operating_inputs": {}},
    {"scenario_inputs": None}, {"scenario_inputs": {}},
    {"scenario_inputs": {"bear": scenario()}},
    {"scenario_inputs": {"bear": scenario(), "base": scenario(), "bull": {}}},
])
def test_input_gates_precede_compiler(monkeypatch, changes):
    f = facts(**changes)

    def forbidden(**kwargs):
        pytest.fail("unverified or malformed inputs reached cash arithmetic")

    monkeypatch.setattr(model, "compile_direct_owner_cash_path", forbidden)
    value = model.DirectOwnerCashValuationModel().value(f, case())
    assert value.status == "not_ready" and value.base_value is None
    assert value.blockers


@pytest.mark.parametrize("key,value", [
    ("start_book_equity", D(1001)), ("ordinary_shares", D(101)),
    ("opening_cash", D(21)), ("opening_cash", D("NaN")),
    ("ordinary_shares", D("Infinity")), ("start_book_equity", D(0)),
    ("opening_debt", D(1)), ("opening_distribution_capacity", D(1)),
])
def test_fact_basis_must_match(key, value):
    f = facts()
    with pytest.raises(ValueError, match="FACT_BASIS"):
        model.DirectOwnerCashValuationModel().value(
            replace(f, operating_inputs=f.operating_inputs | {key: value}), case())


@pytest.mark.parametrize("changes", [
    {"currency": "USD"}, {"scope": "CONSOLIDATED"}, {"symbol": "invalid"},
    {"cost_of_equity": D("NaN")}, {"cost_of_equity": D(0)},
    {"ordinary_shares": D("100.5")}, {"forecast_roes": (D("NaN"),)},
    {"forecast_retentions": (D("1.1"),)}, {"forecast_retentions": ()},
    {"forecast_retentions": [D(0)]}, {"retention": D(".5")},
    {"terminal_growth": D(".01")}, {"terminal_roe": D(".08")},
])
def test_invalid_typed_inputs(changes):
    with pytest.raises(ValueError):
        replace(scenario(), **changes)


def test_symbol_evidence_and_scenario_order_rejections():
    f = facts()
    with pytest.raises(ValueError, match="symbols must match"):
        model.DirectOwnerCashValuationModel().value(replace(f, symbol="000333"), case())
    with pytest.raises(ValueError, match="SCENARIO_SYMBOL_MISMATCH"):
        model.scenario_calculation(f, replace(scenario(), symbol="000333"))
    with pytest.raises(ValueError, match="named evidence"):
        model.DirectOwnerCashValuationModel().value(
            replace(f, evidence_refs=[]), replace(case(), evidence_refs=[]))
    with pytest.raises(ValueError, match="conflict"):
        model.DirectOwnerCashValuationModel().value(
            replace(f, evidence_refs=[dict(id="case", sha256="changed")]), case())
    with pytest.raises(ValueError, match="bear <= base <= bull"):
        model.DirectOwnerCashValuationModel().value(replace(f, scenario_inputs={
            "bear": f.scenario_inputs["bull"], "base": f.scenario_inputs["base"],
            "bull": f.scenario_inputs["bear"]}), case())
    # Dictionary insertion order cannot relabel bear/base/bull.
    reordered = replace(f, scenario_inputs=dict(reversed(list(f.scenario_inputs.items()))))
    assert model.DirectOwnerCashValuationModel().value(reordered, case()) == model.DirectOwnerCashValuationModel().value(f, case())


@pytest.mark.parametrize("change", ["capacity", "debt", "years"])
def test_three_scenarios_share_opening_state_and_calendar(change):
    f = facts()
    data = inputs()
    if change == "capacity":
        data["opening"]["capacity"] = "1"
    elif change == "debt":
        data["opening"]["debt"] = "1"
        data["years"][0]["policy"].update(debt_repayment="1", investment_cash_received="1")
    else:
        data["years"][0]["year"] = 2028
    altered = replace(f, scenario_inputs=f.scenario_inputs | {"base": scenario(data=data)})
    with pytest.raises(ValueError, match="SCENARIO_(OPENING_STATE|YEARS)_MISMATCH"):
        model.DirectOwnerCashValuationModel().value(altered, case())


def test_timing_is_explicitly_unsupported():
    timing = ResidualIncomeValuationTiming(
        datetime.fromisoformat("2025-01-01T00:00:00+08:00"),
        datetime.fromisoformat("2025-06-01T00:00:00+08:00"), ({"id": "timing"},))
    f = facts(valuation_timing=timing)
    for calculate in (lambda: model.DirectOwnerCashValuationModel().value(f, case()),
                      lambda: model.scenario_calculation(f, scenario()),
                      lambda: model.facts_to_payload(f)):
        with pytest.raises(ValueError, match="VALUATION_TIMING_UNSUPPORTED"):
            calculate()


def test_nested_inputs_detached_and_mutation_rechecked():
    s = scenario()
    original = deepcopy(s.years)
    other = replace(s)
    other.years[0]["policy"]["operating_cash"] = "50"
    assert s.years == original
    with pytest.raises(ValueError, match="ANNUAL_VECTOR_MISMATCH"):
        model.scenario_calculation(facts(), other)
    other.years[0]["policy"]["operating_wc_cash_cny"] = "0"
    with pytest.raises(ValueError, match="EXACT_FIELDS"):
        model.scenario_calculation(facts(), other)


def test_lossless_explicit_codec_and_decimal_context():
    f = facts()
    payload = model.facts_to_payload(f)
    encoded = json.loads(json.dumps(payload, allow_nan=False))
    restored = model.facts_from_payload(encoded)
    assert restored == f
    assert model.facts_to_payload(restored) == payload
    assert encoded["scenario_inputs"]["base"]["years"] == f.scenario_inputs["base"].years
    assert encoded["scenario_inputs"]["base"]["terminal"] == f.scenario_inputs["base"].terminal
    expected = model.DirectOwnerCashValuationModel().value(f, case())
    with localcontext() as context:
        context.prec = 5
        assert model.DirectOwnerCashValuationModel().value(restored, case()) == expected
        assert context.prec == 5
    encoded["scenario_inputs"]["base"]["years"][0]["policy"]["operating_cash"] = "50"
    assert f.scenario_inputs["base"].years[0]["policy"]["operating_cash"] == "100"
    with pytest.raises(ValueError, match="ANNUAL_VECTOR_MISMATCH"):
        model.DirectOwnerCashValuationModel().value(model.facts_from_payload(encoded), case())


@pytest.mark.parametrize("change", ["extra", "version", "float", "missing", "v2"])
def test_serialization_refuses_implicit_or_lossy_contracts(change):
    payload = model.scenario_to_payload(scenario())
    if change == "extra": payload["forecast_retention"] = "0"
    if change == "version": payload["scenario_contract"] = "v2"
    if change == "float": payload["cost_of_equity"] = 0.08
    if change == "missing": del payload["terminal"]
    if change == "v2": payload = {"retention_contract": "annual-retention-v2"}
    with pytest.raises(ValueError):
        model.scenario_from_payload(payload)


def test_injected_repository_real_service_and_bundle_preserve_raw_inputs():
    """A test-only thin repository proves the mainline injection seam, not a global fix."""
    from test_research_application import quality_spec
    from value_investment_agent.research_application import ResearchApplicationService
    from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository
    from value_investment_agent.research_artifacts import ResearchArtifactEnvelope, ARTIFACT_FINANCIAL_FACTS
    from value_investment_agent.application.product.company_research import _serialize_outcome
    from value_investment_agent.research_profile import PROFILES
    from value_investment_agent.valuation_router import ValuationRouter

    class DirectTestRepository(InMemoryResearchArtifactRepository):
        def save_object(self, value, *, identity, evidence_refs=(), run_id, advance_head=True):
            if identity.artifact_type != ARTIFACT_FINANCIAL_FACTS:
                return super().save_object(value, identity=identity, evidence_refs=evidence_refs,
                                          run_id=run_id, advance_head=advance_head)
            return self.save(ResearchArtifactEnvelope.build(
                identity=identity, payload=model.facts_to_payload(value),
                evidence_refs=evidence_refs, run_id=run_id), advance_head=advance_head)

    default_before = ValuationRouter().route(PROFILES["quality_compounder"]).model_factory
    spec, _ = quality_spec(run_id="TEST_ONLY_direct_owner_service")
    f = facts(evidence_refs=spec.facts.evidence_refs)
    spec = replace(spec, facts=f, model_version=model.MODEL_VERSION,
                   requested_model=model.MODEL_ID, quote=None, valuation_approval=None)
    repository = DirectTestRepository()
    service = ResearchApplicationService(repository=repository,
                                        router=model.build_direct_owner_cash_router())
    result = service.run_company_research(spec)
    assert result.valuation.model_version == model.MODEL_VERSION
    assert result.valuation.base_value == D(10)
    assert result.valuation.status == "conditional_research_only"
    assert result.decision_recommendation.action == "no_order"
    assert result.decision_recommendation.position_guidance is None
    saved = next(x for x in result.stored_artifacts if x.envelope.identity.artifact_type == ARTIFACT_FINANCIAL_FACTS)
    payload = saved.envelope.payload_object()
    assert payload == model.facts_to_payload(f)
    restored = model.facts_from_payload(payload)
    assert model.DirectOwnerCashValuationModel().value(restored, spec.research_case) == result.valuation
    bundle = _serialize_outcome(result)["artifact_bundle"]
    bundled = next(x for x in bundle["artifacts"] if x["identity"]["artifact_type"] == ARTIFACT_FINANCIAL_FACTS)
    assert json.loads(bundled["canonical_payload"]) == payload
    assert ValuationRouter().route(PROFILES["quality_compounder"]).model_factory is default_before
    assert default_before is not model.DirectOwnerCashValuationModel
    with pytest.raises(ValueError, match="version differs"):
        service.run_company_research(replace(spec, model_version="wrong-version"))
