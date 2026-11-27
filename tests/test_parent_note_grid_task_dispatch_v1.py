"""Real source / test transport integration for the versioned native V3 path."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil

import pytest

from value_investment_agent.application.research import parent_note_grid_task_inputs_v1 as inputs
from value_investment_agent.application.research import parent_note_grid_task_service_v1 as service
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse
from value_investment_agent.application.research import parent_note_grid_case_v1 as case_adapter
from value_investment_agent.application.research import parent_note_grid_task_receipt_v1 as receipt


def write(root, name, payload):
    path = root / "runtime" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    path.write_bytes(raw)
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256(raw).hexdigest())


def explained(value):
    return dict(classification="FORECAST_ASSUMPTION", value=value, evidence_anchors=["profit"],
                rationale="Explicit test-only assumption", counter_evidence="Actual amounts may differ",
                reopen_condition="Reopen on audited parent evidence")


class FixtureProvider:
    def __init__(self):
        self.calls = []

    def complete(self, request):
        packet = json.loads(request.user)
        stage, scenario = packet["stage"], packet["scenario"]
        self.calls.append((scenario, stage))
        fields = packet["required_fields"]
        values = dict(revenue="25000000000", cost="10000000000", other_operating_cash="-8000000000",
                      operating_cash="1000000000", parent_profit="2000000000", payout_ratio="0.3",
                      reserve_ratio="0.1", cash_floor="1000000", maintenance_capex="200000000",
                      growth_capex="50000000", commitments_outside_capex="0", new_borrowing="0",
                      debt_repayment="0", investment_cash_received="0", interest_outside_cfo="1000",
                      other_mandatory_cash="1000000")
        def term(amount, n):
            return dict(values=[amount]*n, evidence_anchors=["profit"],
                        mechanism="Explicit test-only mechanism", counter_evidence="A cash shortfall is possible",
                        reopen_condition="Reopen on audited parent evidence")
        explanations = dict(rationale="Independent fixture operating policy", counter_evidence="A cash shortfall is possible",
                            reopen_condition="Reopen on audited parent evidence")
        if stage == "terminal":
            body = dict(terminal=dict(policy={k:term(values[k],1) for k in fields},
                        remaining_scheduled_events=[], max_transition_years=10, financing=None, **explanations),
                        cost_of_equity=term("0.1",1))
        else:
            body = dict(years=packet["required_years"], series={k:term(values[k],10) for k in fields})
            if stage == "operating":
                body.update(annual_notes=["Ten-year test input under explicit assumptions"]*10, **explanations)
                if "scenario_review" in request.output_schema["required"]:
                    body["scenario_review"] = [body.pop(k) for k in service.native.operating_wire.REVIEW_FIELDS]
            else:
                body["series"]["other_mandatory_cash"]["cash_class_by_year"] = ["NON_FINANCING"] * 10
                body["series"]["debt_repayment"]["values"][0] = "1000000"
        return LLMResponse(json.dumps(body), 100,100, "deepseek-flash")


@pytest.fixture
def retained(tmp_path, monkeypatch):
    value = os.environ.get("FENJIU_SOURCE_ROOT")
    if not value:
        pytest.skip("Set FENJIU_SOURCE_ROOT to run the retained FY/H1 task replay")
    base = "runtime/600809-public-report-sources-20261127"
    root = Path(value)
    for period in ("2025-12-31", "2026-06-30"):
        shutil.copytree(root/base/period, tmp_path/base/period)
    name = base+"/parent-note-grid-source-manifest-v1.json"
    shutil.copyfile(root/name, tmp_path/name)
    template = base + "/v3-case-template-fenjiu-historical-v1.json"
    shutil.copyfile(root/template, tmp_path/template)
    assert sha256((tmp_path/template).read_bytes()).hexdigest() == "65d2b822b655169a521c957b709b3974d6fabd590730d5fbb0ddeaa75889e16f"
    econ = Path("runtime/600809-historical-fyh1-research-v1")
    donor = root if (root/econ/"fresh-distribution-v1.json").is_file() else Path(__file__).resolve().parents[1]
    for folder in ("dividend-index-20260727", "2026-06-30-legal-name"):
        shutil.copytree(donor/econ/folder, tmp_path/econ/folder)
    fact = econ/"fresh-distribution-v1.json"
    shutil.copyfile(donor/fact,tmp_path/fact)
    paid = dict(path=fact.as_posix(), sha256=sha256((tmp_path/fact).read_bytes()).hexdigest())
    config = "config/company-profile-sources-v2/600809.json"
    (tmp_path/config).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root/config, tmp_path/config)
    raw = (tmp_path/name).read_bytes()
    m = json.loads(raw)
    now = datetime.now(timezone.utc)
    def anchor(section, field):
        return dict(period_end="2025-12-31", section=section, field=field, column="current")
    spec = dict(schema_version=inputs.agent.SCHEMA, source_manifest_binding=dict(path=name,sha256=sha256(raw).hexdigest()),
        symbol=m["symbol"], issuer_name=m["issuer_name"], valuation_date="2025-12-31", computed_at=now.isoformat(),
        source_adapter_version=inputs.VERSION, owner_sources=m["owner_sources"], operating_sources=[], action="no_order",
        scope=inputs.agent.SCOPE, currency="CNY", model_applicable=True, implemented_distribution_receipt_binding=paid,
        model_applicability_evidence=dict(profile_input_sha256=inputs.load_registered_source_profile(
            root=tmp_path, symbol=m["symbol"], now=now)["input_fingerprint"], model_version=inputs.MODEL_VERSION,
            purpose="CONDITIONAL_PARENT_RESEARCH", economic_adoption=False),
        fact_anchors=dict(book=anchor("balance_sheet","book_equity_cny"), cash=anchor("cash_flow","closing_cash_and_equivalents_cny"),
                          revenue=anchor("operating","revenue"), cost=anchor("operating","cost"), profit=anchor("income","parent_net_profit_cny")),
        opening=dict(book=dict(classification="FACT",anchor="book"), cash=dict(classification="FACT",anchor="cash"),
                     debt=explained("1000000"), capacity=explained("15000000000")),
        ordinary_shares=dict(classification="DERIVED_FACT",period_end="2025-12-31"), scenarios={})
    cfg=dict(model_id="deepseek-flash", max_completion_tokens_cap=4096, input_cost_per_million="1",
             output_cost_per_million="1", max_run_cost="9", daily_cost_limit="10", currency="CNY")
    monkeypatch.setattr(service.native,"model_configuration",lambda root:cfg.copy())
    return tmp_path, spec, now


def test_create_execute_reopen_compile_with_real_sources(retained):
    root, spec, now = retained
    pin = write(root,"test-note-grid.json",spec)
    registry = root/"config/parent-cash-task-case-bindings-v1.json"
    template = "runtime/600809-public-report-sources-20261127/v3-case-template-fenjiu-historical-v1.json"
    case = dict(path=template,sha256=sha256((root/template).read_bytes()).hexdigest())
    entry = dict(symbol=spec["symbol"],spec_binding=pin,case_package_binding=case,
                 implemented_distribution_receipt_binding=spec["implemented_distribution_receipt_binding"])
    registry.write_text(json.dumps(dict(schema_version="parent-cash-task-case-bindings-v1",
        specs={pin["sha256"]:entry},active_spec_by_symbol={spec["symbol"]:pin["sha256"]})),encoding="utf-8")
    provider = FixtureProvider()
    worker = service.ParentCashService(root,test_provider=provider)
    created = worker.create(spec_binding=pin, request_key="isolated-grid-probe", now=now)
    assert created["status"] == "QUEUED"
    task_id = created["task_id"]
    assert worker.create(spec_binding=pin,request_key="isolated-grid-probe")["task_id"] == task_id
    assert provider.calls == []
    result = worker.run(task_id)
    assert (result["status"], result.get("error_code")) == ("SUCCEEDED", None), (result.get("error_code"), provider.calls)
    assert provider.calls == [tuple(s.split(".")) for s in service.STAGE_ORDER]
    reopened = service.ParentCashService(root,test_provider=FixtureProvider()).read(task_id)
    assert reopened["candidate"] == result["candidate"]
    assert reopened["candidate"]["compiled"]["compiler_version"] == "direct-owner-cash-compilation-note-grid-v1"
    assert reopened["provider_requests"] == 9 and len(reopened["responses"]) == 9
    assert all(row["status"] == "SETTLED" for row in reopened["reservations"].values())
    candidate = reopened["candidate"]
    assert reopened["adoptable_valuation"] is False
    event = candidate["compiled"]["evidence"]["implemented_distribution"]
    assert event["settlement_status"] == "ROUTE_ACTUALS_UNVERIFIED"
    assert event["distribution"]["entitled_shares"] == 1219964222
    for row in candidate["compiled"]["scenarios"].values():
        assert [y["scheduled_owner_distribution_cny"] for y in row["years"]] == ["8002965296.32"] + ["0"] * 9
    completed = datetime.now(timezone.utc)
    package = case_adapter.package_candidate(root,candidate,case,task_id,dict(sha256="f"*64),completed,
        dict(spec_binding=pin,case_package_binding=case,source_adapter_version=inputs.VERSION),receipt.SCHEMA)
    outcome, descriptor = case_adapter.run_registered_research(root,package,completed)
    assert outcome.valuation.status == "conditional_research_only"
    assert json.loads(outcome.valuation.to_json())["assumptions"]["scenario_calculations"] == {
        name:row["calculation"] for name,row in candidate["compiled"]["scenarios"].items()}
    wrong = deepcopy(package)
    wrong["sources"][0]["issuer_identity"]["organization_id"] = "unrelated"
    with pytest.raises(ValueError,match="VALUATION_SOURCE_CLOSURE_MISMATCH"):
        case_adapter.run_registered_research(root,wrong,completed)
    with worker._lock(worker._directory(task_id)):
        _, _, head = worker._load(task_id)
    with pytest.raises(ValueError,match="EXACT_LIVE_SUCCESS"):
        receipt.execute(root=root,task_id=task_id,task_head=head,case_package_binding=case,
                        distribution_binding=entry["implemented_distribution_receipt_binding"],now=completed)
    with (root/spec["owner_sources"][1]["receipt_binding"]["path"]).open("ab") as f:
        f.write(b" ")
    assert worker.read(task_id)["error_code"] == "PARENT_SOURCE_OR_CHECKPOINT_INVALID"
    assert len(provider.calls) == 9


@pytest.mark.parametrize("change,reason", [
    ({"model_applicable":False}, "SOURCE_CONTRACT"),
    ({"model_applicability_evidence":["asserted in prose"]}, "SOURCE_BOUND_APPLICABILITY"),
    ({"model_applicability_evidence":dict(profile_input_sha256="0"*64, model_version=inputs.MODEL_VERSION,
       purpose="CONDITIONAL_PARENT_RESEARCH", economic_adoption=False)}, "MODEL_OR_PROFILE_MISMATCH"),
    ({"computed_at":"2026-01-01T00:00:00+00:00"}, "SOURCE_CLOCK"),
    ({"computed_at":"2099-01-01T00:00:00+00:00"}, "SOURCE_CLOCK"),
    ({"implemented_distribution_receipt_binding": None}, "DISTRIBUTION_RECEIPT_REQUIRED"),
    ({"quarterly_financing_source":{}}, "UNSUPPORTED_SOURCE"),
    ({"issuer_name":"Other issuer"}, "MANIFEST_MISMATCH"),
    ({"valuation_date":"2026-09-30"}, "FY_H1_REQUIRED"),
])
def test_reject_changed_source_before_task_or_transport(retained,change,reason):
    root, spec, now = retained
    pin=write(root,"negative.json",dict(spec,**change))
    provider=FixtureProvider()
    worker=service.ParentCashService(root,test_provider=provider)
    with pytest.raises(ValueError,match=reason):
        worker.create(spec_binding=pin,request_key="negative-grid-probe",now=now)
    assert provider.calls == [] and not list(worker.base.glob("*/input.json"))
