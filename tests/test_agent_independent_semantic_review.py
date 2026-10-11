from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from test_agent_semantic_review import mock_case
from value_investment_agent.application.product import agent_research_surface as surface
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.research.agent_review import llm_pilot
from value_investment_agent.application.research.agent_review.semantic_review import semantic_binding_sha256
from value_investment_agent.application.research.agent_review.snapshot import ResearchSnapshot
from value_investment_agent.application.research.agent_review.source_context import ExcerptRequest
from value_investment_agent.infrastructure.agent_runtime.provider import MockLLMProvider


REVIEW = Path("config/research-reviews/600519-agent-independent-20261011.json")
PACKET = Path("runtime/daily-trade-assistant/20261011-real-admission-neutral-v3/agent-packet.json")
ROOT = Path(__file__).resolve().parents[1]


def _payload(as_of):
    return {"as_of": as_of, "generated_at": datetime.now(timezone.utc).isoformat(),
            "action": "no_order", "audit": {"evidence": []},
            "companies": [{"symbol": "600519", "decision_status": "WAIT",
                           "fact_confidence": "LOW", "g3_approved": False,
                           "position_guidance": None}]}


@pytest.fixture
def review_case(mock_case, tmp_path, monkeypatch):
    workbench, digest, original, snapshot, replies = mock_case
    monkeypatch.setattr(llm_pilot, "load_research_snapshot", lambda **_: snapshot)
    monkeypatch.setattr(surface, "load_research_snapshot", lambda **_: snapshot)
    text = original.read_text(encoding="utf-8")
    requests = tuple(ExcerptRequest(ref["id"], ref["path"], ref["sha256"],
                                   ref["available_at"], text, text_start=0, text_end=len(text))
                     for ref in snapshot.evidence)
    path = tmp_path / "runtime/packet.json"
    packet = llm_pilot.run_llm_research_pilot(
        root=tmp_path, workbench=workbench, workbench_sha256=digest, symbol="600519",
        output=path, provider=MockLLMProvider({key: json.dumps(value)
                                             for key, value in replies.items()}),
        mode="mock", source_requests=requests)
    review = json.loads((ROOT / REVIEW).read_text(encoding="utf-8"))
    review.update(packet_path=path.relative_to(tmp_path).as_posix(), packet_sha256=sha256_file(path),
                  context_sha256=packet["source_context"]["context_sha256"],
                  reviewed_at=datetime.now(timezone.utc).isoformat())
    for row, finding, sidecar in zip(review["findings"], packet["findings"],
                                     packet["finding_source_context"], strict=True):
        cited = set(finding["supporting_evidence_refs"] + finding["counter_evidence_refs"])
        row.update(finding_id=finding["finding_id"], agent_role=finding["agent_role"],
                   finding_sha256=semantic_binding_sha256(finding),
                   finding_context_sha256=sidecar["finding_context_sha256"],
                   excerpt_bindings=[{"source_id": e["source_id"], "path": e["path"],
                                      "source_sha256": e["sha256"],
                                      "excerpt_sha256": semantic_binding_sha256(e)}
                                     for e in packet["source_context"]["excerpts"]
                                     if e["source_id"] in cited])
        for axis in ("facts", "inference", "counterevidence"):
            row[axis]["rationale"] = "Synthetic judgment for consumer boundary tests only."
    review_path = tmp_path / REVIEW
    review_path.parent.mkdir(parents=True)
    review_path.write_text(json.dumps(review), encoding="utf-8")
    return tmp_path, path, review_path, review, packet, original


def _project(case, payload, binding=True):
    root, packet_path, review_path, *_ = case
    surface.project_verified_agent_packet(payload, root=root, path=packet_path,
        expected_sha256=sha256_file(packet_path), independent_review_binding=(
            {"path": review_path.relative_to(root).as_posix(), "sha256": sha256_file(review_path)}
            if binding else None))


def test_completed_independent_verdict_coexists_with_pending_human(review_case):
    payload = _payload(review_case[4]["research_as_of"])
    before = deepcopy(payload)
    _project(review_case, payload)
    company = payload["companies"][0]
    assert {k: v for k, v in company.items() if k != "agent_research"} == before["companies"][0]
    assert payload["action"] == "no_order"
    for view in company["agent_research"]:
        assert view["status"] == "PENDING_HUMAN_REVIEW"
        semantic = view["semantic_review"]
        assert semantic["status"] == "PENDING_SEMANTIC_REVIEW"
        assert semantic["human_confirmation"]["status"] == "PENDING"
        assert semantic["factual_verification"]["status"] == "PENDING"
        independent = semantic["independent_review"]
        assert independent["status"] == "COMPLETED_NON_ADMITTING"
        assert independent["approval_count"] == independent["formal_fact_count"] == 0
        assert independent["decision_changed"] is False
    assert company["agent_research"][1]["semantic_review"]["independent_review"]["inference"][
        "verdict"] == "INSUFFICIENT_EXCERPT_SUPPORT"


