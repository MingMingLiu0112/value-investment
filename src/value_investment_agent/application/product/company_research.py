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
from .research_reviews import attach_research_reviews
from .source_bound_inputs import SOURCE_BOUND_PACKAGE_SCHEMA, verify_package_local_sources


class ResearchInputValidationError(ValueError):
    """Known descriptor rejection before any one-shot request consumption."""


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
    from ..decision.artifact_bundle import export_artifact_bundle

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
        "decision_recommendation": _json_value(outcome.decision_recommendation),
        "artifact_bundle": export_artifact_bundle(outcome.stored_artifacts),
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
    quote_path: Path | None = None,
    quote_sha256: str | None = None,
    event_path: Path | None = None,
    event_sha256: str | None = None,
    reviews_path: Path | None = None,
    reviews_sha256: str | None = None,
    recommendation_schema_version: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    explicit_inputs = {}
    for role, path, digest in (
        ('quote', quote_path, quote_sha256), ('event', event_path, event_sha256),
        ('research_reviews', reviews_path, reviews_sha256),
    ):
        if bool(path) != bool(digest):
            raise ValueError(f'{role} requires paired path/hash')
        if path is not None:
            if package_path is None:
                raise ValueError('explicit market inputs require an explicit research package')
            source = require_inside(root, path, role)
            if sha256_file(source) != digest:
                raise ValueError(f'{role} input hash mismatch')
            explicit_inputs[role] = (source, digest)
    ledger_path = root / "config" / "research-evidence-stop-ledger-v1.json"
    if not ledger_path.is_file():
        raise ValueError("EVIDENCE_STOP_LEDGER_UNAVAILABLE")
    ledger_sha256 = sha256_file(ledger_path)
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
    package_sha256 = sha256_file(package)
    package_payload = load_json_object(package, "valuation package")
    local_source_bindings = verify_package_local_sources(root, package_payload)
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
    # Validate all calculation inputs before consuming a one-shot reopen request.
    effective_package = dict(package_payload)
    if recommendation_schema_version is not None:
        effective_package['recommendation_schema_version'] = recommendation_schema_version
    if 'quote' in explicit_inputs:
        path, digest = explicit_inputs['quote']
        effective_package['quote'] = dict(kind='quote_session', symbol=normalized,
            ref_id='daily-quote-' + digest, bundle_path=path.relative_to(root).as_posix(),
            bundle_sha256=digest)
    if 'event' in explicit_inputs:
        path, digest = explicit_inputs['event']
        validity = package_payload.get('model_validity_input')
        if not isinstance(validity, Mapping):
            raise ValueError('explicit event requires declared model validity input')
        ref = dict(id='daily-event-' + digest, symbol=normalized,
            path=path.relative_to(root).as_posix(), sha256=digest)
        effective_package['model_validity_input'] = dict(validity,
            event_scan_ref=ref, event_scan_evidence_refs=[ref])
    try:
        descriptor = build_descriptor(effective_package, root=root)
        spec = build_research_run_spec(descriptor)
        if reviews_path is not None:
            scan_ref = (effective_package.get('model_validity_input') or {}).get('event_scan_ref') or {}
            spec = attach_research_reviews(root=root, spec=spec, descriptor=descriptor,
                path=explicit_inputs['research_reviews'][0], expected_sha256=reviews_sha256,
                event_sha256=event_sha256 or scan_ref.get('sha256'),
                require_model_binding=(effective_package.get('schema_version') == SOURCE_BOUND_PACKAGE_SCHEMA))
    except (ValueError, FileNotFoundError) as error:
        raise ResearchInputValidationError(str(error)) from error
    for path, digest in explicit_inputs.values():
        if sha256_file(path) != digest:
            raise ValueError('explicit research input changed during validation')
    def verify_consumed_inputs():
        if sha256_file(package) != package_sha256 or sha256_file(ledger_path) != ledger_sha256:
            raise ValueError('research package or evidence-stop ledger changed during execution')
        for path, digest in explicit_inputs.values():
            if sha256_file(path) != digest:
                raise ValueError('explicit research input changed during execution')
        for path, digest in local_source_bindings:
            if sha256_file(path) != digest:
                raise ValueError('source-bound package source changed during execution')

    verify_consumed_inputs()
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
    outcome = ResearchApplicationService(InMemoryResearchArtifactRepository()).run_company_research(
        spec
    )
    verify_consumed_inputs()
    payload = _serialize_outcome(outcome)
    payload['source_verification'] = {
        'status': 'LOCAL_BYTES_VERIFIED' if local_source_bindings else 'NO_LOCAL_BINDING_METADATA',
        'scope': 'byte_integrity_not_fact_semantics_or_investment_approval',
        'source_contract_status': (
            'SOURCE_CUTOFF_AND_SCENARIO_BINDINGS_VALIDATED'
            if package_payload.get('schema_version') == 'm1-valuation-package-v2'
            else 'LEGACY_CONTRACT_NOT_REAL_INPUT_ADMISSION'
        ),
        'sources': [dict(path=path.relative_to(root.resolve()).as_posix(), sha256=digest)
                    for path, digest in local_source_bindings],
    }
    payload['input_descriptor_sha256'] = spec.input_descriptor_sha256
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
                "valuation_package": package_sha256,
                "evidence_stop_ledger": ledger_sha256,
                **{role: digest for role, (_, digest) in explicit_inputs.items()},
                **({"schedule_request": schedule_request_sha256}
                   if schedule_request_sha256 is not None else {}),
            },
            output_path=target,
            output_bytes=None,
        )
        | {"output_sha256": output_hash},
    }
