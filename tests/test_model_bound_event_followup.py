"""Synthetic model-bound explanations only; no real issuer approval is created.

Use the shared model and artifact replay. Only PDF text extraction is replaced
with the text of synthetic originals; source-byte verification remains real.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal
import hashlib
import json
import sys

import pytest

from scripts.current import build_product_workbench_candidate as cli
from test_d2_conditional_shared_service import synthetic_chain, SYMBOL, DAY
from test_product_workbench_excel import _payload
from value_investment_agent.application.historical_validation import event_source_review
from value_investment_agent.application.product.company_research import _serialize_outcome
from value_investment_agent.application.product.decision_surface import (
    project_verified_decision_workbench, verify_current_decision_workbench,
)
from value_investment_agent.application.product.event_followup import read_event_followup
from value_investment_agent.application.product.research_publication_input import (
    prepare_research_publication_input, load_research_publication_input,
)
from value_investment_agent.m1_valuation_package_builder import build_descriptor
from value_investment_agent.presentation.read_models.event_followup import project_event_followup
from value_investment_agent.presentation.read_models.existing_research_report import (
    public_workbench_payload_from_snapshot,
)
from value_investment_agent.presentation.read_models.product_workbench import (
    EVENT_CATEGORY_LABELS, product_workbench_from_payload,
)
from value_investment_agent.research_application import ResearchApplicationService
from value_investment_agent.research_input import build_research_run_spec


SYNTHETIC = "SYNTHETIC_MODEL_BOUND_FOLLOWUP_TEST_ONLY"
UNUSED = "synthetic_unused_parameter"
SCENARIOS = ("bear", "base", "bull")
IMPACT_KINDS = (
    "UNQUANTIFIED_OPERATING_CHANGE", "DISTRIBUTION_RISK_UNRESOLVED",
    "UNQUANTIFIED_CAPITAL_ALLOCATION", "SUPPORTED_STARTING_FACTS_ONLY",
    "DERIVED_DUPLICATE", "NO_NUMERIC_GUIDANCE", "LIMITED_ZERO_RESTATEMENT",
)


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(root, relative, payload):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False,
                               default=lambda value: value.isoformat()), encoding="utf-8")
    return {"path": path.relative_to(root).as_posix(), "sha256": _digest(path)}


def _package_path(root, relative):
    path = root / relative
    return path.with_name(path.stem + "-input.json")


def _input_binding(root, workbench_binding):
    path = _package_path(root, workbench_binding["path"])
    return {"path": path.relative_to(root).as_posix(), "sha256": _digest(path)}


def _build_workbench(root, package, sources, relative, run_id, hour="10:00:00"):
    package = deepcopy(package)
    package["run_id"] = package["research_case"]["run_id"] = run_id
    input_binding = _write(root, _package_path(root, relative).relative_to(root).as_posix(), package)
    descriptor = build_descriptor(package, root=root)
    outcome = ResearchApplicationService().run_company_research(build_research_run_spec(descriptor))
    assert outcome.valuation.status == "conditional_research_only"
    assert outcome.decision_recommendation.recommendation_type == "NO_ACTION"
    assert outcome.human_research_approval is None
    payload = _serialize_outcome(outcome)
    workbench = {
        **payload, "schema_version": "product-current-workbench-request-v1",
        "generated_at": DAY.isoformat() + "T" + hour + "+00:00",
        "research_status": payload["status"], "suggested_state": "NO_ACTION",
        "portfolio_input_status": "BLOCKED_PRIVATE_INPUT", "position_guidance": None,
        "canonical_workbook_written": False,
        "source_verification": {"status": "LOCAL_BYTES_VERIFIED", "sources": sources},
        "input_descriptor_sha256": descriptor.input_sha256,
        "research_receipt": {"input_sha256": {"valuation_package": input_binding["sha256"]}},
    }
    binding = _write(root, relative, workbench)
    restored = verify_current_decision_workbench(workbench)
    assert restored.recommendation.as_policy() == workbench["decision_recommendation"]
    return binding, workbench, restored


@pytest.fixture
def followup_case(synthetic_chain, monkeypatch):
    root, package_path, _, _, _, _, _, _ = synthetic_chain
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["research_case"].update(positives=[], research_status="incomplete",
                                    evidence_status="partial")
    report = root / "runtime" / "synthetic-independent-report.md"
    report.parent.mkdir(exist_ok=True)
    report.write_text(SYNTHETIC + "\nUnquantified operating change; no approval.\n", encoding="utf-8")
    report_binding = {"path": report.relative_to(root).as_posix(), "sha256": _digest(report)}
    report_ref = {"id": "synthetic-independent-report", **report_binding}
    for assumption in package["assumptions"]["assumptions"]:
        assumption["evidence_refs"] = [*assumption["evidence_refs"], report_ref]
    package["assumptions"]["evidence_refs"].append(report_ref)
    consumed_name = next(item["assumption_name"] for item in package["assumption_bindings"]
                         if item["field_path"] == "cost_of_equity")
    unused = deepcopy(next(item for item in package["assumptions"]["assumptions"]
                           if item["name"] == consumed_name))
    unused["name"] = UNUSED
    package["assumptions"]["assumptions"].append(unused)
    package["sources"].append({**report_ref, "kind": "research_artifact",
                               "location": report_binding["path"]})
    scan = json.loads((root / package["model_validity_input"]["event_scan_ref"]["path"])
                      .read_text(encoding="utf-8"))
    template = scan["announcements"][0]
    originals, announcements, claims = [], [], []
    for index in range(7):
        announcement_id = str(9000000101 + index)
        text = SYNTHETIC + " synthetic announcement " + announcement_id
        original = root / "runtime" / (announcement_id + ".pdf")
        original.write_text(text, encoding="utf-8")
        binding = {"path": original.relative_to(root).as_posix(), "sha256": _digest(original)}
        ref = {"id": "synthetic-pdf-" + announcement_id, **binding}
        originals.append(binding)
        announcements.append({**deepcopy(template), "announcement_id": announcement_id,
                              "title": SYNTHETIC, "source_url": "https://example.test/" + announcement_id,
                              "evidence_refs": [ref]})
        claims.append({"label": "synthetic-claim-" + announcement_id,
                       "announcement_id": announcement_id, "summary": SYNTHETIC,
                       "anchors": [{"physical_page": 1, "excerpt": text}]})
    scan.update(announcements=announcements,
                evidence_refs=[ref for item in announcements for ref in item["evidence_refs"]])
    scan_binding = _write(root, "runtime/synthetic-model-scan.json", scan)
    package["model_validity_input"]["event_scan_ref"] = {
        "id": "synthetic-model-scan", "symbol": SYMBOL, **scan_binding,
    }
    sources = [report_binding, scan_binding, *originals]
    workbench_binding, workbench, restored = _build_workbench(
        root, package, sources, "runtime/synthetic-model-workbench.json", "synthetic-followup-model",
    )
    assumptions = {item.name: item for item in restored.dependency_objects["valuation_assumptions"].assumptions}
    impacts = []
    for index, claim in enumerate(claims):
        names = [consumed_name] if index < 3 else []
        impacts.append({
            "announcement_id": claim["announcement_id"], "assumption_names": names,
            "assumption_values": {name: {scenario: str(getattr(assumptions[name], scenario))
                                         for scenario in SCENARIOS} for name in names},
            "kind": IMPACT_KINDS[index],
            "parameters_changed": False, "user_visible": index < 3,
            "reason": SYNTHETIC + " no quantified parameter change",
            "reopen_condition": SYNTHETIC + " new dated operating evidence",
            "claim_labels": [claim["label"]],
        })
    packet = {
        "schema_version": "research-event-followup-v2", "symbol": SYMBOL,
        "scope": "SOURCE_ANCHORED_EXPLANATION_ONLY", "action": "no_order",
        "observed_at": DAY.isoformat() + "T11:00:00+00:00", "event_scan": scan_binding,
        "review_report": report_binding, "model_binding": workbench_binding,
        "model_input_binding": _input_binding(root, workbench_binding),
        "review_provenance": {"kind": "INDEPENDENT_RESEARCH_EXPLANATION_NOT_APPROVAL",
                              "reviewer_id": SYNTHETIC, "integrator_id": SYNTHETIC},
        "materiality_approved": False, "model_validity_approved": False, "investment_approved": False,
        "claims": claims, "assumption_impacts": impacts, "historical_labels": [],
        "unresolved_questions": [SYNTHETIC + " profitability remains unapproved"],
    }
    monkeypatch.setattr(event_source_review, "extract_pages",
                        lambda path: [path.read_text(encoding="utf-8")])
    payload = _payload()
    payload.update(as_of=DAY.isoformat(), generated_at=DAY.isoformat() + "T12:00:00+00:00")
    fixture_binding = _write(root, "runtime/product-fixture.json", {"scope": SYNTHETIC})
    payload["audit"]["evidence"][0].update(**fixture_binding, available_at=DAY.isoformat())
    project_verified_decision_workbench(payload, root=root, path=root / workbench_binding["path"],
                                      expected_sha256=workbench_binding["sha256"], register_company=True)
    card = next(item for item in payload["companies"] if item["symbol"] == SYMBOL)
    card["original_thesis"] = SYNTHETIC + " preserved user entry thesis"
    card["decision_review"].append({"label": "SYNTHETIC_MANUAL_NOTE", "value": SYNTHETIC})
    model = product_workbench_from_payload(payload)
    assert all(step.status == "BLOCKED" for step in model.companies[-1].decision_process
               if step.key != "valuation")
    return dict(root=root, package=package, sources=sources, workbench=workbench,
                workbench_binding=workbench_binding, packet=packet, model=model,
                assumptions=assumptions, consumed_name=consumed_name)


def _read(case, packet=None):
    binding = _write(case["root"], "runtime/synthetic-followup.json",
                     case["packet"] if packet is None else packet)
    return read_event_followup(root=case["root"], cutoff=DAY,
                               path=case["root"] / binding["path"], expected_sha256=binding["sha256"])


def _assert_preserved_decision_portfolio_price(before, after):
    old, new = before.companies[-1], after.companies[-1]
    assert after.companies[:-1] == before.companies[:-1]
    assert after.portfolio == before.portfolio
    assert after.opportunities == before.opportunities
    for field in ("price", "valuation", "margin_of_safety", "dividend", "scenarios",
                  "original_thesis", "thesis_change", "action"):
        assert getattr(new, field) == getattr(old, field)
    assert dict(new.decision_review)["SYNTHETIC_MANUAL_NOTE"] == SYNTHETIC
    assert [step.status for step in new.decision_process] == [step.status for step in old.decision_process]
    for prior, current in zip(old.decision_process, new.decision_process, strict=True):
        assert current.assessment_id == prior.assessment_id
        if prior.key != "research_gate":
            assert current == prior
    assert after.audit_evidence[:len(before.audit_evidence)] == before.audit_evidence
    assert after.today_items[:len(before.today_items)] == before.today_items
    assert after.action == before.action == "no_order"


def _assert_seven_announcement_audit_chain(before, after, followup):
    assert after.events[:len(before.events)] == before.events
    assert after.event_audit_decisions[:len(before.event_audit_decisions)] == before.event_audit_decisions
    new_events = after.events[len(before.events):]
    new_audits = after.event_audit_decisions[len(before.event_audit_decisions):]
    impacts = followup["assumption_impacts"]
    assert len(impacts) == len(new_audits) == 7
    assert len({item.event_id for item in new_audits}) == 7
    expected_ids = {
        f"research-followup-{SYMBOL}-{item['announcement_id']}-{followup['sha256'][:12]}"
        for item in impacts
    }
    assert {item.event_id for item in new_audits} == expected_ids
    assert len(after.audit_evidence) == len(before.audit_evidence) + 1
    evidence = after.audit_evidence[-1]
    assert len(new_events) == sum(item["user_visible"] for item in impacts)
    for impact in impacts:
        event_id = f"research-followup-{SYMBOL}-{impact['announcement_id']}-{followup['sha256'][:12]}"
        audit = next(item for item in new_audits if item.event_id == event_id)
        assert audit.state == "RESEARCH_EXPLANATION_ONLY"
        assert audit.visible is impact["user_visible"]
        assert audit.evidence_refs == (evidence.evidence_id,)
        assert audit.published_at == impact["published_at"]
        assert audit.observed_at == followup["observed_at"]
        assert audit.action == "no_order"
        if impact["user_visible"]:
            assert audit.disposition == "EVIDENCE_GAP"
            event = next(item for item in new_events if item.event_id == event_id)
            assert event.evidence_refs == audit.evidence_refs
            assert event.action == "no_order"
        else:
            assert audit.disposition in {"AUDIT_ONLY", "SUPPRESSED_DUPLICATE"}
            assert event_id not in {item.event_id for item in new_events}
    assert after.audit_evidence[-1].sha256 == followup["sha256"]
    assert after.audit_evidence[-1].path == followup["path"]
    assert after.overview.pending_count == len(after.today_items)


def test_success_preserves_user_decision_portfolio_price_and_visible_audit_chain(followup_case):
    case = followup_case
    before = case["model"]
    followup = _read(case)
    after = project_event_followup(before, followup)
    _assert_preserved_decision_portfolio_price(before, after)
    _assert_seven_announcement_audit_chain(before, after, followup)
    restored = verify_current_decision_workbench(case["workbench"])
    assert restored.recommendation.recommendation_type == "NO_ACTION"
    assert restored.recommendation.position_guidance is None
    assert restored.recommendation.action == after.action == "no_order"
    roundtrip = product_workbench_from_payload(public_workbench_payload_from_snapshot(
        json.loads(json.dumps(asdict(after), default=lambda value: value.isoformat()))))
    canonical_events = tuple(replace(event, category=replace(
        event.category, user_label=EVENT_CATEGORY_LABELS[event.category.code],
    )) for event in after.events)
    assert roundtrip == replace(after, events=canonical_events)


@pytest.mark.parametrize("financial_complete", [False, True])
def test_followup_preserves_replayed_partial_research_without_admitting_investment(
    followup_case, financial_complete,
):
    case = followup_case
    package = deepcopy(case["package"])
    research = package["research_case"]
    research["positives"] = [{"kind": "hypothesis", "text": SYNTHETIC,
                              "evidence_refs": ["case-source"]} for _ in range(3)]
    if financial_complete:
        research.update(research_status="financial_scope_approved", evidence_status="verified")
        research["financial_summary"]["financial_scope_review"] = {
            "scope": "historical_financial_basis_and_conditional_residual_income_research_only",
            "normalized_parent_profit_cny": None,
        }
    binding, _, restored = _build_workbench(
        case["root"], package, case["sources"], "runtime/partial-research-workbench.json",
        "synthetic-partial-research",
    )
    payload = public_workbench_payload_from_snapshot(
        json.loads(json.dumps(asdict(case["model"]), default=lambda value: value.isoformat())))
    project_verified_decision_workbench(payload, root=case["root"],
                                      path=case["root"] / binding["path"],
                                      expected_sha256=binding["sha256"])
    before = product_workbench_from_payload(payload)
    statuses = {step.key: step.status for step in before.companies[-1].decision_process}
    assert statuses["business_quality"] == "PASS"
    assert statuses["financial_facts"] == ("PASS" if financial_complete else "BLOCKED")
    steps = {step.key: step for step in before.companies[-1].decision_process}
    if financial_complete:
        assert "正常化盈利、持续分配、金融尾部及主估值未获批准" in steps["financial_facts"].reason
    else:
        assert "历史财务基础及条件剩余收益研究范围已审阅" not in steps["financial_facts"].reason
    assert "不等于高质量或投资批准" in steps["business_quality"].reason
    packet = deepcopy(case["packet"])
    packet.update(model_binding=binding, model_input_binding=_input_binding(case["root"], binding))
    followup = _read(case, packet)
    after = project_event_followup(before, followup)
    _assert_preserved_decision_portfolio_price(before, after)
    _assert_seven_announcement_audit_chain(before, after, followup)
    assert restored.recommendation.recommendation_type == "NO_ACTION"
    assert restored.recommendation.entry_zone is None
    assert restored.recommendation.reduce_zone is None
    assert restored.recommendation.position_guidance is None
    assert statuses["research_gate"] == statuses["decision_gate"] == "BLOCKED"


@pytest.mark.parametrize("step_key", ["model_applicability", "price_bridge", "research_gate",
                                      "portfolio_gate", "decision_gate"])
def test_followup_still_rejects_investment_admission(followup_case, step_key):
    before = followup_case["model"]
    card = before.companies[-1]
    admitted = replace(card, decision_process=tuple(
        replace(step, status="PASS") if step.key == step_key else step
        for step in card.decision_process))
    model = replace(before, companies=(*before.companies[:-1], admitted))
    with pytest.raises(ValueError, match="cannot inherit admitted decisions"):
        project_event_followup(model, _read(followup_case))


@pytest.mark.parametrize("drift", ["binding", "active-reference"])
def test_partial_research_requires_same_displayed_workbench_without_impacts(followup_case, drift):
    before = followup_case["model"]
    card = before.companies[-1]
    steps = tuple(replace(step, status="PASS") if step.key == "business_quality" else step
                  for step in card.decision_process)
    if drift == "active-reference":
        steps = tuple(replace(step, evidence_refs=(before.audit_evidence[0].evidence_id,))
                      if step.key == "valuation" else step
                      for step in steps)
    model = replace(before, companies=(*before.companies[:-1], replace(card, decision_process=steps)))
    followup = _read(followup_case)
    followup["assumption_impacts"] = []
    if drift == "binding":
        followup["model_binding"] = {"path": "runtime/other-workbench.json", "sha256": "f" * 64}
    with pytest.raises(ValueError, match="differs from the displayed company decision"):
        project_event_followup(model, followup)


@pytest.mark.parametrize("mutation", [
    "missing-announcement", "extra-announcement", "duplicate-announcement",
    "forged-excerpt", "wrong-page", "unknown-assumption", "bear-drift", "base-drift", "bull-drift",
    "nan-parameter", "missing-scenario", "parameters-changed", "materiality-approved",
    "model-approved", "investment-approved", "cross-announcement-anchor",
])
def test_invalid_model_bound_packet_is_rejected(followup_case, mutation):
    case = followup_case
    packet = deepcopy(case["packet"])
    impact = packet["assumption_impacts"][0]
    values = impact["assumption_values"][case["consumed_name"]]
    if mutation == "missing-announcement":
        packet["assumption_impacts"].pop()
    elif mutation in {"extra-announcement", "duplicate-announcement"}:
        extra = deepcopy(impact)
        if mutation == "extra-announcement":
            extra["announcement_id"] = "9000000999"
        packet["assumption_impacts"].append(extra)
    elif mutation == "forged-excerpt":
        packet["claims"][0]["anchors"][0]["excerpt"] = "SYNTHETIC_FORGED_TEXT_NOT_IN_ORIGINAL"
    elif mutation == "wrong-page":
        packet["claims"][0]["anchors"][0]["physical_page"] = 2
    elif mutation == "unknown-assumption":
        impact["assumption_names"] = ["synthetic-unregistered-parameter"]
    elif mutation.endswith("-drift"):
        scenario = mutation.split("-")[0]
        values[scenario] = str(Decimal(values[scenario]) + Decimal("0.01"))
    elif mutation == "nan-parameter":
        values["base"] = "NaN"
    elif mutation == "missing-scenario":
        values.pop("bull")
    elif mutation == "parameters-changed":
        impact["parameters_changed"] = True
    elif mutation == "cross-announcement-anchor":
        impact["claim_labels"] = [packet["claims"][1]["label"]]
    else:
        key = {"materiality-approved": "materiality_approved", "model-approved": "model_validity_approved",
               "investment-approved": "investment_approved"}[mutation]
        packet[key] = True
    with pytest.raises(ValueError):
        _read(case, packet)


@pytest.mark.parametrize("role", ["review_report", "model_binding", "model_input_binding", "original"])
def test_report_workbench_or_original_byte_drift_rejected(followup_case, role):
    case = followup_case
    binding = case["sources"][-1] if role == "original" else case["packet"][role]
    path = case["root"] / binding["path"]
    path.write_bytes(path.read_bytes() + b"\nSYNTHETIC_BYTE_DRIFT")
    with pytest.raises(ValueError):
        _read(case)


def test_resealed_workbench_still_requires_real_artifact_replay(followup_case):
    case = followup_case
    workbench = deepcopy(case["workbench"])
    workbench["artifact_bundle"]["artifacts"][0]["canonical_payload"] += " "
    packet = deepcopy(case["packet"])
    packet["model_binding"] = _write(case["root"], "runtime/resealed-workbench.json", workbench)
    with pytest.raises(ValueError, match="hash"):
        _read(case, packet)


def test_registered_but_unconsumed_assumption_cannot_claim_model_impact(followup_case):
    case = followup_case
    assert UNUSED in case["assumptions"]
    assert not any(item["assumption_name"] == UNUSED for item in case["package"]["assumption_bindings"])
    packet = deepcopy(case["packet"])
    impact = packet["assumption_impacts"][0]
    impact["assumption_names"] = [UNUSED]
    impact["assumption_values"] = {UNUSED: {
        scenario: str(getattr(case["assumptions"][UNUSED], scenario)) for scenario in SCENARIOS
    }}
    with pytest.raises(ValueError):
        _read(case, packet)


@pytest.mark.parametrize("mutation, error", [
    ("missing-input", "model input package requires"),
    ("receipt-hash", "executed research receipt"),
    ("descriptor-hash", "model input descriptor"),
    ("resealed-facts", "replayed financial_facts"),
    ("resealed-assumptions", "replayed valuation_assumptions"),
    ("missing-consumed-scenario", "consumed|unknown parameters"),
])
def test_input_package_must_match_receipt_descriptor_and_replayed_dependencies(
    followup_case, mutation, error,
):
    case = followup_case
    packet = deepcopy(case["packet"])
    workbench = deepcopy(case["workbench"])
    if mutation == "missing-input":
        packet.pop("model_input_binding")
    elif mutation == "receipt-hash":
        workbench["research_receipt"]["input_sha256"]["valuation_package"] = "0" * 64
    elif mutation == "descriptor-hash":
        workbench["input_descriptor_sha256"] = "0" * 64
    else:
        package = json.loads((case["root"] / packet["model_input_binding"]["path"])
                             .read_text(encoding="utf-8"))
        if mutation == "resealed-facts":
            inputs = package["facts"]["operating_inputs"]
            key = next(iter(inputs))
            inputs[key] = str(Decimal(inputs[key]) + Decimal("1"))
        elif mutation == "resealed-assumptions":
            assumption = next(item for item in package["assumptions"]["assumptions"]
                              if item["name"] == case["consumed_name"])
            for scenario in SCENARIOS:
                assumption[scenario] = str(Decimal(assumption[scenario]) + Decimal("0.001"))
        else:
            package["assumption_bindings"] = [
                item for item in package["assumption_bindings"]
                if not (item["assumption_name"] == case["consumed_name"] and item["scenario"] == "bull")
            ]
        packet["model_input_binding"] = _write(case["root"], "runtime/resealed-input.json", package)
        workbench["research_receipt"]["input_sha256"]["valuation_package"] = packet["model_input_binding"]["sha256"]
        workbench["input_descriptor_sha256"] = build_descriptor(package, root=case["root"]).input_sha256
    if mutation != "missing-input":
        packet["model_binding"] = _write(case["root"], "runtime/resealed-input-workbench.json", workbench)
    with pytest.raises(ValueError, match=error):
        _read(case, packet)


@pytest.mark.parametrize("retained_reference", [False, True])
@pytest.mark.parametrize("model_drift", ["run-identity", "scenario-values"])
def test_followup_must_bind_current_displayed_model_not_another_retained_model(
    followup_case, retained_reference, model_drift,
):
    case = followup_case
    package = deepcopy(case["package"])
    if model_drift == "scenario-values":
        assumption = next(item for item in package["assumptions"]["assumptions"]
                          if item["name"] == case["consumed_name"])
        for scenario in SCENARIOS:
            value = str(Decimal(assumption[scenario]) + Decimal("0.005"))
            assumption[scenario] = value
            package["facts"]["scenario_inputs"][scenario]["cost_of_equity"] = value
            for item in package["assumption_bindings"]:
                if item["assumption_name"] == case["consumed_name"] and item["scenario"] == scenario:
                    item["expected_value"] = value
    binding, workbench, restored = _build_workbench(
        case["root"], package, case["sources"], "runtime/other-model.json",
        "synthetic-other-model", hour="09:30:00",
    )
    assert binding["sha256"] != case["workbench_binding"]["sha256"]
    assert workbench["generated_at"] < case["workbench"]["generated_at"]
    if model_drift == "scenario-values":
        assert workbench["valuation"]["base_value"] != case["workbench"]["valuation"]["base_value"]
    packet = deepcopy(case["packet"])
    packet["model_binding"] = binding
    packet["model_input_binding"] = _input_binding(case["root"], binding)
    assumptions = {item.name: item for item in restored.dependency_objects["valuation_assumptions"].assumptions}
    for impact in packet["assumption_impacts"]:
        impact["assumption_values"] = {
            name: {scenario: str(getattr(assumptions[name], scenario)) for scenario in SCENARIOS}
            for name in impact["assumption_names"]
        }
    followup = _read(case, packet)
    model = case["model"]
    if retained_reference:
        historical = replace(model.audit_evidence[-1], evidence_id="synthetic-retained-other-model",
                             path=binding["path"], sha256=binding["sha256"])
        card = replace(model.companies[-1], evidence_refs=(*model.companies[-1].evidence_refs,
                                                         historical.evidence_id))
        model = replace(model, companies=(*model.companies[:-1], card),
                        audit_evidence=(*model.audit_evidence, historical))
        assert historical.evidence_id in card.evidence_refs
        assert all(step.assessment_id != historical.evidence_id for step in card.decision_process)
    with pytest.raises(ValueError, match="displayed company decision"):
        project_event_followup(model, followup)


def test_hidden_disposition_remains_audited_without_a_visible_event(followup_case):
    case = followup_case
    followup = _read(case)
    after = project_event_followup(case["model"], followup)
    assert sum(not item["user_visible"] for item in followup["assumption_impacts"]) == 4
    _assert_seven_announcement_audit_chain(case["model"], after, followup)
    _assert_preserved_decision_portfolio_price(case["model"], after)


def test_all_hidden_impacts_keep_seven_audits_and_preserve_decision(followup_case):
    case = followup_case
    packet = deepcopy(case["packet"])
    for impact in packet["assumption_impacts"]:
        impact["user_visible"] = False
    followup = _read(case, packet)
    after = project_event_followup(case["model"], followup)
    assert after.events == case["model"].events
    _assert_seven_announcement_audit_chain(case["model"], after, followup)
    _assert_preserved_decision_portfolio_price(case["model"], after)


def test_cli_consumes_model_bound_followup_and_exports_reverifiable_handoff(followup_case, monkeypatch):
    case = followup_case
    root = case["root"]
    envelope = {
        "schema_version": "historical-company-read-model-preview-v1",
        "snapshot": asdict(case["model"]), "action": "no_order",
        "canonical_written": False, "historical_preview": True,
        "decision_workbench_binding": case["workbench_binding"],
    }
    base = _write(root, "runtime/base-read-model.json", envelope)
    handoff = root / "runtime" / "base-handoff.json"
    prepare_research_publication_input(root=root, read_model_path=root / base["path"],
                                      expected_sha256=base["sha256"], output_path=handoff)
    followup_binding = _write(root, "runtime/cli-followup.json", case["packet"])
    output = root / "runtime" / "cli-result.json"
    exported = root / "runtime" / "cli-handoff.json"
    monkeypatch.setattr(cli, "ROOT", root)
    monkeypatch.setattr(sys, "argv", [
        "candidate", "--historical-preview", "--read-model-only", "--base-publication-input",
        "--base-payload", str(handoff), "--base-payload-sha256", _digest(handoff),
        "--generated-at", DAY.isoformat() + "T12:00:00+00:00",
        "--event-followup", followup_binding["path"], followup_binding["sha256"],
        "--output", str(output), "--publication-input", str(exported),
    ])
    assert cli.main() == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    snapshot = result["snapshot"]
    replayed = load_research_publication_input(root=root, path=exported, expected_sha256=_digest(exported))
    assert replayed["snapshot"] == snapshot
    assert replayed["publication_approved"] is False
    assert replayed["canonical_written"] is False
    assert replayed["strict_pit_admitted"] is False
    model = product_workbench_from_payload(public_workbench_payload_from_snapshot(snapshot))
    followup = read_event_followup(root=root, cutoff=DAY,
                                  path=root / followup_binding["path"],
                                  expected_sha256=followup_binding["sha256"])
    _assert_preserved_decision_portfolio_price(case["model"], model)
    _assert_seven_announcement_audit_chain(case["model"], model, followup)
    assert result["event_followup_binding"]["sha256"] == followup_binding["sha256"]
    assert result["canonical_written"] is False
    assert result["action"] == model.action == "no_order"
