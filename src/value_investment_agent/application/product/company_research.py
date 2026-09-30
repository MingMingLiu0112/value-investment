"""Run the shared company-research application for an explicit symbol."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from ...domain.research.evidence_stop import (
    evaluate_research_schedule,
    evidence_stops_from_payload,
    schedule_request_from_payload,
)
from ...infrastructure.evidence.evidence_stop_schedule import (
    claim_research_schedule_once,
    verified_official_package_source_ids,
)
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
        "issuer_identity_status": outcome.issuer_identity_status,
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


def _verified_source_ids(
    root: Path, package_payload: Mapping[str, Any], request: Any,
) -> frozenset[str]:
    sources = package_payload.get("sources")
    if not isinstance(sources, list):
        return frozenset()
    return verified_official_package_source_ids(
        root, sources, request.new_evidence_ids, symbol=request.symbol,
    )


def _blocked_result(
    *, root: Path, symbol: str, decision: Mapping[str, Any],
    ledger_sha256: str, schedule_request_sha256: str | None,
    output_path: Path | None,
) -> dict[str, Any]:
    payload = {
        "schema_version": "generic-company-research-result-v1",
        "run_id": None,
        "symbol": symbol,
        "status": "BLOCKED_BY_RESEARCH_SCHEDULER",
        "action": ACTION_NO_ORDER,
        "blockers": [str(decision["status"])],
        "schedule_gate": dict(decision),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    target = (
        require_inside(root, output_path, "company research output")
        if output_path is not None else None
    )
    if target is not None:
        write_new_json(target, payload)
    input_hashes = {"evidence_stop_ledger": ledger_sha256}
    if schedule_request_sha256 is not None:
        input_hashes["schedule_request"] = schedule_request_sha256
    return {
        "result": payload,
        "receipt": receipt(
            command="company_research", symbol=symbol,
            input_hashes=input_hashes, output_path=target, output_bytes=None,
        ) | {"output_sha256": sha256_file(target) if target is not None else None},
    }


def run_company_research_for_symbol(
    *,
    root: Path,
    symbol: str,
    package_path: Path | None = None,
    output_path: Path | None = None,
    schedule_request: Mapping[str, Any] | None = None,
    schedule_request_sha256: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    ledger_path = root / "config" / "research-evidence-stop-ledger-v1.json"
    if not ledger_path.is_file():
        raise ValueError("EVIDENCE_STOP_LEDGER_UNAVAILABLE")
    stops = evidence_stops_from_payload(
        load_json_object(ledger_path, "evidence-stop ledger")
    )
    request = (
        None if schedule_request is None
        else schedule_request_from_payload(schedule_request)
    )
    active_stops = tuple(stop for stop in stops if stop.symbol == normalized)
    if not active_stops:
        decision = evaluate_research_schedule(
            symbol=normalized, stops=stops, request=request,
        )
        if not decision["allowed"]:
            return _blocked_result(
                root=root, symbol=normalized, decision=decision,
                ledger_sha256=sha256_file(ledger_path),
                schedule_request_sha256=schedule_request_sha256,
                output_path=output_path,
            )
    if active_stops and request is None:
        decision = evaluate_research_schedule(
            symbol=normalized, stops=stops, request=None,
        )
        return _blocked_result(
            root=root, symbol=normalized, decision=decision,
            ledger_sha256=sha256_file(ledger_path),
            schedule_request_sha256=schedule_request_sha256,
            output_path=output_path,
        )

    package = _package_for_symbol(root, normalized, package_path)
    package_payload = load_json_object(package, "valuation package")
    verified_ids = (
        _verified_source_ids(root, package_payload, request)
        if request is not None else frozenset()
    )
    decision = evaluate_research_schedule(
        symbol=normalized, stops=stops, request=request,
        verified_evidence_ids=verified_ids,
    )
    if not decision["allowed"]:
        return _blocked_result(
            root=root, symbol=normalized, decision=decision,
            ledger_sha256=sha256_file(ledger_path),
            schedule_request_sha256=schedule_request_sha256,
            output_path=output_path,
        )
    consumption = None
    if active_stops:
        consumption = claim_research_schedule_once(
            root=root,
            request=request,
            decision=decision,
            ledger_sha256=sha256_file(ledger_path),
            request_sha256=schedule_request_sha256,
        )
        if not consumption["created"]:
            blocked_decision = {
                **decision,
                "allowed": False,
                "status": "BLOCKED_EVIDENCE_ALREADY_CONSUMED",
                "consumption_schedule_id": consumption["schedule_id"],
            }
            return _blocked_result(
                root=root, symbol=normalized, decision=blocked_decision,
                ledger_sha256=sha256_file(ledger_path),
                schedule_request_sha256=schedule_request_sha256,
                output_path=output_path,
            )
    descriptor = build_descriptor(package_payload, root=root)
    outcome = ResearchApplicationService(InMemoryResearchArtifactRepository()).run_company_research(
        build_research_run_spec(descriptor)
    )
    payload = _serialize_outcome(outcome)
    payload["schedule_gate"] = decision
    if consumption is not None:
        payload["schedule_consumption"] = consumption
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
            input_hashes={
                "valuation_package": sha256_file(package),
                "evidence_stop_ledger": sha256_file(ledger_path),
                **({"schedule_request": schedule_request_sha256}
                   if schedule_request_sha256 is not None else {}),
            },
            output_path=target,
            output_bytes=None,
        )
        | {"output_sha256": output_hash},
    }
