"""Direct tests for the aggregate-capex adapter and frozen V2 calculation."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from test_direct_parent_owner_cash_v1 import inputs
from value_investment_agent.application.research import direct_owner_gross_capex_v1 as adapter
from value_investment_agent.application.research.agent_review import quarterly_parent_cash_source
from value_investment_agent.infrastructure.filings.quarterly_operating_facts_v1 import CASH_FIELDS

NOW = datetime(2027, 11, 10, tzinfo=timezone.utc)


@pytest.fixture
def case(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    original = runtime / "quarter.pdf"
    original.write_bytes(b"TEST_ONLY quarter PDF bytes")
    ref = dict(path="runtime/quarter.pdf", sha256=sha256(original.read_bytes()).hexdigest(),
               available_at="2027-10-30T00:00:00+00:00", physical_page=2,
               excerpt=CASH_FIELDS["cash_capex"] + " 18.00 14.00")
    rows = [
        f"{label} 18.00 14.00" for label in
        (*CASH_FIELDS.values(), "取得投资收益收到的现金")
    ]
    pages = [
        "证券代码：600887 测试股份有限公司2027年第三季度报告",
        "\n".join(["母公司现金流量表", "2027年1—9月", "编制单位：测试股份有限公司",
                  "单位：元 币种：人民币", "项目 2027年前三季度（1-9月） 2026年前三季度（1-9月）", *rows]),
    ]
    monkeypatch.setattr(adapter, "extract_pages", lambda path: pages)
    monkeypatch.setattr(quarterly_parent_cash_source, "extract_pages", lambda path: pages)

    old = inputs()
    old["years"][0]["scheduled_owner_distribution_cny"] = "10"
    old["years"][0]["policy"].update(maintenance_capex="12", growth_capex="8")
    aggregate = deepcopy(old)
    for row in [*aggregate["years"], aggregate["terminal"]]:
        row["policy"].pop("maintenance_capex")
        row["policy"].pop("growth_capex")
        row["policy"]["gross_capex_cny"] = "20"
        row["capex_trace"] = dict(
            classification="FORECAST_ASSUMPTION",
            condition="Continue the observed aggregate spending only under the modeled operating conditions.",
            investment_profit_link="Investment supports output; customer volumes govern the profit effect.",
            counter_evidence="Lower cash and profit with unchanged investment stress the payout.",
            reopen_condition="Reopen if the output or required investment differs from the scenario.",
            source_refs=[ref],
        )
    aggregate["terminal"]["capex_trace"]["stationary_reinvestment"] = (
        "Continued aggregate reinvestment supports unchanged capacity after finite projects end.")
    aggregate["countercase"] = dict(operating_cash_cny="90", parent_profit_cny="75")
    args = dict(root=tmp_path, scenario=aggregate, symbol="600887", issuer_name="测试股份有限公司",
                first_year_source=dict(path=ref["path"], sha256=ref["sha256"],
                    acquired_at=ref["available_at"],
                    url="https://static.cninfo.com.cn/finalpage/2027-10-30/123.PDF"),
                as_of=NOW)
    return args, old, original


def test_adapter_replays_v2_arithmetic_and_publishes_only_aggregate(case):
    args, split, _ = case
    receipt = adapter.compute_gross_capex_receipt(**args)
    expected = adapter.arithmetic.compile_direct_owner_cash_path_v2(**split)
    for row in expected["annual_rows"] + expected["terminal_rows"]:
        policy = row["cash_policy"]
        policy["gross_capex_cny"] = str(adapter.Decimal(policy.pop("maintenance_capex"))
                                       + adapter.Decimal(policy.pop("growth_capex")))
        row["capex_allocation"] = "UNALLOCATED"
    assert receipt["calculation"] == expected
    assert receipt["first_year_floor"]["gross_capex_cny"] == "18.00"
    assert receipt["countercase_result"]["steady_distribution_cny"] == "70"
    assert receipt["formal_eligibility"] is False and receipt["action"] == "no_order"
    serialized = json.dumps(receipt)
    assert "maintenance_capex" not in serialized and "growth_capex" not in serialized
    assert adapter.replay_gross_capex_receipt(root=args["root"], receipt=json.loads(serialized),
                                            now=NOW) == receipt
    receipt["calculation"]["per_share_value"] = "999"
    with pytest.raises(ValueError, match="REPLAY_MISMATCH"):
        adapter.replay_gross_capex_receipt(root=args["root"], receipt=receipt, now=NOW)


@pytest.mark.parametrize(("invalid", "reason"), [
    ("below_floor", "BELOW_FIRST_YEAR_REALIZED"),
    ("mixed", "EXCLUSIVE_TOTAL_REQUIRED"),
    ("missing_condition", "CONDITION_TRACE_REQUIRED"),
    ("wrong_page", "CONDITION_EXCERPT_INVALID"),
    ("future", "CONDITION_SOURCE_UNAVAILABLE"),
    ("not_adverse", "COUNTERCASE_NOT_ADVERSE"),
])
def test_adapter_refuses_unsupported_or_inconsistent_aggregate(case, invalid, reason):
    args, _, _ = case
    annual = args["scenario"]["years"][0]
    terminal = args["scenario"]["terminal"]
    if invalid == "below_floor":
        annual["policy"]["gross_capex_cny"] = "17.99"
    elif invalid == "mixed":
        annual["policy"]["maintenance_capex"] = "20"
    elif invalid == "missing_condition":
        del terminal["capex_trace"]["stationary_reinvestment"]
    elif invalid == "wrong_page":
        annual["capex_trace"]["source_refs"][0]["physical_page"] = 1
    elif invalid == "future":
        annual["capex_trace"]["source_refs"][0]["available_at"] = "2030-01-01T00:00:00+00:00"
    else:
        args["scenario"]["countercase"]["parent_profit_cny"] = "80"
    with pytest.raises(ValueError, match=reason):
        adapter.compute_gross_capex_receipt(**args)


def test_source_tamper_blocks_receipt_replay(case):
    args, _, original = case
    receipt = adapter.compute_gross_capex_receipt(**args)
    original.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SOURCE_HASH_CHANGED"):
        adapter.replay_gross_capex_receipt(root=args["root"], receipt=receipt, now=NOW)



def test_adverse_case_can_block_without_turning_base_into_approval(case):
    args, _, _ = case
    args["scenario"]["countercase"] = dict(operating_cash_cny="20", parent_profit_cny="75")
    receipt = adapter.compute_gross_capex_receipt(**args)
    assert receipt["countercase_result"] == {
        "status": "BLOCKED", "reason": "DIRECT_OWNER_NO_POSITIVE_SUPPORTED_TERMINAL_DISTRIBUTION"}
    assert receipt["formal_eligibility"] is False


def test_v3_dispatch_hides_private_slots_and_e2_checks_frozen_result(case, monkeypatch):
    from value_investment_agent.application.research.agent_review import parent_cash_task_v3 as service_module
    from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse
    from types import SimpleNamespace

    args, split, _ = case
    scenario = args["scenario"]
    root = args["root"]
    plan = dict(schema_version=adapter.WIRE_VERSION, source_fingerprint="pinned-context",
                years=[{key: row[key] for key in ("year", "capex_trace")} |
                       {"gross_capex_cny": row["policy"]["gross_capex_cny"]} for row in scenario["years"]],
                terminal=dict(gross_capex_cny="20", capex_trace=scenario["terminal"]["capex_trace"]),
                countercase=scenario["countercase"])
    path = root / "runtime" / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    pin = dict(path="runtime/plan.json", sha256=sha256(path.read_bytes()).hexdigest())
    spec = dict(gross_capex_plan_binding=pin, gross_capex_cutoff=NOW.isoformat(),
                source_fingerprint="pinned-context", spec_binding={},
                implemented_distribution_receipt_binding={"path": "paid"})
    service = service_module.ParentCashTaskServiceV3(root, test_provider=object())
    from dataclasses import dataclass

    @dataclass
    class Request:
        user: str
        output_schema: dict
        transport_output_contract: str

    context = dict(symbol="600887", annual_capex_floor=dict(
        year=2027, symbol="600887", scope="ISSUER_PARENT_STANDALONE", currency="CNY", minimum_cny="18"))
    schema = dict(required=["maintenance_capex", "growth_capex"],
                  properties={"maintenance_capex": {}, "growth_capex": {}})
    request = Request(json.dumps(dict(scenario="base", required_years=[2027], source_context=context)),
                      schema, "maintenance_capex + growth_capex")
    monkeypatch.setattr(service_module.ParentCashTaskServiceV3, "_legacy_wire",
                        staticmethod(lambda *a, **kw: request))
    wire = service._wire(spec, "policy", request, root=root)
    assert wire.output_schema["required"] == ["gross_capex_cny"]
    assert json.loads(wire.user)["gross_capex_contract"]["binding"] == pin
    term = dict(values=["20"])
    response = LLMResponse(json.dumps(dict(series={"gross_capex_cny": term})), 0, 0, "test")
    monkeypatch.setattr(service_module, "parse_staged_parent_cash_response",
                        lambda response, **kw: json.loads(response.text))
    parsed = service._parse_stage(dict(spec, implementation_sha256={}), "policy", response,
                                  request, "pinned-context")
    assert parsed["series"]["maintenance_capex"] == term
    wrong = LLMResponse(json.dumps(dict(series={"gross_capex_cny": dict(values=["21"])})), 0, 0, "test")
    with pytest.raises(ValueError, match="GROSS_CAPEX_LOCKED_TOTAL_CHANGED"):
        service._parse_stage(dict(spec, implementation_sha256={}), "policy", wrong, request, "pinned-context")
    flat = LLMResponse(json.dumps(dict(policy={"gross_capex_cny": {"value": "20"}})), 0, 0, "test")
    assert json.loads(adapter.private_legacy_response(flat, "terminal", plan,
        flat_terminal=True).text)["policy"]["maintenance_capex"]["value"] == "20"

    compiled_base = dict(split, calculation=adapter.arithmetic.compile_direct_owner_cash_path_v2(**split))
    raw = dict(compiled=dict(scenarios={"base": compiled_base}), source_fingerprint="pinned-context",
               scenario_draft_sha256={"base": "draft"},
               candidate_spec=dict(symbol=args["symbol"], issuer_name=args["issuer_name"],
                                   quarterly_financing_source=args["first_year_source"]))
    monkeypatch.setattr(service_module, "assemble_parent_cash_drafts_v2", lambda **kw: deepcopy(raw))
    result = service._assemble(spec, {}, NOW)
    assert result["gross_capex_plan_binding"] == pin
    receipt = result["aggregate_base_receipt"]
    assert receipt["scenario"]["years"][0]["policy"]["gross_capex_cny"] == "20"
    assert "maintenance_capex" not in json.dumps(result)
    assert adapter.replay_gross_capex_receipt(root=root, receipt=receipt, now=NOW) == receipt
    compiled_base["years"][0]["policy"]["growth_capex"] = "9"
    with pytest.raises(ValueError, match="GROSS_CAPEX_E2_TOTAL_CHANGED"):
        service._assemble(spec, {}, NOW)
