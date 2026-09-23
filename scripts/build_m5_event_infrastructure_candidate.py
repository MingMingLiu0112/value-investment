"""Build a standalone simulated M5 event infrastructure Excel candidate."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

from value_investment_agent.investment_decision import ACTION_NO_ORDER
from value_investment_agent.m5_event_core import (
    EVENT_STATUS_ACTIVE,
    INGEST_ACCEPTED,
    INGEST_CORRECTION_ACCEPTED,
    INGEST_DUPLICATE,
    INGEST_SUPERSEDES_ACCEPTED,
    NAMESPACE_SIMULATED,
    ChangeEventInput,
    EventLedger,
)
from value_investment_agent.m5_event_dependencies import (
    dependency_graph_from_payload,
)
from value_investment_agent.m5_event_run import run_event_batch
from value_investment_agent.m5_event_watermark import ScanWatermark
from value_investment_agent.m5_event_workbook import (
    write_m5_event_workbook,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "tests" / "fixtures" / "m5_event_infrastructure_demo.json"
SCHEMA_VERSION = "m5-event-demo-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "A股价值投资_M5事件监控候选_20260924.xlsx",
    )
    return parser.parse_args()


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def _event_from_payload(payload: dict) -> ChangeEventInput:
    return ChangeEventInput(
        source_event_id=str(payload["source_event_id"]),
        symbol=str(payload["symbol"]),
        event_type=str(payload["event_type"]),
        detected_at=_datetime(payload["detected_at"], "detected_at"),
        available_at=_datetime(payload["available_at"], "available_at"),
        effective_at=_datetime(payload["effective_at"], "effective_at")
        if payload.get("effective_at")
        else None,
        previous_state=dict(payload.get("previous_state") or {}),
        current_state=dict(payload.get("current_state") or {}),
        severity=str(payload["severity"]),
        reason=str(payload["reason"]),
        evidence_refs=tuple(dict(item) for item in payload.get("evidence_refs") or ()),
        confidence=str(payload["confidence"]),
        requires_human_review=bool(payload["requires_human_review"]),
        namespace=NAMESPACE_SIMULATED,
    )


def load_input(path: Path) -> tuple[dict, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("M5 event input must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unknown M5 event input schema")
    if payload.get("action") != ACTION_NO_ORDER:
        raise ValueError("M5 event input must remain no_order")
    if payload.get("namespace") != NAMESPACE_SIMULATED:
        raise ValueError("Public M5 event candidate must be simulated")
    return payload, {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def prepare_event_batch(
    payload: dict,
) -> tuple[tuple[ChangeEventInput, ...], tuple[datetime, ...]]:
    observed_times = tuple(
        _datetime(item, "observed_at")
        for item in payload.get("observed_times") or ()
    )
    raw_events = payload.get("events") or ()
    if len(raw_events) != len(observed_times):
        raise ValueError("Event and observed_at counts differ")

    resolver = EventLedger(namespace=NAMESPACE_SIMULATED)
    prepared: list[ChangeEventInput] = []
    for raw, observed_at in zip(raw_events, observed_times):
        item = dict(raw)
        correction_source = item.pop("correction_of_source_event_id", None)
        event = _event_from_payload(item)
        if correction_source:
            target = resolver.latest_for(
                symbol=event.symbol,
                source_event_id=str(correction_source),
            )
            if target is None or target.status != EVENT_STATUS_ACTIVE:
                raise ValueError(
                    f"Correction target is unavailable: {correction_source}"
                )
            event = ChangeEventInput(
                source_event_id=event.source_event_id,
                symbol=event.symbol,
                event_type=event.event_type,
                detected_at=event.detected_at,
                available_at=event.available_at,
                effective_at=event.effective_at,
                previous_state=event.previous_state,
                current_state=event.current_state,
                severity=event.severity,
                reason=event.reason,
                evidence_refs=event.evidence_refs,
                confidence=event.confidence,
                requires_human_review=event.requires_human_review,
                correction_of_event_id=target.event_id,
                namespace=NAMESPACE_SIMULATED,
            )
        else:
            result = resolver.append(event, observed_at=observed_at)
            if result.status not in {
                INGEST_ACCEPTED,
                INGEST_CORRECTION_ACCEPTED,
                INGEST_SUPERSEDES_ACCEPTED,
                INGEST_DUPLICATE,
            }:
                raise ValueError(
                    f"Fixture event failed resolver preflight: {result.status}"
                )
        prepared.append(event)
    return tuple(prepared), observed_times


def build_models(payload: dict):
    watermark_payload = dict(payload["watermark"])
    watermark = ScanWatermark(
        watermark_id=str(watermark_payload["watermark_id"]),
        scope=str(watermark_payload["scope"]),
        source=str(watermark_payload["source"]),
        coverage_through=_datetime(
            watermark_payload["coverage_through"],
            "coverage_through",
        ),
        retrieved_at=_datetime(watermark_payload["retrieved_at"], "retrieved_at"),
        parser_version=str(watermark_payload["parser_version"]),
        coverage_status=str(watermark_payload["coverage_status"]),
        source_health=str(watermark_payload["source_health"]),
        evidence_refs=tuple(
            dict(item) for item in watermark_payload.get("evidence_refs") or ()
        ),
    )
    graph = dependency_graph_from_payload(payload["graph"])
    events, observed_times = prepare_event_batch(payload)
    generated_at = _datetime(payload["generated_at"], "generated_at")
    receipt = run_event_batch(
        events=events,
        observed_times=observed_times,
        watermark=watermark,
        graph=graph,
        run_id=str(payload["run_id"]),
        generated_at=generated_at,
    )
    return receipt, watermark


def main() -> int:
    args = parse_args()
    payload, input_receipt = load_input(args.input.resolve())
    receipt, watermark = build_models(payload)
    result = write_m5_event_workbook(
        receipt,
        watermark,
        output=args.output,
        root=args.output.resolve().parent,
        security_names=payload.get("security_names"),
    )
    manifest = {
        **result,
        "schema_version": SCHEMA_VERSION,
        "run_id": receipt.run_id,
        "generated_at": receipt.generated_at.isoformat(),
        "input": input_receipt,
        "health_status": receipt.health_status,
        "silent_ok": receipt.silent_ok,
        "review_due": list(receipt.review_due),
    }
    args.output.resolve().with_suffix(".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
