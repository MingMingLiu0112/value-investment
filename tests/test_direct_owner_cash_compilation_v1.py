"""TEST_ONLY compiler contracts; retained originals have separate real receipts."""
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal
import pytest
from value_investment_agent.application.research import direct_owner_cash_compilation_v1 as compiler
from value_investment_agent.application.research import direct_owner_cash_research_v1 as runner

NOW=datetime(2026,11,16,tzinfo=timezone.utc)
def assumption(value):
    return dict(classification="FORECAST_ASSUMPTION",value=value,evidence_anchors=["profit"],
        rationale="TEST_ONLY explicit policy",counter_evidence="TEST_ONLY adverse cash conversion",
        reopen_condition="TEST_ONLY new facts")
def sample(monkeypatch):
    vals=dict(book_equity_cny="1000",closing_cash_and_equivalents_cny="20",
              parent_net_profit_cny="80",revenue="200",cost="100",shares="100")
    statement=dict(period_end="2025-12-31",balance_sheet={},cash_flow={},income={}, ordinary_shares_evidence=dict(period_end="2025-12-31",unit="shares",scope="TOTAL_ISSUED_ORDINARY_SHARES",count="100",source_refs={"id":"TEST_ONLY"}))
    anchors={}
    for name,value in vals.items():
        section="cash_flow" if name=="closing_cash_and_equivalents_cny" else "balance_sheet"
        statement[section][name]=dict(current=value,comparative=value)
        anchors[name]=dict(period_end="2025-12-31",section=section,field=name,column="current")
    anchors["profit"]=anchors["parent_net_profit_cny"]
    observed=dict(symbol="600519",scope=compiler.SCOPE,currency="CNY",classification="FACT",
        period_start="2025-01-01",period_end="2025-12-31",revenue="200",cost="100",
        customer_cash="200",supplier_cash="100",cfo="100",source_refs={"id":"TEST_ONLY"})
    monkeypatch.setattr(compiler,"read_parent_direct_owner_cash_sources",lambda **kw:dict(statements=[statement]))
    monkeypatch.setattr(compiler,"read_parent_direct_cash_research",lambda **kw:dict(observed=[observed]))
    flow=dict(parent_profit="80",operating_cash="100",investment_cash_received="0",
        maintenance_capex="20",growth_capex="0",commitments_outside_capex="0",debt_repayment="0",
        new_borrowing="0",interest_outside_cfo="0",other_mandatory_cash="0",cash_floor="20",
        payout_ratio="1",reserve_ratio="0")
    driver=dict(historical_start="2025-01-01",historical_end="2025-12-31",
        revenue=assumption("200"),cost=assumption("100"),other_operating_cash=assumption("0"),
        rationale="TEST_ONLY constant production",counter_evidence="TEST_ONLY deterioration",
        reopen_condition="TEST_ONLY latest filing")
    scenario=dict(rationale="TEST_ONLY",counter_evidence="TEST_ONLY",reopen_condition="TEST_ONLY",
        cost_of_equity=assumption("0.08"),
        years=[dict(year=2026,operating_forecast=driver,policy={k:assumption(v) for k,v in flow.items() if k!="operating_cash"})],
        terminal=dict(policy={k:assumption(v) for k,v in flow.items()},rationale="TEST_ONLY constant owner cash",
            counter_evidence="TEST_ONLY decline",reopen_condition="TEST_ONLY capital needs",
            remaining_scheduled_events=[],max_transition_years=100))
    source=dict(path="runtime/TEST_ONLY.pdf",sha256="b"*64,available_at="2026-04-01T00:00:00+00:00",period_end="2025-12-31")
    case=dict(industry="消费品",investment_path="quality_compounder",thesis="TEST_ONLY cash evidence",
        return_driver="TEST_ONLY distributions",mispricing_hypothesis="TEST_ONLY no market comparison",
        positives=[],counter_evidence=[],thesis_breakers=[],next_events=[])
    return dict(schema_version=compiler.SCHEMA,action="no_order",symbol="600519",issuer_name="贵州茅台",
        currency="CNY",scope=compiler.SCOPE,valuation_date="2025-12-31",
        owner_sources=[source],operating_sources=[dict(path="runtime/TEST_ONLY.json",sha256="c"*64)],
        fact_anchors=anchors,opening=dict(book=dict(classification="FACT",anchor="book_equity_cny"),
            cash=dict(classification="FACT",anchor="closing_cash_and_equivalents_cny"),
            capacity=assumption("0"),debt=assumption("0")),
        ordinary_shares=dict(classification="FACT",period_end="2025-12-31"),
        scenarios={k:deepcopy(scenario) for k in ("bear","base","bull")},
        profile_id="quality_compounder",model_applicable=True,model_applicability_evidence=["TEST_ONLY"],
        research_case=case,run_id="TEST_ONLY_direct_root",research_version="TEST_ONLY_direct_root",
        computed_at=NOW.isoformat(),research_as_of=NOW.date().isoformat(),
        source_descriptors=[dict(id="TEST_ONLY_SOURCE",kind="annual_report",
            location="https://www.cninfo.com.cn/TEST_ONLY.pdf",local_path=source["path"],sha256=source["sha256"],
            retrieved_at=source["available_at"],issuer_identity=dict(venue="CNINFO",security_code="600519",
                organization_id="gssh0600519",issuer_name="贵州茅台"))])
