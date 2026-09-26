"""Run the shared company-research application for an explicit symbol."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from ...m1_valuation_package_builder import build_descriptor
from ...research_application import ResearchApplicationService
from ...research_artifact_repository import InMemoryResearchArtifactRepository
from ...research_input import build_research_run_spec
from .common import (
    ACTION_NO_ORDER,
    load_json_object,
    normalize_symbol,
    receipt,
    require_inside,
    sha256_file,
    write_new_json,
)


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "to_json"):
        return json.loads(value.to_json())
    if hasattr(value, "as_policy"):
        return value.as_policy()
    return value


def _package_for_symbol(root: Path, symbol: str, package_path: Path | None) -> Path:
    if package_path is not None:
        path = require_inside(root, package_path, "valuation package")
        payload = load_json_object(path, "valuation package")
        if payload.get("symbol") != symbol:
            raise ValueError("valuation package symbol does not match the requested symbol")
        return path
    matches = []
    package_dir = root / "config" / "m1-valuation-packages-v1"
    for path in sorted(package_dir.glob("*.json")):
        payload = load_json_object(path, "valuation package")
        if payload.get("symbol") == symbol:
            matches.append(path)
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one valuation package for symbol {symbol}, found {len(matches)}"
        )
    return matches[0]


def _serialize_outcome(outcome: Any) -> dict[str, Any]:
    return {
        "schema_version": "generic-company-research-result-v1",
        "run_id": outcome.run_id,
        "symbol": outcome.symbol,
        "profile_id": outcome.profile_id,
        "status": outcome.status,
        "action": ACTION_NO_ORDER,
        "as_of": outcome.as_of.isoformat(),
        "available_at": outcome.available_at.isoformat(),
        "blockers": list(outcome.blockers),
        "route": _json_value(outcome.route),
        "gate": asdict(outcome.gate) if outcome.gate is not None else None,
        "valuation": _json_value(outcome.valuation),
        "assumptions": _json_value(outcome.assumptions),
        "model_validity": _json_value(outcome.model_validity),
        "quote_snapshot": _json_value(outcome.quote_snapshot),
        "price_bridge": _json_value(outcome.price_bridge),
        "price_attractiveness": _json_value(outcome.price_attractiveness),
        "distribution_result": _json_value(outcome.distribution_result),
        "current_status": _json_value(outcome.current_status),
        "human_research_approval": _json_value(outcome.human_research_approval),
        "event_materiality_review": _json_value(outcome.event_materiality_review),
        "pre_decision_eligibility": _json_value(outcome.pre_decision_eligibility),
    }


def run_company_research_for_symbol(
    *,
    root: Path,
    symbol: str,
    package_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    package = _package_for_symbol(root, normalized, package_path)
    descriptor = build_descriptor(load_json_object(package, "valuation package"), root=root)
    outcome = ResearchApplicationService(InMemoryResearchArtifactRepository()).run_company_research(
        build_research_run_spec(descriptor)
    )
    payload = _serialize_outcome(outcome)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    target = (
        require_inside(root, output_path, "company research output")
        if output_path is not None
        else None
    )
    if target is not None:
        write_new_json(target, payload)
        output_hash = sha256_file(target)
    else:
        output_hash = None
    return {
        "result": payload,
        "receipt": receipt(
            command="company_research",
            symbol=normalized,
            input_hashes={"valuation_package": sha256_file(package)},
            output_path=target,
            output_bytes=None,
        )
        | {"output_sha256": output_hash},
    }
