"""Apply one reconciled ACTUAL M5 batch to local append-only receipts.

This command is deliberately not an operational runner.  It validates that a
user-confirmed review remains byte-identical after a later complete CNINFO
scan, then writes only local JSON state and receipt artifacts.  It never
starts a scheduler, sends a notification, writes PostgreSQL, or places orders.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.investment_decision import ACTION_NO_ORDER  # noqa: E402
from value_investment_agent.m5_actual_offline_authorization import (  # noqa: E402
    M5ActualOfflineAuthorization,
    USER_CONFIRMED_DELEGATED_REVIEW,
    graph_sha256,
)
from value_investment_agent.m5_disclosure_queue import (  # noqa: E402
    disclosure_review_queue_from_payload,
)
from value_investment_agent.m5_disclosure_review import disclosure_queue_sha256  # noqa: E402
from value_investment_agent.m5_event_dependencies import dependency_graph_from_payload  # noqa: E402
from value_investment_agent.m5_event_run import apply_run_request  # noqa: E402
from value_investment_agent.m5_event_state_store import (  # noqa: E402
    JsonM5EventRunReceiptStore,
    JsonM5EventRunStateStore,
)
from value_investment_agent.m5_event_watermark import (  # noqa: E402
    SOURCE_HEALTHY,
    WATERMARK_COVERAGE_COMPLETE,
    ScanWatermark,
)
from value_investment_agent.m5_materiality_bridge import MaterialityBridgeBatch  # noqa: E402
from value_investment_agent.m5_run_request import build_run_request_from_bridge_batch  # noqa: E402


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--generated-at", required=True, type=datetime.fromisoformat)
    parser.add_argument("--bridge-batches", required=True, type=Path)
    parser.add_argument("--review-manifest", required=True, type=Path)
    parser.add_argument("--current-queue", required=True, type=Path)
    parser.add_argument("--reconciliation", required=True, type=Path)
    parser.add_argument("--graph-receipt", required=True, type=Path)
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--receipt-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def _batch_for_symbol(path: Path, symbol: str) -> MaterialityBridgeBatch:
    raw = _read_json(path)
    if not isinstance(raw, list):
        raise ValueError("bridge-batches must be a JSON list")
    batches = tuple(MaterialityBridgeBatch.from_payload(item) for item in raw)
    matches = tuple(item for item in batches if item.symbol == symbol)
    if len(matches) != 1:
        raise ValueError("Expected exactly one bridge batch for symbol")
    batch = matches[0]
    if batch.namespace != "ACTUAL" or batch.action != ACTION_NO_ORDER:
        raise ValueError("Actual offline application requires one ACTUAL no_order batch")
    return batch


def _verify_reconciliation(
    *,
    path: Path,
    queue_sha256: str,
    symbol: str,
) -> dict:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise ValueError("reconciliation must be a JSON object")
    counts = raw.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("reconciliation counts are required")
    if raw.get("action") != ACTION_NO_ORDER:
        raise ValueError("reconciliation must remain no_order")
    if raw.get("current_queue_sha256") != queue_sha256:
        raise ValueError("reconciliation does not bind the current queue")
    if counts.get("pending_human_review") != 0 or counts.get("hash_conflicts") != 0:
        raise ValueError("current queue still has unresolved human-review items")
    resolutions = raw.get("resolutions")
    if not isinstance(resolutions, list) or not resolutions:
        raise ValueError("reconciliation resolutions are required")
    scoped = [item for item in resolutions if item.get("symbol") == symbol]
    if len(scoped) != len(resolutions):
        raise ValueError("reconciliation contains another symbol")
    if any(item.get("disposition") != "CARRY_FORWARD_PRIOR_HUMAN_DECISION" for item in scoped):
        raise ValueError("all actual-review inputs must be carried forward")
    return raw


def main() -> int:
    args = parse_args()
    if args.generated_at.tzinfo is None:
        raise ValueError("--generated-at must include a timezone")
    if args.generated_at > datetime.now(timezone.utc):
        raise ValueError("--generated-at cannot be in the future")
    paths = {
        name: value.resolve()
        for name, value in {
            "bridge_batches": args.bridge_batches,
            "review_manifest": args.review_manifest,
            "current_queue": args.current_queue,
            "reconciliation": args.reconciliation,
            "graph_receipt": args.graph_receipt,
        }.items()
    }
    if any(not path.is_file() for path in paths.values()):
        raise ValueError("all input artifacts must exist")
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise ValueError("output-dir must not already exist")

    batch = _batch_for_symbol(paths["bridge_batches"], args.symbol)
    queue = disclosure_review_queue_from_payload(_read_json(paths["current_queue"]))
    current_queue_sha256 = disclosure_queue_sha256(queue)
    reconciliation = _verify_reconciliation(
        path=paths["reconciliation"],
        queue_sha256=current_queue_sha256,
        symbol=args.symbol,
    )
    manifest = _read_json(paths["review_manifest"])
    if not isinstance(manifest, dict):
        raise ValueError("review manifest must be a JSON object")
    review = manifest.get("files", {}).get("reviews.json", {})
    bridge = manifest.get("files", {}).get("bridge_batches.json", {})
    original_queue = manifest.get("queue", {})
    if not all(isinstance(item, dict) for item in (review, bridge, original_queue)):
        raise ValueError("review manifest bindings are required")
    review_path = Path(_required_text(review.get("path"), "review manifest review path"))
    review_sha256 = _required_text(review.get("sha256"), "review manifest review hash")
    if not review_path.is_file() or _digest(review_path) != review_sha256:
        raise ValueError("review manifest review bytes do not match its hash")
    bridge_path = Path(_required_text(bridge.get("path"), "review manifest bridge path"))
    bridge_sha256 = _required_text(bridge.get("sha256"), "review manifest bridge hash")
    if bridge_path.resolve() != paths["bridge_batches"] or _digest(bridge_path) != bridge_sha256:
        raise ValueError("review manifest bridge bytes do not match the requested batch")
    original_queue_sha256 = _required_text(
        original_queue.get("queue_sha256"), "review manifest queue hash"
    )

    graph_receipt = _read_json(paths["graph_receipt"])
    if not isinstance(graph_receipt, dict) or graph_receipt.get("symbol") != args.symbol:
        raise ValueError("graph receipt must match the requested symbol")
    graph = dependency_graph_from_payload(graph_receipt.get("graph"))
    if batch.review_id not in reconciliation.get("prior_review_ids", []):
        raise ValueError("reconciliation does not bind the bridge batch review")
    authorization = M5ActualOfflineAuthorization(
        authorization_id=(
            f"{args.symbol}-reconciled-offline-"
            f"{args.generated_at.strftime('%Y%m%dT%H%M%S%z')}"
        ),
        review_provenance=USER_CONFIRMED_DELEGATED_REVIEW,
        review_sha256=review_sha256,
        queue_sha256=original_queue_sha256,
        dependency_graph_sha256=graph_sha256(graph),
        authorized_at=args.generated_at,
    )
    scan = next((item for item in queue.scans if item.symbol == args.symbol), None)
    if scan is None or scan.coverage_status != WATERMARK_COVERAGE_COMPLETE:
        raise ValueError("current queue lacks complete scan coverage for symbol")
    watermark = ScanWatermark(
        watermark_id=f"{queue.queue_id}-{args.symbol}",
        scope=args.symbol,
        source=queue.provider,
        coverage_through=queue.retrieved_at,
        retrieved_at=queue.retrieved_at,
        parser_version=queue.parser_version,
        coverage_status=WATERMARK_COVERAGE_COMPLETE,
        source_health=SOURCE_HEALTHY,
        evidence_refs=tuple(scan.evidence_refs),
    )
    request = build_run_request_from_bridge_batch(
        batch,
        run_id=args.run_id,
        generated_at=args.generated_at,
        watermark=watermark,
        graph=graph,
        actual_offline_authorization=authorization,
    )
    result = apply_run_request(
        request=request,
        store=JsonM5EventRunStateStore(args.state_root.resolve()),
        receipt_store=JsonM5EventRunReceiptStore(args.receipt_root.resolve()),
    )
    output_dir.mkdir(parents=True)
    request_path = output_dir / "request.json"
    request_path.write_text(request.to_json() + "\n", encoding="utf-8")
    result_path = output_dir / "application.json"
    result_path.write_text(
        json.dumps(result.as_policy(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    output = {
        "schema_version": "m5-actual-offline-application-v1",
        "symbol": args.symbol,
        "action": ACTION_NO_ORDER,
        "operations": {
            "scheduler_enabled": False,
            "notification_enabled": False,
            "production_database_write": False,
        },
        "inputs": {name: {"path": str(path), "sha256": _digest(path)} for name, path in paths.items()},
        "reconciliation_id": reconciliation["reconciliation_id"],
        "current_queue_sha256": current_queue_sha256,
        "request": {"path": str(request_path), "sha256": _digest(request_path)},
        "application": {"path": str(result_path), "sha256": _digest(result_path)},
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
