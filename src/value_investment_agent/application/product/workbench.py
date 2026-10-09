"""Build a symbol-neutral current-workbench request from shared research output."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .common import (
    ACTION_NO_ORDER,
    normalize_symbol,
    receipt,
    require_inside,
    sha256_file,
    write_new_json,
)
from .company_research import run_company_research_for_symbol
from ..decision.artifact_bundle import ReadOnlyArtifactBundleRepository
from ..decision.restore_decision_recommendation import verify_decision_recommendation_payload
from .existing_valuation import read_existing_research_result
from .common import load_json_object


def load_existing_workbench_for_presentation(
    *, root: Path, path: Path, expected_sha256: str,
) -> dict[str, Any]:
    """Recheck result and original bytes at the presentation boundary."""
    path = require_inside(root, path, "existing workbench")
    if sha256_file(path) != expected_sha256:
        raise ValueError("existing workbench hash mismatch")
    payload = load_json_object(path, "existing workbench")
    if (payload.get("schema_version") != "product-existing-research-workbench-v1"
            or payload.get("action") != ACTION_NO_ORDER
            or payload.get("suggested_state") != "NOT_READY"
            or payload.get("position_guidance") is not None):
        raise ValueError("existing workbench presentation scope mismatch")
    records = payload["research"]["source_records"]
    if not records:
        raise ValueError("existing workbench requires original evidence")
    for record in records:
        original = require_inside(root, root / record["path"], "workbench original")
        if sha256_file(original) != record["sha256"]:
            raise ValueError("workbench original hash mismatch")
    return payload


def build_current_workbench_for_symbol(
    *,
    root: Path,
    symbol: str,
    package_path: Path | None = None,
    output_path: Path,
    existing_manifest_path: Path | None = None,
    existing_manifest_sha256: str | None = None,
    arithmetic_input_path: Path | None = None,
    arithmetic_input_sha256: str | None = None,
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
    target = require_inside(root, output_path, "current workbench output")
    if existing_manifest_path is not None or existing_manifest_sha256 is not None:
        if existing_manifest_path is None or existing_manifest_sha256 is None or package_path is not None:
            raise ValueError("existing workbench requires manifest and hash and excludes package")
        if any(value is not None for value in (
            schedule_request, schedule_request_sha256, quote_path, quote_sha256,
            event_path, event_sha256, reviews_path, reviews_sha256,
            recommendation_schema_version,
        )):
            raise ValueError(
                "existing workbench excludes schedule/market/review/schema inputs"
            )
        existing = read_existing_research_result(
            root=root, symbol=normalized, manifest_path=existing_manifest_path,
            manifest_sha256=existing_manifest_sha256,
            arithmetic_input_path=arithmetic_input_path,
            arithmetic_input_sha256=arithmetic_input_sha256,
        )
        payload = {
            "schema_version": "product-existing-research-workbench-v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "symbol": normalized, "action": ACTION_NO_ORDER,
            "scope": "EXISTING_RESEARCH_ONLY_NOT_CURRENT_ADVICE",
            "research": existing,
            "suggested_state": "NOT_READY", "position_guidance": None,
            "canonical_workbook_written": False,
        }
        write_new_json(target, payload)
        return {"result": payload, "receipt": {
            "command": "current_workbench", "symbol": normalized,
            "input_sha256": {"existing_manifest": existing_manifest_sha256,
                             "arithmetic_input": arithmetic_input_sha256},
            "output_path": str(target.relative_to(root.resolve())),
            "output_sha256": sha256_file(target), "action": ACTION_NO_ORDER,
        }}
    if arithmetic_input_path is not None or arithmetic_input_sha256 is not None:
        raise ValueError("arithmetic input requires existing-result mode")
    research = run_company_research_for_symbol(
        root=root,
        symbol=normalized,
        package_path=package_path,
        output_path=None,
        schedule_request=schedule_request,
        schedule_request_sha256=schedule_request_sha256,
        quote_path=quote_path,
        quote_sha256=quote_sha256,
        event_path=event_path,
        event_sha256=event_sha256,
        reviews_path=reviews_path,
        reviews_sha256=reviews_sha256,
        recommendation_schema_version=recommendation_schema_version,
    )
    outcome = research["result"]
    stopped = outcome["status"] == "BLOCKED_BY_RESEARCH_SCHEDULER"
    if not stopped:
        bundle = outcome.get("artifact_bundle")
        recommendation = outcome.get("decision_recommendation")
        if not isinstance(bundle, dict) or not isinstance(recommendation, dict):
            raise ValueError("Current workbench requires replayable decision artifacts")
        repository = ReadOnlyArtifactBundleRepository(bundle)
        verify_decision_recommendation_payload(
            repository, payload=recommendation,
            recommendation_artifact=repository.recommendation_artifact(recommendation),
        )
    evidence_stops = []
    if stopped:
        ledger = root / "config" / "research-evidence-stop-ledger-v1.json"
        expected = research["receipt"]["input_sha256"]["evidence_stop_ledger"]
        if sha256_file(ledger) != expected:
            raise ValueError("evidence-stop ledger changed during workbench read")
        evidence_stops = [item for item in load_json_object(ledger, "evidence-stop ledger")["stops"]
                          if item["symbol"] == normalized]
        if sha256_file(ledger) != expected:
            raise ValueError("evidence-stop ledger changed during workbench read")
    payload = {
        "schema_version": "product-current-workbench-request-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "command": "current_workbench",
        "symbol": normalized,
        "action": ACTION_NO_ORDER,
        "research_status": outcome["status"],
        "research_blockers": outcome["blockers"],
        "current_status": None if stopped else outcome["current_status"],
        "valuation": None if stopped else outcome["valuation"],
        "price_bridge": None if stopped else outcome["price_bridge"],
        "price_attractiveness": None if stopped else outcome.get("price_attractiveness"),
        "pre_decision_eligibility": None if stopped else outcome.get("pre_decision_eligibility"),
        "decision_recommendation": None if stopped else outcome.get("decision_recommendation"),
        "artifact_bundle": None if stopped else outcome["artifact_bundle"],
        "portfolio_input_status": "BLOCKED_PRIVATE_INPUT",
        "schedule_gate": outcome.get("schedule_gate"),
        "evidence_stops": evidence_stops,
        "suggested_state": (
            "NOT_READY" if stopped else
            (outcome.get("decision_recommendation") or {}).get("recommendation_type", "NOT_READY")
        ),
        "position_guidance": None,
        "canonical_workbook_written": False,
        "requires_product_renderer": True,
        "research_receipt": research["receipt"],
        "source_verification": None if stopped else outcome.get("source_verification"),
        "input_descriptor_sha256": None if stopped else outcome.get("input_descriptor_sha256"),
    }
    write_new_json(target, payload)
    return {
        "result": payload,
        "receipt": receipt(
            command="current_workbench",
            symbol=normalized,
            input_hashes=research["receipt"]["input_sha256"],
            output_path=target,
            output_bytes=None,
        )
        | {"output_sha256": sha256_file(target)},
    }


def load_stopped_workbench_for_presentation(*, root: Path, path: Path, expected_sha256: str) -> dict[str, Any]:
    """Recheck the stopped result against the current source ledger, without research."""
    path = require_inside(root, path, "stopped workbench")
    if sha256_file(path) != expected_sha256:
        raise ValueError("stopped workbench hash mismatch")
    payload = load_json_object(path, "stopped workbench")
    if (payload.get("schema_version") != "product-current-workbench-request-v1"
            or payload.get("action") != ACTION_NO_ORDER
            or payload.get("research_status") != "BLOCKED_BY_RESEARCH_SCHEDULER"
            or payload.get("suggested_state") != "NOT_READY"
            or payload.get("position_guidance") is not None
            or payload.get("canonical_workbook_written") is not False
            or any(payload.get(key) is not None for key in ("valuation", "price_bridge", "current_status"))):
        raise ValueError("stopped workbench scope mismatch")
    symbol = normalize_symbol(payload["symbol"])
    gate = payload.get("schedule_gate")
    if not isinstance(gate, dict) or gate.get("allowed") is not False:
        raise ValueError("stopped workbench requires denied schedule gate")
    ledger = root / "config/research-evidence-stop-ledger-v1.json"
    expected = payload["research_receipt"]["input_sha256"]["evidence_stop_ledger"]
    if sha256_file(ledger) != expected:
        raise ValueError("stopped workbench ledger hash mismatch")
    registered = [stop for stop in load_json_object(ledger, "evidence-stop ledger")["stops"]
                  if stop["symbol"] == symbol]
    if not registered or registered != payload.get("evidence_stops"):
        raise ValueError("stopped workbench questions differ from ledger")
    if sha256_file(ledger) != expected or sha256_file(path) != expected_sha256:
        raise ValueError("stopped workbench source changed during read")
    return {"result": payload, "observed_at": datetime.now(timezone.utc).isoformat(),
            "source_bindings": [{"path": str(path.relative_to(root.resolve())), "sha256": expected_sha256},
                                {"path": str(ledger.relative_to(root.resolve())), "sha256": expected}]}