def test_compiler_recalculates_cfo_owner_distribution_and_shared_service(monkeypatch,tmp_path):
    spec=sample(monkeypatch)
    c=compiler.compile_source_bound_owner_cash(root=tmp_path,spec=spec,now=NOW)
    assert Decimal(c["scenarios"]["base"]["years"][0]["policy"]["operating_cash"])==100
    assert Decimal(c["scenarios"]["base"]["calculation"]["per_share_value"])==10
    outcome,descriptor=runner.run_direct_owner_cash_research(runner._package(spec,c),NOW,root=tmp_path)
    assert outcome.valuation.base_value==10
    assert outcome.decision_recommendation.action=="no_order"
    assert outcome.decision_recommendation.position_guidance is None
    assert descriptor.as_policy()["facts"]["scenario_inputs"]["base"]["years"][0]["policy"]["operating_cash"]=="100"


def test_compiler_rejects_uncovered_issued_financing_even_with_new_borrowing(monkeypatch,tmp_path):
    spec=sample(monkeypatch)
    source_reader=compiler.read_parent_direct_owner_cash_sources
    issue=dict(code="CP1",maturity="2026-12-30",principal_cny="100",
        actual_settlement_verified=False,outstanding_at_evaluation_cny=None,
        classification="FACT",scope="ISSUER_FINANCING_DISCLOSURE",currency="CNY")
    monkeypatch.setattr(compiler,"read_parent_direct_owner_cash_sources",lambda **kw:
        {**source_reader(**kw),"constraints":{"issued_financing":[issue]}})
    spec["scenarios"]["base"]["years"][0]["policy"]["new_borrowing"]=assumption("100")
    with pytest.raises(ValueError,match="DIRECT_INPUT_FINANCING_MATURITY_UNCOVERED"):
        compiler.compile_source_bound_owner_cash(root=tmp_path,spec=spec,now=NOW)
@pytest.mark.parametrize("fault",["unknown","wrong_opening_date","source_issuer","missing_policy","future_year","missing_anchor","unsupported_scope","skipped_year","money_as_shares","interim_basis"])
def test_exact_economic_and_source_boundaries(monkeypatch,tmp_path,fault):
    spec=sample(monkeypatch)
    if fault=="skipped_year":spec["scenarios"]["base"]["years"][0]["year"]=2030
    if fault=="money_as_shares":spec["ordinary_shares"]={"classification":"FACT","anchor":"profit"}
    if fault=="interim_basis":spec["valuation_date"]="2025-06-30"
    if fault=="unknown":spec["opening"]["debt"]={"classification":"UNKNOWN"}
    if fault=="wrong_opening_date":spec["valuation_date"]="2024-12-31"
    if fault=="source_issuer":spec["symbol"]="600887"
    if fault=="missing_policy":del spec["scenarios"]["base"]["years"][0]["policy"]["maintenance_capex"]
    if fault=="future_year":spec["scenarios"]["base"]["years"][0]["year"]=2025
    if fault=="missing_anchor":spec["scenarios"]["base"]["cost_of_equity"]["evidence_anchors"]=["absent"]
    if fault=="unsupported_scope":spec["scope"]="CONSOLIDATED"
    with pytest.raises((ValueError,KeyError)):
        compiler.compile_source_bound_owner_cash(root=tmp_path,spec=spec,now=NOW)
def test_input_mutation_recalculates_cash_without_cross_scenario_pollution(monkeypatch,tmp_path):
    spec=sample(monkeypatch)
    original=deepcopy(spec)
    first=compiler.compile_source_bound_owner_cash(root=tmp_path,spec=spec,now=NOW)
    spec["scenarios"]["bear"]["years"][0]["operating_forecast"]["other_operating_cash"]["value"]="-30"
    second=compiler.compile_source_bound_owner_cash(root=tmp_path,spec=spec,now=NOW)
    assert second["scenarios"]["base"]==first["scenarios"]["base"]
    assert Decimal(second["scenarios"]["bear"]["calculation"]["annual_rows"][0]["conditional_distribution_cny"])==50
    assert original["scenarios"]["bear"]["years"][0]["operating_forecast"]["other_operating_cash"]["value"]=="0"