@pytest.mark.parametrize("mutation", [
    "symbol", "packet_path", "packet_sha256", "context_sha256", "finding_id",
    "agent_role", "finding_sha256", "finding_context_sha256", "excerpt_sha256",
    "source_sha256", "source_path", "source_id", "duplicate", "missing", "verdict",
    "blank_rationale", "axis_extra", "row_extra", "scope", "approval", "facts", "action",
    "decision", "top_extra", "date", "future_date", "reviewer",
])
def test_review_rejects_drift_and_escalation_without_mutating_product(review_case, mutation):
    root, path, review_path, review, packet, _ = review_case
    row = review["findings"][0]
    if mutation in {"symbol", "packet_path", "packet_sha256", "context_sha256", "scope", "action"}:
        review[mutation] = "invalid"
    elif mutation in {"finding_id", "agent_role", "finding_sha256", "finding_context_sha256"}:
        row[mutation] = "invalid"
    elif mutation in {"excerpt_sha256", "source_sha256", "source_id"}:
        row["excerpt_bindings"][0][mutation] = "invalid"
    elif mutation == "source_path":
        row["excerpt_bindings"][0]["path"] = "other.txt"
    elif mutation == "duplicate":
        review["findings"][1] = deepcopy(row)
    elif mutation == "missing":
        review["findings"].pop()
    elif mutation == "verdict":
        row["inference"]["verdict"] = "APPROVED"
    elif mutation == "blank_rationale":
        row["facts"]["rationale"] = " "
    elif mutation == "axis_extra":
        row["facts"]["confidence"] = "HIGH"
    elif mutation == "row_extra":
        row["g3_approved"] = True
    elif mutation == "approval":
        review["approval_count"] = True
    elif mutation == "facts":
        review["formal_fact_count"] = 1
    elif mutation == "decision":
        review["decision_changed"] = True
    elif mutation == "top_extra":
        review["human_confirmation"] = "APPROVED"
    elif mutation == "date":
        review["reviewed_at"] = "2020-01-01T00:00:00"
    elif mutation == "future_date":
        review["reviewed_at"] = "2099-01-01T00:00:00+00:00"
    elif mutation == "reviewer":
        review["reviewer"] = " "
    review_path.write_text(json.dumps(review), encoding="utf-8")
    payload = _payload(packet["research_as_of"])
    before = deepcopy(payload)
    with pytest.raises(ValueError):
        _project(review_case, payload)
    assert payload == before
    # Review rejection must not block unrelated verified packet research.
    _project(review_case, payload, binding=False)
    assert payload["companies"][0]["agent_research"][0]["semantic_review"][
        "independent_review"]["status"] == "PENDING"


def test_review_file_hash_is_required_and_path_cannot_escape(review_case):
    root, packet_path, review_path, _, packet, _ = review_case
    for binding in ({"path": REVIEW.as_posix(), "sha256": "0" * 64},
                    {"path": "../review.json", "sha256": sha256_file(review_path)},
                    {"path": REVIEW.as_posix(), "sha256": sha256_file(review_path), "approve": True}):
        payload = _payload(packet["research_as_of"])
        before = deepcopy(payload)
        with pytest.raises(ValueError):
            surface.project_verified_agent_packet(payload, root=root, path=packet_path,
                expected_sha256=sha256_file(packet_path), independent_review_binding=binding)
        assert payload == before


