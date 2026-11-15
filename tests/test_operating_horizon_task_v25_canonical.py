"""TEST_ONLY V25 native transport.  It never invokes a paid model."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from test_operating_horizon_task_v19_generic import setup as v19_setup
from test_operating_horizon_draft_v1 import context as base_context  # noqa: F401
from test_operating_horizon_split_v8 import _annual, _cash
from value_investment_agent.application.research.agent_review import operating_horizon_task_v25_canonical as task
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse

NOW = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)


def native_row(scenario):
    path = json.loads(_annual())["years"]["2027"]["operating_paths"][scenario]
    names = {"volume_change": "revenue_activity_volume",
             "realization_mix_change": "realization_mix_change",
             "unit_cost_change": "unit_cost_change", "fixed_cogs_share": "fixed_cogs_share",
             "opex_change": "opex_change", "surcharge_ratio": "surcharge_ratio",
             "other_pretax_cny": "other_pretax_cny"}
    drivers = [dict(driver_id=names[name], value=dict(type="range", lower=float(row["lower"]),
        upper=float(row["upper"]), unit="CNY" if name == "other_pretax_cny" else "ratio"),
        baseline_anchor_ids=row["evidence_ids"], rationale=row["rationale"])
        for name, row in path["drivers"].items()]
    capital_ids = {"investment": "capital_investment", "funding_access": "funding_access",
                   "terminal": "terminal"}
    capital = [dict(assumption_id=capital_ids[row["dimension"]],
        value=dict(type="unknown" if row["classification"] == "UNKNOWN" else "range",
                   lower=row["lower"], upper=row["upper"], unit=row["unit"]),
        baseline_anchor_ids=row["evidence_ids"], rationale=row["rationale"])
        for row in path["capital_assumptions"]]
    case = path["unit_cost_case"]
    return dict(scenario=scenario, drivers=drivers, capital_assumptions=capital,
        unit_cost_mechanism="INPUT_PRICE",
        unit_cost_case=dict(conditional_mechanism=case["mechanism"],
                            mechanism_source_ids=case["source_anchor_ids"],
                            contrary_evidence_ids=case["contrary_evidence_ids"]),
        counter_evidence=["historical cost ratio is contrary evidence"],
        reopen_condition=case["reopen_condition"])


@pytest.fixture
def setup(v19_setup, monkeypatch):
    old, source, calls = v19_setup
    monkeypatch.setattr(task, "_now", lambda value=None: value or NOW)
    service = task.OperatingHorizonTaskService(old.root, source_loader=old.source_loader,
        source_loader_version=old.source_loader_version, test_provider=old.test_provider)
    def complete(request):
        calls.append(request)
        if len(calls) <= 3:
            scenario = task.SCENARIOS[len(calls) - 1]
            return LLMResponse(json.dumps(native_row(scenario)), 100, 50, "TEST_ONLY")
        return LLMResponse(_cash(unknown=True), 100, 50, "TEST_ONLY")
    service.test_provider.complete = complete
    return service, source, calls


def test_native_three_scenarios_are_normalized_then_wait_for_cash_evidence(setup):
    service, _, calls = setup
    created = service.create(symbol="600887", request_key="TEST_V25_NATIVE", years=[2027], now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "WAITING_EVIDENCE", result
    assert result["provider_requests"] == len(calls) == 4
    assert result["stage_validated"] == ["bear", "base", "bull", "cash"]
    assert result["annual_result"]["action"] == "no_order"
    assert result["formal_eligibility"] is False


def test_native_invalid_driver_is_sealed_before_next_call(setup):
    service, _, calls = setup
    def invalid(request):
        calls.append(request)
        value = native_row("bear")
        value["drivers"][0]["driver_id"] = "invented"
        return LLMResponse(json.dumps(value), 100, 50, "TEST_ONLY")
    service.test_provider.complete = invalid
    created = service.create(symbol="600887", request_key="TEST_V25_INVALID", years=[2027], now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["provider_requests"] == len(calls) == 1
    assert result["stage_validated"] == []


def test_v25_cannot_read_v21_failed_task(setup):
    service, _, calls = setup
    created = service.create(symbol="600887", request_key="TEST_V25_CANCEL", years=[2027], now=NOW)
    assert service.cancel(created["task_id"], now=NOW)["status"] == "CANCELLED"
    assert calls == []


def test_v25_uses_full_local_schema_for_json_object_transport(setup):
    service, source, _ = setup
    created = service.create(symbol="600887", request_key="TEST_V25_SCHEMA", years=[2027], now=NOW)
    spec, state, _ = service._load(created["task_id"])
    request, _ = service._request_for_stage(spec, state, service._context(spec), "bear")
    assert request.transport_output_contract is None
    assert request.output_schema["required"] == [
        "scenario", "drivers", "capital_assumptions", "unit_cost_mechanism",
        "unit_cost_case", "counter_evidence", "reopen_condition",
    ]







@pytest.mark.parametrize("valid_source", [True, False])
def test_v25_return_plan_applies_reported_fact_provenance(tmp_path, monkeypatch, valid_source):
    from value_investment_agent.application.research import (
        operating_horizon_cash_policy_e2_v11 as shared,
        operating_horizon_cash_policy_e2_v17 as e2,
    )

    digest = "a" * 64
    original = {"evidence": [{
        "id": "filing-row", "kind": "SOURCE_BOUND_REPORTED_STATEMENT_ROW",
        "pdf_sha256": digest, "source_id": "official:" + digest,
        "physical_page": 83 if valid_source else 0, "unit": "CNY",
        "available_at": "2026-04-25T08:00:00+08:00", "period": "2025-12-31",
    }]}
    spec = {
        "source_loader_binding": {"version": e2.RETURN_PLAN_LOADER},
        "context_sha256": "b" * 64,
    }
    service = object.__new__(task.OperatingHorizonTaskService)
    service.root = tmp_path
    monkeypatch.setattr(service, "_load", lambda _: (spec, {}, {}))
    monkeypatch.setattr(service, "_context", lambda _: original)

    def consume(**kwargs):
        projected = kwargs["service"]._context(spec)
        assert projected["evidence"][0]["kind"] == "VERIFIED_REPORTED_FACT"
        return {"input_manifest": {}}

    monkeypatch.setattr(shared, "_read_bound_cash_policy_e2_input", consume)
    if not valid_source:
        with pytest.raises(ValueError, match="V25_E2_REPORTED_FACT_PROVENANCE_INVALID"):
            e2.read_v25_cash_policy_e2_input(root=tmp_path, task_id="test", now=NOW, service=service)
        return
    result = e2.read_v25_cash_policy_e2_input(root=tmp_path, task_id="test", now=NOW, service=service)
    assert result["input_manifest"]["source_kind_projection"]["evidence_ids"] == ["filing-row"]
    assert original["evidence"][0]["kind"] == "SOURCE_BOUND_REPORTED_STATEMENT_ROW"


@pytest.mark.parametrize(("term", "citations", "accepted"), [
    ("reserve_ratio", ["charter"], True),
    ("accessible_profit_ratio", ["charter"], False),
    ("accessible_profit_ratio", ["charter", "parent-cfo"], True),
    ("commitment_cash_cny", ["financing"], False),
    ("commitment_cash_cny", ["fund-bound"], False),
    ("commitment_cash_cny", ["fund-bound", "capex-contract"], True),
    ("commitment_cash_cny", ["financing", "capex-contract"], True),
    ("commitment_cash_cny", ["financing", "parent-cfo"], False),
    ("commitment_cash_cny", ["historical-capex"], False),
    ("operating_wc_cash_cny", ["parent-cfo"], False),
    ("operating_wc_cash_cny", ["borrowing"], False),
    ("operating_wc_cash_cny", ["receivable-balance"], False),
    ("operating_wc_cash_cny", ["group-wc"], False),
    ("operating_wc_cash_cny", ["ambiguous-wc"], False),
    ("operating_wc_cash_cny", ["parent-cfo", "working-capital"], True),
])
def test_v25_cash_constraints_require_applicable_primary_anchor(monkeypatch, term, citations, accepted):
    from value_investment_agent.application.research import operating_horizon_cash_policy_e2_v17 as e2
    from value_investment_agent.application.research.agent_review import (
        operating_cash_policy_draft_v16_generic as cash,
    )

    evidence = [
        {"id": "charter", "scope": "ISSUER_ARTICLES_RULE_TEXT"},
        {"id": "financing", "scope": "ISSUER_FINANCING_DISCLOSURE"},
        {"id": "fund-bound", "scope": "ISSUER_PARENT_UNDATED_COMMITMENT_BOUND"},
        {"id": "parent-cfo", "scope": "parent", "field": "parent_cfo"},
        {"id": "historical-capex", "scope": "parent", "field": "gross_capex_cny"},
        {"id": "working-capital", "scope": "parent", "field": "working_capital_cash_component"},
        {"id": "borrowing", "scope": "parent", "field": "borrowings_received_cny",
         "text": "为补充营运资金取得借款收到的现金"},
        {"id": "receivable-balance", "scope": "parent", "field": "accounts_receivable",
         "text": "经营性应收期末余额"},
        {"id": "group-wc", "scope": "consolidated", "field": "working_capital_cash_component"},
        {"id": "ambiguous-wc", "field": "working_capital_cash_component"},
        {"id": "capex-contract", "scope": "parent"},
    ]
    context = {"evidence": evidence, "source_binding": {}}
    monkeypatch.setattr(cash, "candidates", lambda *_: {
        "reserve_ratio": ["charter"],
        "accessible_profit_ratio": ["charter", "parent-cfo"],
        "commitment_cash_cny": ["financing", "fund-bound", "capex-contract", "historical-capex"],
        "operating_wc_cash_cny": [
            "parent-cfo", "working-capital", "group-wc", "ambiguous-wc", "borrowing", "receivable-balance",
        ],
    })
    from value_investment_agent.application.research.agent_review.operating_cash_evidence_coverage import (
        describe_cash_evidence,
    )

    coverage = describe_cash_evidence(context)
    assert coverage["e2_applicable_anchor_ids"]["operating_wc_cash_cny"] == ["working-capital"]
    assert coverage["e2_applicable_anchor_ids"]["commitment_cash_cny"] == ["capex-contract"]
    policy = {"2027": {"base": {"terms": {term: {"evidence_ids": citations}}}}}
    if accepted:
        e2._validate_cash_constraint_citations(policy, context)
    else:
        with pytest.raises(ValueError, match="V25_E2_CASH_TERM_REQUIRES_APPLICABLE_ANCHOR:" + term):
            e2._validate_cash_constraint_citations(policy, context)

@pytest.mark.parametrize("unknown", [True, False])
def test_compact_cash_stage_settles_and_replays(setup, unknown):
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v25_compact_cash import (
        CompactCashTaskService,
    )

    old, source, calls = setup
    from value_investment_agent.application.research.agent_review import operating_cash_policy_draft_v16_generic as draft

    source["evidence"].append(dict(source["evidence"][0], id="test:cash-fields",
        field="historical_cash_policy",
        text="TEST_ONLY dividend parent CFO capex working capital commitment"))
    payload = json.loads(_cash(unknown=unknown))
    anchors = draft.candidates(source, source["source_binding"])
    for path in payload["years"]["2027"]["shareholder_cash_paths"].values():
        for name, term in path.items():
            if name in anchors and term["classification"] != "UNKNOWN":
                term["evidence_ids"] = anchors[name][:1]

    service = CompactCashTaskService(old.root, source_loader=old.source_loader,
        source_loader_version=old.source_loader_version, test_provider=old.test_provider)
    annual_provider = service.test_provider.complete

    def complete(request):
        if len(calls) < 3:
            return annual_provider(request)
        calls.append(request)
        return LLMResponse(json.dumps(payload), 100, 50, "TEST_ONLY")

    service.test_provider.complete = complete
    created = service.create(symbol="600887", request_key="TEST_V25_COMPACT", years=[2027], now=NOW)
    task_id = created["task_id"]
    result = service.run(task_id, now=NOW)
    if result["status"] == "FAILED":
        spec, state, _ = service._load(task_id)
        service._result(spec, state, service._context(spec))
    assert result["status"] == ("WAITING_EVIDENCE" if unknown else "SUCCEEDED"), result
    assert result["stage_validated"] == ["bear", "base", "bull", "cash"]
    assert len(calls) == 4
    assert "VALIDATED_ANNUAL_CALCULATIONS=" in calls[-1].user
    assert service.read(task_id)["research_result"] == result["research_result"]
    assert len(calls) == 4
    with pytest.raises(ValueError, match="V25_IMPLEMENTATION_OR_LOADER_CHANGED"):
        old.read(task_id)


@pytest.mark.parametrize("extra", [1, 2])
def test_sealed_bull_citation_transcription_is_bounded_and_read_only(setup, extra):
    from value_investment_agent.application.research.agent_review.operating_horizon_v25_citation_transcription import (
        replay_annual_citation_transcription,
    )

    service, source, calls = setup
    evidence = next(row for row in source["evidence"]
                    if row.get("field") == "cost" and row.get("period") == "2025-06-30")
    previous = evidence["id"]
    correct = "operating-statement:" + "b" * 64
    evidence["id"] = correct
    malformed = "operating-statement:" + "a" * extra + "b" * 64

    def response(request):
        name = task.SCENARIOS[len(calls)]
        calls.append(request)
        value = json.loads(json.dumps(native_row(name)).replace(json.dumps(previous), json.dumps(correct)))
        if name == "bull":
            driver = next(row for row in value["drivers"] if row["driver_id"] == "unit_cost_change")
            anchors = [item for item in driver["baseline_anchor_ids"] if item != correct]
            driver["baseline_anchor_ids"] = [*anchors, malformed]
        return LLMResponse(json.dumps(value), 100, 50, "TEST_ONLY")

    service.test_provider.complete = response
    task_id = service.create(symbol="600887", request_key="TEST_V25_TRANSCRIPTION", years=[2027], now=NOW)["task_id"]
    failed = service.run(task_id, now=NOW)
    assert failed["error_code"] == "V25_BULL_RESPONSE_REJECTED"
    before = {p: p.read_bytes() for p in service._directory(task_id).rglob("*.json")}
    if extra == 1:
        receipt = replay_annual_citation_transcription(service, task_id)
        assert receipt["replayed_citation"] == correct
        assert receipt["original_citation"] == malformed
        assert receipt["formal_eligibility"] is False and receipt["action"] == "no_order"
        assert len(receipt["next_cash_request_sha256"]) == 64
    else:
        with pytest.raises(ValueError, match="V25_TRANSCRIPTION_REQUIRES_ONE_EXTRA_HEX_CHARACTER"):
            replay_annual_citation_transcription(service, task_id)
    assert before == {p: p.read_bytes() for p in service._directory(task_id).rglob("*.json")}
    assert len(calls) == 3
    if extra == 1:
        from value_investment_agent.application.research.agent_review.operating_cash_continuation import (
            run_term_guided_cash_continuation, run_transcribed_cash_continuation,
        )

        def cash_response(request):
            calls.append(request)
            return LLMResponse(_cash(unknown=True), 100, 50, "TEST_ONLY")

        service.test_provider.complete = cash_response
        followup = run_transcribed_cash_continuation(service, task_id)
        assert followup["action"] == "no_order" and followup["formal_eligibility"] is False
        assert followup["economic_review"]["cash_policy_appendix_status"] != "COMPLETE_UNAPPROVED"
        assert all(path.read_bytes() == data for path, data in before.items())
        with pytest.raises(ValueError, match="CASH_CONTINUATION_ALREADY_ATTEMPTED"):
            run_transcribed_cash_continuation(service, task_id)
        assert len(calls) == 4
        revised = run_term_guided_cash_continuation(service, task_id)
        assert revised["action"] == "no_order" and revised["formal_eligibility"] is False
        assert "TERM_EVIDENCE_GUIDE=" in calls[-1].user and calls[-1].user != calls[-2].user
        with pytest.raises(ValueError, match="CASH_CONTINUATION_ALREADY_ATTEMPTED"):
            run_term_guided_cash_continuation(service, task_id)
        assert len(calls) == 5
        assert all(path.read_bytes() == data for path, data in before.items())


def test_cash_guide_pairs_exact_report_hash_and_period_across_source_aliases(setup):
    from value_investment_agent.application.research.agent_review.operating_cash_term_evidence import (
        build_cash_term_evidence,
    )

    _, context, _ = setup
    consolidated = next(row for row in context["evidence"] if
                        row.get("field") == "parent_profit" and row["period"] == "2025-12-31")
    standalone = dict(consolidated, id="TEST_ONLY:standalone-profit", field="parent_net_profit",
                      scope="parent", source_id="TEST_ONLY:report-alias", value="25")
    context["evidence"].append(standalone)
    guide = build_cash_term_evidence(context, context["source_binding"])
    comparisons = guide["accessible_profit_ratio"]["historical_comparisons"]
    assert any(row["evidence_ids"] == [standalone["id"], consolidated["id"]] for row in comparisons)
    assert all(row["scope"] == "HISTORICAL_PROFIT_COMPARISON_NOT_CASH_CONVERSION"
               for row in comparisons)
    standalone["pdf_sha256"] = ("b" if consolidated["pdf_sha256"][0] != "b" else "c") * 64
    guide = build_cash_term_evidence(context, context["source_binding"])
    assert not guide["accessible_profit_ratio"]["historical_comparisons"]


def test_cash_diagnostic_transcription_only_removes_single_extra_closing_brace():
    from value_investment_agent.application.research.agent_review.cash_json_transcription import (
        remove_single_extra_object_close,
    )

    assert remove_single_extra_object_close(' {"years":{"2027":{}}}} ') == '{"years":{"2027":{}}}'
    for text in ('{"years":{}}', '{"years":{}}}}', '{"years":{}}{"other":1}', '[1]}', '{"years":'):
        with pytest.raises(ValueError):
            remove_single_extra_object_close(text)



def test_v25_charter_source_is_bound_and_replays_independently_of_current_registry(tmp_path, monkeypatch):
    from hashlib import sha256

    from value_investment_agent.application.research.agent_review import (
        operating_horizon_charter_sources_v1 as charter,
    )

    corpus = {"issuer_name": "样本股份有限公司", "evidence": [{"id": "existing-fact"}],
              "source_binding": {"path": "runtime/base.json", "sha256": "a" * 64}}
    monkeypatch.setattr(charter.base, "build_operating_horizon_source_context", lambda **_: corpus)
    monkeypatch.setattr(charter.charter, "extract_pages", lambda _: [
        "样本股份有限公司章程",
        "公司分配当年税后利润时，应当提取利润的10%列入公司法定公积金。"
        "公司法定公积金累计额为公司注册资本的50%以上的，可以不再提取。",
    ])

    pdf = tmp_path / "runtime" / "charter.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"TEST_ONLY charter layout")
    selection = {"path": "runtime/charter.pdf", "sha256": sha256(pdf.read_bytes()).hexdigest(),
                 "url": "https://static.cninfo.com.cn/finalpage/2026-07-01/12345.PDF",
                 "available_at": "2026-07-02T09:00:00+08:00"}
    config = tmp_path / charter.CONFIG
    config.parent.mkdir()
    config.write_text(json.dumps({"000568": selection}), encoding="utf-8")
    request = dict(root=tmp_path, symbol="000568", now=NOW)

    first = charter.build_operating_horizon_source_context(**request)
    row, prior = first["evidence"]
    assert row["id"] == "cninfo:12345:statutory_reserve_rule" and row["physical_page"] == 2
    assert row["scope"] == "ISSUER_ARTICLES_RULE_TEXT" and row["unit"] == "TEXT"
    assert row["pdf_sha256"] == selection["sha256"] and "value" not in row
    assert corpus["evidence"] == [prior]

    config.write_text(json.dumps({"000568": {**selection, "available_at": "2027-01-01T00:00:00Z"}}),
                      encoding="utf-8")
    with pytest.raises(ValueError, match="CHARTER_SOURCE_URL_OR_AVAILABILITY_INVALID"):
        charter.build_operating_horizon_source_context(**request)
    assert charter.build_operating_horizon_source_context(**request, binding=first["source_binding"]) == first

    pdf.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="RESERVE_CHARTER_HASH_CHANGED"):
        charter.build_operating_horizon_source_context(**request, binding=first["source_binding"])



@pytest.mark.parametrize("compact", [False, True])
def test_v25_charter_floor_is_not_payout_anchor_in_either_transport(monkeypatch, tmp_path, compact):
    from types import SimpleNamespace

    from value_investment_agent.application.research import operating_horizon_cash_policy_e2_v17 as e2
    from value_investment_agent.application.research.agent_review import (
        operating_cash_policy_draft_v16_generic as cash,
    )

    binding = {"version": e2.CHARTER_DISTRIBUTION_LOADER}
    if compact:
        binding["cash_transport"] = "compact"
    context = {
        "source_binding": binding,
        "evidence": [
            {"id": "floor", "scope": "ISSUER_ARTICLES_DISTRIBUTABLE_PROFIT_FLOOR"},
            {"id": "policy", "scope": "ISSUER_RETURN_PLAN"},
        ],
    }
    service = SimpleNamespace(
        _load=lambda _: ({"source_loader_binding": binding}, None, None),
        _context=lambda _: context,
    )
    term = {"evidence_ids": ["floor"]}
    result = {"policy_years": {"2027": {"base": {"terms": {"target_payout_ratio": term}}}}}
    monkeypatch.setattr(e2, "read_generic_cash_policy_e2_input", lambda **_: result)
    monkeypatch.setattr(cash, "candidates", lambda *_: {"target_payout_ratio": ["floor", "policy"]})
    with pytest.raises(ValueError, match="V25_E2_CASH_TERM_REQUIRES_APPLICABLE_ANCHOR:target_payout_ratio"):
        e2.read_v25_cash_policy_e2_input(root=tmp_path, task_id="test", now=NOW, service=service)
    term["evidence_ids"].append("policy")
    assert e2.read_v25_cash_policy_e2_input(root=tmp_path, task_id="test", now=NOW, service=service) is result

def test_parent_wc_loader_keeps_e2_eligible_anchor_in_bounded_cash_request(setup, monkeypatch):
    from value_investment_agent.application.research.agent_review import (
        operating_cash_policy_draft_v16_generic as draft,
        operating_horizon_sources_parent_wc as loader,
    )
    from value_investment_agent.application.research.operating_horizon_cash_policy_e2_v17 import (
        cash_constraint_anchor_ids,
    )

    service, context, _ = setup
    context["snapshot_fingerprint"] = "f" * 64
    template = context["evidence"][0]
    context["evidence"].extend(
        dict(template, id=f"TEST_ONLY:unusable-wc:{i}", field="parent_customer_cash",
             scope="parent", text="TEST_ONLY working capital proxy")
        for i in range(9)
    )
    verified = dict(template, id="TEST_ONLY:verified-parent-wc", field="working_capital_cash_component",
                    scope="parent", text="TEST_ONLY verified working capital cash component")
    registry = service.root / loader.CONFIG
    registry.write_text(json.dumps({"600887": True}), encoding="utf-8")
    monkeypatch.setattr(loader.base, "build_operating_horizon_source_context", lambda **_: deepcopy(context))
    monkeypatch.setattr(loader, "_cash_rows", lambda *_: [verified])
    source = loader.build_operating_horizon_source_context(root=service.root, symbol="600887", now=NOW)
    binding = source["source_binding"]
    request = draft.build_request(source, binding)
    terms = json.loads(request.user.split("\nTERM_HISTORICAL_CANDIDATE_IDS=", 1)[1])
    eligible = cash_constraint_anchor_ids(source)["operating_wc_cash_cny"]
    assert eligible == [verified["id"]]
    assert terms["operating_wc_cash_cny"][0] == verified["id"]
    assert len(terms["operating_wc_cash_cny"]) == 8

    from value_investment_agent.application.research.agent_review.operating_cash_term_evidence import (
        build_cash_term_evidence,
    )

    guide = build_cash_term_evidence(source, binding)["operating_wc_cash_cny"]
    assert guide["validator_candidate_ids"] == [verified["id"]]
    assert guide["evidence"][0]["id"] == verified["id"]
    assert loader.build_operating_horizon_source_context(
        root=service.root, symbol="600887", now=NOW, binding=binding,
    ) == source
