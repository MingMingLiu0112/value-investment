"""Adapt verified M5 observations to the existing, blocked research input contract."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from .m5_event_run import M5EventRunReceipt
from .research_artifacts import canonicalize_artifact_payload, sha256_text
from .research_case import ResearchCase
from .research_input import ResearchInputDescriptor, finalize_input_descriptor
from .research_profile import PROFILES
from .research_run_contract import (
    INPUT_DESCRIPTOR_SCHEMA, ResearchDependencyFingerprint, ResearchPitFrame,
    ResearchSourceDescriptor,
)
from .valuation_models.residual_income import MODEL_VERSION, QualityCompounderFacts
from .valuation_router import route_profile


def build_pending_research_input(
    *, receipt: M5EventRunReceipt, facts_artifact: Mapping[str, Any],
    facts_file_sha256: str, equity_package: Mapping[str, Any],
    equity_file_sha256: str, name: str, profile_id: str,
    evaluated_at: datetime,
) -> ResearchInputDescriptor:
    if evaluated_at.tzinfo is None or receipt.namespace != "ACTUAL" or receipt.action != "no_order":
        raise ValueError("Pending descriptor requires an ACTUAL no-order receipt and timezone")
    facts = facts_artifact["payload"]
    identity = facts_artifact["identity"]
    if (facts.get("schema_version") != "m5-verified-financial-facts-v1"
        or facts.get("action") != "no_order" or not facts.get("facts")
        or identity.get("artifact_type") != "financial_facts"
        or identity.get("scope_key") != facts.get("symbol")
        or sha256_text(canonicalize_artifact_payload(facts)) != facts_artifact.get("payload_sha256")):
        raise ValueError("Verified financial facts artifact is invalid")
    symbol = facts["symbol"]
    if {event.symbol for event in receipt.active_events} != {symbol}:
        raise ValueError("Receipt events do not match the verified facts")
    period = date.fromisoformat(facts["facts"][0]["report_period_end"])
    if any(item["report_period_end"] != period.isoformat() for item in facts["facts"]):
        raise ValueError("Verified facts contain inconsistent periods")
    published_at = datetime.fromisoformat(facts["published_at"])
    source_available_at = datetime.fromisoformat(facts["available_at"])
    verified_at = datetime.fromisoformat(facts["verified_at"])
    if (identity.get("as_of") != period.isoformat()
        or identity.get("available_at") != facts["available_at"]
        or not published_at <= source_available_at <= verified_at
        or facts_artifact.get("evidence_refs") != [{
            "id": f"pdf:{facts['announcement_id']}",
            "source_url": facts["source_url"], "sha256": facts["pdf_sha256"],
        }]):
        raise ValueError("Verified facts PIT or PDF evidence is not bound")
    basis = equity_package["current_disclosed_basis"]
    if (equity_package.get("symbol") != symbol
        or basis.get("period_end") != period.isoformat()
        or basis.get("source_id") != f"cninfo:{facts['announcement_id']}"
        or basis.get("source_url") != facts["source_url"]
        or basis.get("raw_file_hash") != facts["pdf_sha256"]
        or equity_package.get("valuation_approved") is not False):
        raise ValueError("Archived equity basis is not tied to the verified filing")
    available_at = max(
        verified_at,
        datetime.fromisoformat(basis["assessment_available_at"]),
        receipt.generated_at,
    )
    if evaluated_at < available_at:
        raise ValueError("Pending descriptor cannot precede its source availability")
    if profile_id not in PROFILES:
        raise ValueError("Unknown research profile")
    route = route_profile(profile_id)
    if route.facts_contract is not QualityCompounderFacts:
        raise ValueError("This adapter only accepts the registered quality-compounder facts contract")
    refs = [
        {"id": f"official-pdf:{facts['announcement_id']}", "source_url": facts["source_url"],
         "sha256": facts["pdf_sha256"]},
        {"id": "m5-verified-facts", "sha256": facts_file_sha256},
        {"id": "issuer-equity-basis", "sha256": equity_file_sha256},
        {"id": "m5-actual-receipt", "sha256": receipt.state_sha256},
    ]
    start_book = Decimal(str(basis["parent_equity_cny"]))
    shares = Decimal(str(basis["issued_shares"]))
    if not start_book.is_finite() or not shares.is_finite() or min(start_book, shares) <= 0:
        raise ValueError("Archived equity and shares must be positive finite observations")
    blockers = ("m5_actual_event_research_pending", "scenario_inputs_not_approved")
    facts_input = QualityCompounderFacts(
        symbol=symbol, as_of=period, verified=False, confidence="低",
        evidence_refs=refs, blockers=list(blockers),
        operating_inputs={"start_book_equity": start_book, "ordinary_shares": shares},
        scenario_inputs=None,
    )
    case = ResearchCase(
        symbol=symbol, name=name, as_of=evaluated_at.date(),
        run_id=f"m5-pending-{receipt.receipt_id}", generated_at=evaluated_at,
        research_version="m5-actual-pending-v1", industry=PROFILES[profile_id].industry,
        investment_path=PROFILES[profile_id].investment_path,
        thesis="Event-bound business reassessment is pending.",
        return_driver="Not established for the refreshed event case.",
        mispricing_hypothesis="No refreshed valuation or price conclusion.",
        financial_summary={"period_end": period.isoformat(),
                           "parent_equity_cny": str(start_book), "issued_shares": str(shares)},
        positives=[], counter_evidence=[], thesis_breakers=[], next_events=[],
        evidence_status="partial", valuation_status="not_ready",
        research_status="event_revalidation_pending", blockers=list(blockers),
        evidence_refs=refs, quote_date=None, financial_period=period,
        missing_date_reasons={"quote_date": "No quote is used in this event input preflight."},
    )
    sources = (
        ResearchSourceDescriptor(
            id="official-pdf", kind="filing", location=facts["source_url"],
            sha256=facts["pdf_sha256"],
            published_at=published_at,
        ),
        ResearchSourceDescriptor(
            id="verified-facts", kind="research_artifact", location="m5-verified-facts",
            sha256=facts_file_sha256, retrieved_at=verified_at,
        ),
        ResearchSourceDescriptor(
            id="equity-basis", kind="research_artifact", location="issuer-equity-basis",
            sha256=equity_file_sha256,
            retrieved_at=datetime.fromisoformat(basis["assessment_available_at"]),
        ),
    )
    descriptor = ResearchInputDescriptor(
        schema_version=INPUT_DESCRIPTOR_SCHEMA, descriptor_version="m5-actual-pending-v1",
        symbol=symbol, name=name, profile_id=profile_id, requested_model=route.selected_model,
        run_id=case.run_id,
        point_in_time=ResearchPitFrame(
            report_period=period, research_as_of=case.as_of, valuation_date=period,
            available_at=available_at, computed_at=evaluated_at,
        ),
        dependencies=ResearchDependencyFingerprint(
            rule_version="m5-actual-pending-v1", profile_id=profile_id,
            model_id=route.selected_model, model_version=MODEL_VERSION,
            parser_version="deterministic_archived_pdf_table_context_v1",
        ),
        sources=sources, research_case=case, facts=facts_input, assumptions=None,
        assumption_bindings=(), distribution_result=None, quote=None,
        model_validity_input=None, valuation_approval=None, blockers=blockers,
    )
    return finalize_input_descriptor(descriptor)