def test_immutable_receipt_existing_public_reader_and_policy_consume_same_result(monkeypatch,tmp_path):
    import json
    from hashlib import sha256
    from value_investment_agent.application.product.first_research_input_view_v1 import read_first_research_input
    spec=sample(monkeypatch)
    runtime=tmp_path/"runtime";runtime.mkdir()
    (runtime/"TEST_ONLY.json").write_bytes(b"{}")
    spec["operating_sources"][0]["sha256"]=sha256(b"{}").hexdigest()
    spec["price_policy"]=dict(draft_id="TEST_ONLY",policy_id="TEST_ONLY",rule_version="TEST_ONLY",profile_id="quality_compounder",
        effective_from="2026-11-16",effective_through="2026-11-16",rationale="TEST_ONLY historical endpoint",
        dividend_coverage_risk="TEST_ONLY unapproved",rules=[dict(action="entry",scenario="bear",value_fraction="1",comparison="LTE",rationale="TEST_ONLY")])
    raw=json.dumps(spec,ensure_ascii=False).encode("utf-8")
    (runtime/"spec.json").write_bytes(raw)
    binding=dict(path="runtime/spec.json",sha256=sha256(raw).hexdigest())
    built=runner.build_direct_owner_cash_receipt(root=tmp_path,spec_binding=binding,
        output_dir=runtime/"output",now=NOW)
    config=tmp_path/"config";config.mkdir()
    (config/"current-first-research-inputs-v1.json").write_text(json.dumps(dict(
        schema_version="current-first-research-inputs-v1",action="no_order",
        cases={spec["symbol"]:{"receipt":built["receipt_binding"]}})),encoding="utf-8")
    before={p:p.read_bytes() for p in runtime.rglob("*") if p.is_file()}
    view=read_first_research_input(root=tmp_path,symbol=spec["symbol"],now=NOW)
    assert view["status"]=="SOURCE_BOUND_FIRST_INPUT_COMPILED",view
    assert view["valuation"]==built["result"]["valuation"]
    assert view["direct_owner_cash"]["annual_rows"]["base"]==built["result"]["compiled"]["scenarios"]["base"]["calculation"]["annual_rows"]
    assert view["direct_owner_cash"]["conditional_price"]["status"]=="HISTORICAL_CONDITIONAL_DRAFT"
    midnight=read_first_research_input(root=tmp_path,symbol=spec["symbol"],now=datetime(2026,11,16,16,30,tzinfo=timezone.utc))
    assert "EXPIRED" in midnight["direct_owner_cash"]["conditional_price"]["reason_codes"]
    assert midnight["direct_owner_cash"]["conditional_price"]["draft_prices"] is None
    assert view["personal_quantity"] is None and not view["formal_eligibility"]
    assert before=={p:p.read_bytes() for p in runtime.rglob("*") if p.is_file()}
    (runtime/"spec.json").write_bytes(raw+b" ")
    denied=read_first_research_input(root=tmp_path,symbol=spec["symbol"],now=NOW)
    assert denied["status"]=="UNASSESSABLE" and "HASH_CHANGED" in denied["reason"]


def test_public_direct_dispatch_rejects_private_manifest_before_replay(monkeypatch,tmp_path):
    import json
    from hashlib import sha256
    from value_investment_agent.application.product.first_research_input_view_v1 import read_first_research_input
    runtime=tmp_path/"runtime";runtime.mkdir()
    config=tmp_path/"config";config.mkdir()
    receipt=dict(schema_version=runner.RECEIPT_SCHEMA,symbol="600519",action="no_order",
        source_bindings=[dict(path="runtime/private/account.json",sha256="a"*64)],
        spec_binding=dict(path="runtime/spec.json",sha256="b"*64),
        result_binding=dict(path="runtime/result.json",sha256="c"*64))
    raw=json.dumps(receipt).encode();(runtime/"receipt.json").write_bytes(raw)
    (config/"current-first-research-inputs-v1.json").write_text(json.dumps(dict(
        schema_version="current-first-research-inputs-v1",action="no_order",
        cases={"600519":{"receipt":dict(path="runtime/receipt.json",sha256=sha256(raw).hexdigest())}})),encoding="utf-8")
    def forbidden(**kwargs):raise AssertionError("Private paths must be rejected before replay")
    monkeypatch.setattr("value_investment_agent.application.product.direct_owner_cash_view_v1.replay_direct_owner_cash_receipt",forbidden)
    view=read_first_research_input(root=tmp_path,symbol="600519",now=NOW)
    assert view["status"]=="UNASSESSABLE"
