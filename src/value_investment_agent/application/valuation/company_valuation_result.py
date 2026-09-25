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
    facts = FinancialFacts(
        symbol=symbol,
        as_of=date.fromisoformat(audit["as_of_period"]),
        verified=audit["financial_scope_approved"] is True,
        evidence_refs=[_reference(root, "financial_scope", facts_path)],
        blockers=list(audit.get("per_share_blockers", [])),
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
