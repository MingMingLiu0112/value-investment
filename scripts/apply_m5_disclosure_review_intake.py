"""Apply an append-only, user-confirmed M5 disclosure intake JSON.

This is an alternative input surface to the editable workbook.  It exists for
an explicit user-confirmed delegated review and deliberately reuses the same
queue binding, archived-PDF verification and materiality bridge contracts.
It writes receipts only; it never applies events, sends notifications or orders.
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
from value_investment_agent.m5_disclosure_queue import disclosure_review_queue_from_payload  # noqa: E402
from value_investment_agent.m5_disclosure_review import (  # noqa: E402
    build_disclosure_materiality_reviews,
    disclosure_review_intake_from_payload,
    disclosure_queue_sha256,
)
from value_investment_agent.m5_event_core import NAMESPACE_ACTUAL  # noqa: E402
from value_investment_agent.m5_materiality_bridge import build_materiality_bridge_batch  # noqa: E402


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--intake", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--archive-root", type=Path, default=ROOT)
    parser.add_argument(
        "--review-provenance",
        required=True,
        choices=("USER_CONFIRMED_DELEGATED_REVIEW",),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queue_path = args.queue.resolve()
    intake_path = args.intake.resolve()
    runtime_root = args.runtime_root.resolve()
    archive_root = args.archive_root.resolve()
    if not queue_path.is_file() or not intake_path.is_file():
        raise ValueError("Queue and intake JSON must exist")
    if runtime_root.exists():
        raise ValueError("Receipt directory must not already exist")

    queue = disclosure_review_queue_from_payload(json.loads(queue_path.read_text(encoding="utf-8")))
    intake = disclosure_review_intake_from_payload(json.loads(intake_path.read_text(encoding="utf-8")))
    if queue.action != ACTION_NO_ORDER or intake.action != ACTION_NO_ORDER:
        raise ValueError("M5 delegated review must remain no_order")
    reviews = build_disclosure_materiality_reviews(queue, intake, archive_root=archive_root)
    batches = tuple(build_materiality_bridge_batch(review, namespace=NAMESPACE_ACTUAL) for review in reviews)

    runtime_root.mkdir(parents=True)
    files = {
        "intake.json": runtime_root / "intake.json",
        "reviews.json": runtime_root / "reviews.json",
        "bridge_batches.json": runtime_root / "bridge_batches.json",
    }
    files["intake.json"].write_text(intake.to_json() + "\n", encoding="utf-8")
    files["reviews.json"].write_text(json.dumps([item.as_policy() for item in reviews], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files["bridge_batches.json"].write_text(json.dumps([item.as_policy() for item in batches], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "m5-delegated-review-application-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_provenance": args.review_provenance,
        "action": ACTION_NO_ORDER,
        "queue": {"path": str(queue_path), "sha256": _digest(queue_path), "queue_sha256": disclosure_queue_sha256(queue)},
        "intake": {"path": str(intake_path), "sha256": _digest(intake_path), "reviewed_at": intake.reviewed_at.isoformat()},
        "review_count": len(reviews),
        "decision_count": sum(len(item.decisions) for item in reviews),
        "event_count": sum(len(item.events) for item in batches),
        "silent_decision_count": sum(item.silent_count for item in batches),
        "events_not_applied": True,
        "files": {name: {"path": str(path), "sha256": _digest(path)} for name, path in files.items()},
    }
    (runtime_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
