"""Build one research-only valuation result through an explicit model."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any

from ...domain.research.research_case import ResearchCase
from ...domain.research.research_profile import PROFILES
from ...domain.research.research_run_contract import (
    ResearchIssuerIdentity,
    ResearchSourceDescriptor,
)
from ...domain.research.issuer_identity import (
    ISSUER_IDENTITY_NOT_READY,
    ISSUER_IDENTITY_REJECTED,
    assess_issuer_identity,
    event_evidence_refs_from_case,
)
from ...price_bridge import pending_price_bridge_for_incomplete_valuation
from ...valuation_models.fcff import FCFFValuationModel, FinancialFacts
from ...valuation_router import ROUTE_SUPPORTED, ValuationRouter


def _reference(root: Path, ref_id: str, path: Path) -> dict[str, str]:
    return {
        "id": ref_id,
        "path": str(path.relative_to(root)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _case(payload: dict[str, Any], symbol: str) -> ResearchCase:
    for record in payload["records"]:
        if record["case"]["symbol"] == symbol:
            raw = record["case"].copy()
            for key in ("as_of", "quote_date", "financial_period"):
                if raw.get(key):
                    raw[key] = date.fromisoformat(raw[key])
            raw["generated_at"] = datetime.fromisoformat(raw["generated_at"])
            return ResearchCase(**raw)
    raise ValueError(f"ResearchCase not found: {symbol}")


def _fact_sources(audit: dict[str, Any]) -> tuple[ResearchSourceDescriptor, ...]:
    sources = []
    refs = audit.get("evidence_refs")
    if not isinstance(refs, list):
        return ()
    for raw in refs:
        if not isinstance(raw, dict):
            continue
        ref_id = raw.get("id")
        digest = raw.get("sha256")
        location = raw.get("source_url") or raw.get("path") or raw.get("location")
        if not all(isinstance(value, str) and value.strip() for value in (ref_id, digest, location)):
            continue
        raw_identity = raw.get("issuer_identity")
        identity = None
        if isinstance(raw_identity, dict) and isinstance(raw_identity.get("venue"), str):
            identity = ResearchIssuerIdentity(
                venue=raw_identity["venue"],
                security_code=(
                    str(raw_identity["security_code"])
                    if raw_identity.get("security_code") is not None else None
                ),
                issuer_name=(
                    str(raw_identity["issuer_name"])
                    if raw_identity.get("issuer_name") is not None else None
                ),
                organization_id=(
                    str(raw_identity["organization_id"])
                    if raw_identity.get("organization_id") is not None else None
                ),
            )
        try:
            sources.append(ResearchSourceDescriptor(
                id=ref_id,
                kind=str(raw.get("kind") or "financial_fact_evidence"),
                location=location,
                sha256=digest.lower(),
                issuer_identity=identity,
            ))
        except (TypeError, ValueError):
            continue
    return tuple(sources)


def build_company_valuation_result(
    *,
    root: Path,
    symbol: str,
    case_path: Path,
    facts_path: Path,
    model: str,
    profile_id: str | None = None,
    applicability_path: Path | None = None,
) -> dict[str, Any]:
    """Preserve the current explicit FCFF-only behavior for existing callers."""

    root = root.resolve()
    if model != "fcff":
        raise ValueError("Only the explicitly selected fcff model is supported")
    route = None
    if profile_id is not None:
        if profile_id not in PROFILES:
            raise ValueError(f"Unknown research profile: {profile_id}")
        route = ValuationRouter().route(PROFILES[profile_id], model)
        if route.status != ROUTE_SUPPORTED or route.model_type != "FCFF":
            raise ValueError(
                f"Profile {profile_id} does not support the selected FCFF model"
            )
    case = _case(json.loads(case_path.read_text(encoding="utf-8")), symbol)
    audit = json.loads(facts_path.read_text(encoding="utf-8"))
    facts_payload_symbol = audit.get("symbol")
    source_descriptors = (
        *_fact_sources(audit),
        *_fact_sources({"evidence_refs": case.evidence_refs}),
    )
    identity = assess_issuer_identity(
        symbol=symbol,
        facts_symbol=(
            facts_payload_symbol
            if isinstance(facts_payload_symbol, str) else None
        ),
        research_case_symbol=case.symbol,
        fact_evidence_refs=(
            audit.get("evidence_refs")
            if isinstance(audit.get("evidence_refs"), list) else []
        ),
        sources=source_descriptors,
        event_evidence_refs=event_evidence_refs_from_case(case),
    )
    identity_status = identity.status
    identity_blockers = identity.blockers
    facts = FinancialFacts(
        symbol=symbol,
        as_of=date.fromisoformat(audit["as_of_period"]),
        verified=(audit.get("financial_scope_approved") is True
                  and identity_status not in {ISSUER_IDENTITY_NOT_READY, ISSUER_IDENTITY_REJECTED}),
        evidence_refs=[
            _reference(root, "financial_scope", facts_path),
            *(
                [dict(ref) for ref in audit["evidence_refs"] if isinstance(ref, dict)]
                if isinstance(audit.get("evidence_refs"), list) else []
            ),
        ],
        blockers=list(dict.fromkeys([
            *audit.get("per_share_blockers", []),
            *identity_blockers,
        ])),
        operating_inputs={
            key: (None if value is None else Decimal(str(value)))
            for key, value in audit.get("fcff_inputs", {}).items()
        },
    )
    result = FCFFValuationModel().value(facts, case)
    price_bridge = pending_price_bridge_for_incomplete_valuation(
        result,
        evidence_refs=list(result.evidence_refs),
    )
    payload: dict[str, Any] = {
        "version": "unified-company-valuation-result-v1",
        "model": model,
        "result": json.loads(result.to_json()),
        "price_bridge": json.loads(price_bridge.to_json()),
        "research_case_ref": _reference(root, "excel_mvp_research_cases", case_path),
        "formal_fair_value": None,
        "trade_approved": False,
        "live_eligible": False,
        "action": "no_order",
        "facts_payload_symbol": facts_payload_symbol,
        "issuer_identity_status": identity_status,
        "issuer_identity_blockers": list(identity_blockers),
    }
    if route is not None:
        payload["valuation_route"] = route.as_policy()
    if applicability_path is not None:
        if route is None:
            raise ValueError(
                "Applicability evidence requires an explicit --profile-id"
            )
        applicability = json.loads(applicability_path.read_text(encoding="utf-8"))
        if (
            applicability.get("symbol") != symbol
            or applicability.get("profile_route", {}).get("profile_id")
            != route.profile_id
            or applicability.get("profile_route", {}).get("model_type")
            != route.model_type
        ):
            raise ValueError(
                "Valuation applicability does not match the selected profile route"
            )
        payload["valuation_applicability"] = {
            "path": str(applicability_path.relative_to(root)),
            "sha256": hashlib.sha256(applicability_path.read_bytes()).hexdigest(),
            "policy": applicability,
        }
    return payload