def test_changed_original_is_rejected_before_independent_projection(review_case):
    payload = _payload(review_case[4]["research_as_of"])
    before = deepcopy(payload)
    review_case[5].write_text("Changed source", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        _project(review_case, payload)
    assert payload == before


@pytest.mark.parametrize("change", ["finding", "excerpt", "packet_scope", "packet_symbol"])
def test_review_cannot_bypass_packet_revalidation(review_case, change):
    root, path, review_path, review, packet, _ = review_case
    if change == "finding":
        packet["findings"][0]["claim"] = "Dividends and investment are approved."
    elif change == "excerpt":
        packet["source_context"]["excerpts"][0]["excerpt"] = "Invented official source excerpt."
    elif change == "packet_scope":
        packet["formal_fact_count"] = 1
    else:
        packet["symbol"] = "000001"
    path.write_text(json.dumps(packet), encoding="utf-8")
    review["packet_sha256"] = sha256_file(path)
    review_path.write_text(json.dumps(review), encoding="utf-8")
    payload = _payload(packet["research_as_of"])
    before = deepcopy(payload)
    with pytest.raises(ValueError):
        _project(review_case, payload)
    assert payload == before


def test_late_audit_conflict_does_not_leave_partial_product_evidence(review_case):
    payload = _payload(review_case[4]["research_as_of"])
    # The second cited source conflicts after the first source would be appended.
    source_id = sorted({ref for f in review_case[4]["findings"]
                        for ref in f["supporting_evidence_refs"]})[-1]
    payload["audit"]["evidence"] = [{"evidence_id": source_id, "path": "wrong.txt"}]
    before = deepcopy(payload)
    with pytest.raises(ValueError, match="conflicts"):
        _project(review_case, payload)
    assert payload == before


@pytest.mark.skipif(not (ROOT / PACKET).is_file(), reason="Local source-bound runtime packet is absent")
def test_actual_packet_and_originals_accept_only_bounded_review():
    payload = _payload("2026-10-08")
    surface.project_verified_agent_packet(payload, root=ROOT, path=ROOT / PACKET,
        expected_sha256=sha256_file(ROOT / PACKET), independent_review_binding={
            "path": REVIEW.as_posix(), "sha256": sha256_file(ROOT / REVIEW)})
    reviews = [view["semantic_review"] for view in payload["companies"][0]["agent_research"]]
    assert len(reviews) == 3
    assert all(r["independent_review"]["status"] == "COMPLETED_NON_ADMITTING" for r in reviews)
    assert all(r["human_confirmation"]["status"] == "PENDING" for r in reviews)
    assert reviews[0]["independent_review"]["inference"]["verdict"] == "REASONABLE_WITH_LIMITS"
    assert reviews[1]["independent_review"]["inference"]["verdict"] == "INSUFFICIENT_EXCERPT_SUPPORT"
    assert reviews[2]["independent_review"]["inference"]["verdict"] == "REASONABLE_RESEARCH_QUESTION"


def test_report_keeps_unreviewed_findings_pending_without_completed_verdict_text(review_case):
    from value_investment_agent.presentation.daily_trade_assistant import _render_report

    packet = review_case[4]
    payload = _payload(packet["research_as_of"])
    _project(review_case, payload, binding=False)
    workbench = {"symbol": "600519", "decision_recommendation": {
        "recommendation_type": "NO_ACTION", "decision_as_of": packet["research_as_of"]}}
    report = _render_report(workbench, payload, {"status": "PENDING_EXTERNAL_DATA"},
                            packet["scope"], None, None)
    assert "已绑定独立研究审阅" not in report
    assert "当前尚未获人工语义批准" in report
    assert all(view["semantic_review"]["independent_review"]["status"] == "PENDING"
               for view in payload["companies"][0]["agent_research"])


@pytest.mark.parametrize("changed_field", [None, "packet_fingerprint",
    "missing_packet_file", "wrong_packet_hash", "missing_packet_hash",
    "missing_review_file", "wrong_review_hash", "missing_review_hash", "missing_review_binding",
    *[
    f.name for f in fields(ResearchSnapshot)
    if f.name not in {"input_fingerprint", "workbench_sha256"}
]])
def test_historical_review_reuse_compares_every_snapshot_content_field(
        review_case, monkeypatch, changed_field):
    from value_investment_agent.application.product import daily_trade_assistant as daily
    from value_investment_agent.application.research.agent_review import snapshot as snapshots

    root, packet_path, review_path, _, packet, _ = review_case
    original = surface.load_research_snapshot()
    current = replace(original, input_fingerprint="new-generation-fingerprint",
                      workbench_sha256="new-generation-workbench-hash")
    if changed_field == "packet_fingerprint":
        packet["research_input_fingerprint"] = "wrong-original-fingerprint"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
    elif changed_field in {f.name for f in fields(ResearchSnapshot)}:
        # The branch must compare even fields added to ResearchSnapshot later.
        current = replace(current, **{changed_field: {"changed": changed_field}})
    calls = []
    def load(**kwargs):
        calls.append(kwargs)
        if kwargs["workbench"] == root / packet["workbench_path"]:
            assert kwargs["expected_sha256"] == packet["workbench_sha256"]
            return original
        assert kwargs["expected_sha256"] == sha256_file(kwargs["workbench"])
        return current
    monkeypatch.setattr(snapshots, "load_research_snapshot", load)
    monkeypatch.setattr(daily, "inspect_daily_case_assets", lambda **_: {"blockers": []})
    config = root / "config"
    package, request = config / "reuse-package.json", config / "reuse-request.json"
    package.write_text(json.dumps({"symbol": "600519", "point_in_time": {
        "research_as_of": original.as_of.isoformat()}}), encoding="utf-8")
    request.write_text(json.dumps({"symbol": "600519"}), encoding="utf-8")
    case = {"package": package.relative_to(root).as_posix(), "package_sha256": sha256_file(package),
            "schedule_request": request.relative_to(root).as_posix(),
            "schedule_request_sha256": sha256_file(request),
            "reviewed_agent_packet": packet_path.relative_to(root).as_posix(),
            "reviewed_agent_packet_sha256": sha256_file(packet_path),
            "independent_agent_review": review_path.relative_to(root).as_posix(),
            "independent_agent_review_sha256": sha256_file(review_path)}
    if changed_field == "missing_packet_file":
        case["reviewed_agent_packet"] = "runtime/missing-reviewed-packet.json"
    elif changed_field == "wrong_packet_hash":
        case["reviewed_agent_packet_sha256"] = "0" * 64
    elif changed_field == "missing_packet_hash":
        case.pop("reviewed_agent_packet_sha256")
    elif changed_field == "missing_review_file":
        case["independent_agent_review"] = "config/research-reviews/missing-review.json"
    elif changed_field == "wrong_review_hash":
        case["independent_agent_review_sha256"] = "0" * 64
    elif changed_field == "missing_review_hash":
        case.pop("independent_agent_review_sha256")
    elif changed_field == "missing_review_binding":
        case.pop("independent_agent_review")
    workbench = {"symbol": "600519", "action": "no_order", "suggested_state": "NO_ACTION",
                 "decision_recommendation": {"decision_as_of": original.as_of.isoformat()}}
    def build(**kwargs):
        kwargs["output_path"].write_text(json.dumps(workbench), encoding="utf-8")
        return {"result": workbench}
    monkeypatch.setattr(daily, "build_current_workbench_for_symbol", build)
    monkeypatch.setattr(daily, "run_agent_research_pilot", lambda **_: pytest.fail("Must reuse old packet"))
    monkeypatch.setattr(daily, "run_llm_research_pilot", lambda **_: pytest.fail("No provider fallback"))
    def run():
        return daily.run_daily_trade_assistant(root=root, symbol="600519", case=case,
            output_dir=root / "runtime/historical-reuse-test", agent_mode="offline",
            report_renderer=lambda *args: "Research only\n" + (args[5] or ""))
    result = run()
    output = root / "runtime/historical-reuse-test"
    assert result["status"] == "RESEARCH_RUN_COMPLETED_WITH_ADMISSION_STATUS"
    assert result["recommendation_type"] == "NO_ACTION"
    assert result["action"] == "no_order" and result["position_guidance"] is None
    assert result["canonical_workbook_written"] is False
    assert json.loads((output / "workbench.json").read_text(encoding="utf-8")) == workbench
    assert json.loads((output / "receipt.json").read_text(encoding="utf-8")) == result
    report = (output / "report.md").read_text(encoding="utf-8")
    assert "Research only" in report
    if changed_field is not None:
        assert result["agent_scope"] is None
        assert result["agent_error"].startswith("Independent Agent review reuse rejected; research continues:")
        assert result["agent_error"] in report
        assert "agent_packet" not in result["outputs"]
        assert not (output / "agent-packet.json").exists()
        assert "agent_research" not in workbench
        if changed_field == "packet_fingerprint" or changed_field in {f.name for f in fields(ResearchSnapshot)}:
            assert "does not match current research inputs" in result["agent_error"]
    else:
        assert result["agent_scope"] == packet["scope"] == "MOCK_LLM_RESEARCH_NOT_ADMITTED"
        assert result["agent_error"] is None
        assert result["outputs"]["agent_packet"]["path"] == case["reviewed_agent_packet"]
        assert result["outputs"]["agent_packet"]["sha256"] == case["reviewed_agent_packet_sha256"]
    assert len(calls) == (0 if changed_field in {
        "missing_packet_file", "wrong_packet_hash", "missing_packet_hash",
        "missing_review_file", "wrong_review_hash", "missing_review_hash", "missing_review_binding"} else 2)
