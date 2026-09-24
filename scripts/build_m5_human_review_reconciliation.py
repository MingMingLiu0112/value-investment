"""Reconcile the current CNINFO disclosure queue with prior human reviews."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.event_materiality import (  # noqa: E402
    EventMaterialityReview,
    event_materiality_review_from_payload,
)
from value_investment_agent.investment_decision import ACTION_NO_ORDER  # noqa: E402
from value_investment_agent.m5_disclosure_queue import (  # noqa: E402
    DisclosureReviewQueue,
    disclosure_review_queue_from_payload,
)
from value_investment_agent.m5_human_review_reconciliation import (  # noqa: E402
    M5_RECONCILIATION_SCHEMA,
    M5HumanReviewReconciliation,
    reconcile_m5_human_reviews,
)


DEFAULT_PRIOR_REVIEWS = (
    ROOT
    / "runtime"
    / "m1-post-review-20260923T114228Z"
    / "event-materiality-reviews.json"
)
DEFAULT_CURRENT_QUEUE = (
    ROOT
    / "runtime"
    / "m5-disclosure-review-20260923T213249Z"
    / "queue.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior-reviews", type=Path, default=DEFAULT_PRIOR_REVIEWS)
    parser.add_argument("--current-queue", type=Path, default=DEFAULT_CURRENT_QUEUE)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--archive-root", type=Path, default=ROOT)
    parser.add_argument("--as-of", type=lambda value: datetime.fromisoformat(value))
    return parser.parse_args()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_prior_reviews(path: Path) -> tuple[EventMaterialityReview, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("Prior materiality reviews must be a non-empty list")
    reviews = tuple(event_materiality_review_from_payload(item) for item in payload)
    if any(review.action != ACTION_NO_ORDER for review in reviews):
        raise ValueError("Prior materiality reviews must remain no_order")
    return reviews


def _load_queue(path: Path) -> DisclosureReviewQueue:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("action") != ACTION_NO_ORDER:
        raise ValueError("Current disclosure queue must remain no_order")
    return disclosure_review_queue_from_payload(payload)


def _current_title_map(queue: DisclosureReviewQueue) -> dict[tuple[str, str], dict]:
    return {
        (scan.symbol, item.announcement_id): {
            "title": item.title,
            "published_at": item.published_at.isoformat(),
            "source_url": item.source_url,
            "rule_kind": item.rule_kind,
        }
        for scan in queue.scans
        for item in scan.announcements
        if item.materiality_candidate
    }


def _write_json(path: Path, payload: dict) -> dict:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"path": str(path.resolve()), "sha256": _digest(path)}


def main() -> int:
    args = parse_args()
    as_of = args.as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        raise ValueError("--as-of must include a timezone")
    prior_path = args.prior_reviews.resolve()
    queue_path = args.current_queue.resolve()
    archive_root = args.archive_root.resolve()
    prior_reviews = _load_prior_reviews(prior_path)
    queue = _load_queue(queue_path)

    run_stamp = as_of.strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or (
        ROOT / "runtime" / f"m5-human-review-reconciliation-{run_stamp}"
    )
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Reconciliation output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    reconciliation = reconcile_m5_human_reviews(
        queue=queue,
        prior_reviews=prior_reviews,
        reconciliation_id=f"m5-human-review-reconciliation-{run_stamp}",
        archive_root=archive_root,
        as_of=as_of,
    )
    titles = _current_title_map(queue)
    pending_queue = {
        "schema_version": "m5-human-review-pending-queue-v1",
        "reconciliation_id": reconciliation.reconciliation_id,
        "as_of": as_of.isoformat(),
        "action": ACTION_NO_ORDER,
        "items": [
            {
                **item.as_policy(),
                **titles[(item.symbol, item.announcement_id)],
            }
            for item in reconciliation.pending_resolutions
        ],
    }

    reconciliation_receipt = _write_json(
        output_dir / "reconciliation.json",
        reconciliation.as_policy(),
    )
    pending_receipt = _write_json(output_dir / "pending-queue.json", pending_queue)
    manifest_payload = {
        "schema_version": M5_RECONCILIATION_SCHEMA,
        "reconciliation_id": reconciliation.reconciliation_id,
        "as_of": as_of.isoformat(),
        "prior_reviews_input": {
            "path": str(prior_path),
            "sha256": _digest(prior_path),
        },
        "current_queue_input": {
            "path": str(queue_path),
            "sha256": _digest(queue_path),
        },
        "archive_root": str(archive_root),
        "outputs": {
            "reconciliation": reconciliation_receipt,
            "pending_queue": pending_receipt,
        },
        "counts": reconciliation.as_policy()["counts"],
        "action": ACTION_NO_ORDER,
    }
    manifest_receipt = _write_json(output_dir / "manifest.json", manifest_payload)
    print(json.dumps(manifest_receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
