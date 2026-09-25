from datetime import datetime, timezone
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from value_investment_agent.m5_event_run import m5_event_run_receipt_from_payload
from value_investment_agent.m5_pending_research_input import build_pending_research_input
from value_investment_agent.research_application import ResearchApplicationService
from value_investment_agent.research_input import build_research_run_spec, descriptor_from_payload
from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository


ROOT = Path(os.environ.get("M5_ACTUAL_EVIDENCE_ROOT", Path(__file__).resolve().parents[1]))
LOCAL = Path(__file__).resolve().parents[1]
BASE = ROOT / "runtime/m5-600519-disclosure-rescan-20260925"
RECEIPT = BASE / "actual-valid-receipts/m5-receipt-44a756ccad5433e236c3d74ff3ce3a75d65be835de52109407ad6ac4f0e0576d.json"
FACTS = LOCAL / "runtime/m5-verified-facts-actual-20260925.json"
EQUITY_POINTER = ROOT / "runtime/company-research/600519-consolidated-parent-equity-inputs-latest.json"
AT = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


def _inputs():
    if any(not path.is_file() for path in (RECEIPT, FACTS, EQUITY_POINTER)):
        pytest.skip("ACTUAL 600519 evidence is unavailable")
    pointer = json.loads(EQUITY_POINTER.read_text(encoding="utf-8"))
    equity_path = (ROOT / pointer["path"] / "evidence.json").resolve()
    assert equity_path.is_relative_to(ROOT.resolve())
    equity_sha = hashlib.sha256(equity_path.read_bytes()).hexdigest()
    assert equity_sha == pointer["sha256"]
    return dict(
        receipt=m5_event_run_receipt_from_payload(json.loads(RECEIPT.read_text(encoding="utf-8"))["receipt"]),
        facts_file_bytes=FACTS.read_bytes(), equity_file_bytes=equity_path.read_bytes(),
        name="贵州茅台", profile_id="quality_compounder",
        evaluated_at=AT,
    )


def test_actual_pending_descriptor_routes_to_null_not_ready_valuation():
    inputs = _inputs()
    descriptor = build_pending_research_input(**inputs)
    restored = descriptor_from_payload(descriptor.as_policy())
    assert restored.input_sha256 == descriptor.input_sha256
    assert restored.facts.operating_inputs["start_book_equity"] == 251253594419.50
    assert restored.facts.operating_inputs["ordinary_shares"] == 1250081601
    assert restored.facts.scenario_inputs is None
    assert restored.facts.verified is False
    assert restored.assumptions is None
    assert restored.point_in_time.report_period.isoformat() == "2026-06-30"
    assert restored.point_in_time.research_as_of.isoformat() == "2026-09-25"
    event_pdfs = {(ref["sha256"], ref["source_url"])
                  for event in inputs["receipt"].active_events
                  for ref in event.evidence_refs if ref.get("source_url")}
    source_pdfs = {(source.sha256, source.location) for source in restored.sources
                   if source.kind == "filing"}
    case_pdfs = {(ref["sha256"], ref["source_url"])
                 for ref in restored.research_case.evidence_refs if ref.get("source_url")}
    assert len(event_pdfs) == 2
    assert source_pdfs == case_pdfs == event_pdfs
    assert any(source.id == "actual-receipt"
               and source.sha256 == inputs["receipt"].state_sha256
               for source in restored.sources)

    spec = build_research_run_spec(restored)
    outcome = ResearchApplicationService(InMemoryResearchArtifactRepository()).run_company_research(spec)
    assert outcome.valuation.status == "not_ready"
    assert (outcome.valuation.bear_value, outcome.valuation.base_value,
            outcome.valuation.bull_value) == (None, None, None)
    assert "quality_compounder_scenario_inputs_not_registered" in outcome.valuation.blockers
    assert outcome.valuation.valuation_date.isoformat() == "2026-06-30"


def test_pending_descriptor_rejects_unrelated_equity_filing():
    inputs = _inputs()
    equity = json.loads(inputs["equity_file_bytes"])
    equity["current_disclosed_basis"]["raw_file_hash"] = "0" * 64
    inputs["equity_file_bytes"] = json.dumps(equity).encode("utf-8")
    with pytest.raises(ValueError, match="not tied"):
        build_pending_research_input(**inputs)


def test_pending_descriptor_rejects_event_without_unique_pinned_pdf():
    inputs = _inputs()
    original = inputs["receipt"]
    event = original.active_events[0]
    changed = replace(event, evidence_refs=tuple(ref for ref in event.evidence_refs
                                                  if not ref.get("source_url")))
    inputs["receipt"] = SimpleNamespace(
        namespace=original.namespace, action=original.action,
        active_events=(changed, *original.active_events[1:]),
        generated_at=original.generated_at, receipt_id=original.receipt_id,
        state_sha256=original.state_sha256,
    )
    with pytest.raises(ValueError, match="one pinned source PDF"):
        build_pending_research_input(**inputs)


@pytest.mark.parametrize("field,value", [
    ("pdf_sha256", "0" * 64),
    ("source_url", "https://static.cninfo.com.cn/finalpage/unrelated.PDF"),
    ("announcement_id", "unrelated-announcement"),
])
def test_pending_descriptor_rejects_facts_unbound_to_actual_event(field, value):
    inputs = _inputs()
    artifact = json.loads(inputs["facts_file_bytes"])
    artifact["payload"][field] = value
    from value_investment_agent.research_artifacts import canonicalize_artifact_payload, sha256_text
    artifact["payload_sha256"] = sha256_text(
        canonicalize_artifact_payload(artifact["payload"])
    )
    if field in {"pdf_sha256", "source_url"}:
        artifact["evidence_refs"][0][
            "sha256" if field == "pdf_sha256" else "source_url"
        ] = value
    inputs["facts_file_bytes"] = json.dumps(artifact).encode("utf-8")
    with pytest.raises(ValueError, match="not bound to exactly one ACTUAL event"):
        build_pending_research_input(**inputs)


def test_actual_pending_descriptor_cannot_register_valuation_input_node():
    from value_investment_agent.m5_event_dependencies import DependencyGraph, DependencyNode
    from value_investment_agent.m5_research_artifact_graph import attach_valuation_input_descriptor

    inputs = _inputs()
    descriptor = build_pending_research_input(**inputs)
    graph = DependencyGraph((
        DependencyNode(
            node_id="verified-facts", kind="financial_facts", symbol=descriptor.symbol,
            inputs=(), version=hashlib.sha256(inputs["facts_file_bytes"]).hexdigest(),
            evidence_refs=({"id": "pdf"},),
        ),
        DependencyNode(
            node_id="research-case", kind="research_thesis", symbol=descriptor.symbol,
            inputs=(), version="a" * 64, evidence_refs=({"id": "case"},),
        ),
    ))
    with pytest.raises(ValueError, match="incomplete"):
        attach_valuation_input_descriptor(
            graph=graph, descriptor=descriptor, receipt=inputs["receipt"],
            operating_basis_bytes=inputs["equity_file_bytes"],
            assumption_package_bytes=b"{}",
        )
