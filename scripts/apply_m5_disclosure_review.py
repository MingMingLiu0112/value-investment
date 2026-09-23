"""Apply a completed M5 review workbook without creating events or notifications."""
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
from value_investment_agent.m5_disclosure_queue import (  # noqa: E402
    disclosure_review_queue_from_payload,
)
from value_investment_agent.m5_disclosure_review import (  # noqa: E402
    build_disclosure_materiality_reviews,
    disclosure_queue_sha256,
)
from value_investment_agent.m5_disclosure_review_workbook import (  # noqa: E402
    read_m5_disclosure_review_workbook,
)
from value_investment_agent.m5_event_core import NAMESPACE_SIMULATED  # noqa: E402
from value_investment_agent.m5_materiality_bridge import (  # noqa: E402
    build_materiality_bridge_batch,
)


DEFAULT_QUEUE = (
    ROOT
    / "runtime"
    / "m5-disclosure-review-20260923T213249Z"
    / "queue.json"
)
DEFAULT_WORKBOOK = ROOT / "A股价值投资_M5真实披露人工复核回填_20260924.xlsx"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--runtime-root", type=Path)
    return parser.parse_args()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    args = parse_args()
    queue_path = args.queue.resolve()
    workbook_path = args.workbook.resolve()
    if not queue_path.is_file():
        raise ValueError(f"Disclosure queue is missing: {queue_path}")
    if not workbook_path.is_file():
        raise ValueError(f"Disclosure review workbook is missing: {workbook_path}")
    queue = disclosure_review_queue_from_payload(
        json.loads(queue_path.read_text(encoding="utf-8"))
    )
    if queue.action != ACTION_NO_ORDER:
        raise ValueError("Disclosure review queue must remain no_order")
    intake = read_m5_disclosure_review_workbook(workbook_path, queue)
    reviews = build_disclosure_materiality_reviews(queue, intake)
    batches = [
        build_materiality_bridge_batch(review, namespace=NAMESPACE_SIMULATED)
        for review in reviews
    ]
    generated_at = datetime.now(timezone.utc)
    if args.runtime_root is None:
        runtime_root = ROOT / "runtime" / f"m5-disclosure-review-applied-{generated_at:%Y%m%dT%H%M%SZ}"
    else:
        runtime_root = args.runtime_root.resolve()
    if runtime_root.exists() and any(runtime_root.iterdir()):
        raise ValueError(f"Review application runtime is not empty: {runtime_root}")
    runtime_root.mkdir(parents=True, exist_ok=True)

    files: dict[str, Path] = {}
    files["intake.json"] = runtime_root / "intake.json"
    files["reviews.json"] = runtime_root / "reviews.json"
    files["bridge_batches.json"] = runtime_root / "bridge_batches.json"
    files["intake.json"].write_text(
        intake.to_json() + "\n",
        encoding="utf-8",
    )
    files["reviews.json"].write_text(
        json.dumps(
            [review.as_policy() for review in reviews],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    files["bridge_batches.json"].write_text(
        json.dumps(
            [batch.as_policy() for batch in batches],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "m5-disclosure-review-application-v1",
        "generated_at": generated_at.isoformat(),
        "action": ACTION_NO_ORDER,
        "queue": {
            "path": str(queue_path),
            "sha256": _digest(queue_path),
            "queue_sha256": disclosure_queue_sha256(queue),
        },
        "workbook": {
            "path": str(workbook_path),
            "sha256": _digest(workbook_path),
        },
        "reviewed_at": intake.reviewed_at.isoformat(),
        "review_count": len(reviews),
        "decision_count": len(intake.decisions),
        "event_count": sum(len(batch.events) for batch in batches),
        "silent_decision_count": sum(batch.silent_count for batch in batches),
        "files": {
            name: {
                "path": str(path),
                "sha256": _digest(path),
            }
            for name, path in files.items()
        },
        "events_not_applied": True,
    }
    manifest_path = runtime_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
