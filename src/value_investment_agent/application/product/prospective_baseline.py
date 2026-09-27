"""Build append-only public baseline cards for prospective research cases."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from .common import load_json_object, require_inside, sha256_file, write_new_json


def _time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def build_prospective_baselines(*, root: Path, input_path: Path, output_path: Path) -> dict[str, Any]:
    source = require_inside(root, input_path, "prospective baseline input")
    target = require_inside(root, output_path, "prospective baseline output")
    if not target.is_relative_to((root / "runtime").resolve()):
        raise ValueError("prospective baseline output must remain under runtime")
    payload = load_json_object(source, "prospective baseline input")
    if payload.get("schema_version") != "prospective-baseline-input-v1" or payload.get("action") != "no_order":
        raise ValueError("prospective baseline input must be v1 and action=no_order")
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 3:
        raise ValueError("prospective baseline input must contain exactly three cases")
    now = datetime.now(timezone.utc)
    cards: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, Mapping):
            raise ValueError("baseline case must be an object")
        cutoff = _time(case.get("baseline_cutoff_at"), "baseline_cutoff_at")
        facts = case.get("known_facts", [])
        if not isinstance(facts, list):
            raise ValueError("known_facts must be a list")
        for fact in facts:
            if not isinstance(fact, Mapping):
                raise ValueError("known fact must be an object")
            available = _time(fact.get("available_at"), "fact.available_at")
            if available > cutoff:
                raise ValueError("future fact cannot enter baseline")
            required = ("fact_id", "source_url", "source_document_id", "source_sha256", "fact_type")
            if any(not isinstance(fact.get(field), str) or not fact[field].strip() for field in required):
                raise ValueError("known fact provenance is incomplete")
            ledger.append({
                "case_id": case["case_id"], "symbol": case["symbol"],
                "observation_id": f"baseline:{fact['fact_id']}",
                "observed_at": now.isoformat(), "source_available_at": available.isoformat(),
                "source_document_id": fact["source_document_id"], "source_sha256": fact["source_sha256"],
                "fact_type": fact["fact_type"], "dependency_nodes": fact.get("dependency_nodes", []),
                "classification": "BASELINE_FACT",
            })
        cards.append({
            "case_id": case["case_id"], "symbol": case["symbol"], "company": case["company"],
            "profile": case["profile"], "model_applicability": case["model_applicability"],
            "business_quality": case["business_quality"], "financial_quality": case["financial_quality"],
            "capital_allocation": case["capital_allocation"], "return_drivers": case["return_drivers"],
            "mispricing_hypothesis": case["mispricing_hypothesis"], "dividend_sustainability": case["dividend_sustainability"],
            "strongest_counterevidence": case["strongest_counterevidence"], "thesis_breakers": case["thesis_breakers"],
            "known_facts": facts, "unknowns": case["unknowns"], "next_evidence_trigger": case["next_evidence_trigger"],
            "research_status": case["research_status"], "valuation_status": case["valuation_status"], "action": "no_order",
        })
    result = {"schema_version": "prospective-baseline-snapshot-v1", "built_at": now.isoformat(), "action": "no_order", "cards": cards, "observation_ledger": ledger}
    write_new_json(target, result)
    return result | {"output_path": str(target), "output_sha256": sha256_file(target), "input_sha256": sha256_file(source)}


__all__ = ["build_prospective_baselines"]
