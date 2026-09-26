"""Review one symbol's disclosure queue without applying events or notifying."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from ...m5_disclosure_queue import disclosure_review_queue_from_payload
from ...m5_disclosure_review import (
    build_disclosure_materiality_reviews,
    disclosure_queue_sha256,
    disclosure_review_intake_from_payload,
)
from ...m5_event_core import NAMESPACE_ACTUAL
from ...m5_materiality_bridge import build_materiality_bridge_batch
from .common import (
    ACTION_NO_ORDER,
    load_json_object,
    normalize_symbol,
    receipt,
    require_inside,
    sha256_file,
    write_new_json,
)


def review_event_for_symbol(
    *,
    root: Path,
    symbol: str,
    queue_path: Path,
    intake_path: Path,
    runtime_root: Path,
    archive_root: Path | None = None,
    review_provenance: str | None = None,
) -> dict[str, Any]:
    """Build one symbol's review artifacts without applying events.

    ``review_provenance`` is a self-asserted claim, not an authenticated
    signature, so it has no default: a caller must state it explicitly.  The
    manifest records that the claim is unauthenticated and that an ACTUAL run
    still requires a signed, pinned approval receipt before anything can be
    applied.
    """
    normalized = normalize_symbol(symbol)
    queue_file = require_inside(root, queue_path, "event queue")
    intake_file = require_inside(root, intake_path, "event review intake")
    output_root = require_inside(root, runtime_root, "event review output")
    archive = require_inside(root, archive_root or root, "event archive root")
    if review_provenance is None:
        raise ValueError("event review requires an explicit review provenance claim")
    if review_provenance != "USER_CONFIRMED_DELEGATED_REVIEW":
        raise ValueError("event review requires USER_CONFIRMED_DELEGATED_REVIEW")
    if not queue_file.is_file() or not intake_file.is_file():
        raise ValueError("event queue and intake must be existing files")
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("event review output directory must be empty or absent")

    queue = disclosure_review_queue_from_payload(
        load_json_object(queue_file, "event queue")
    )
    intake = disclosure_review_intake_from_payload(
        load_json_object(intake_file, "event review intake")
    )
    if queue.action != ACTION_NO_ORDER or intake.action != ACTION_NO_ORDER:
        raise ValueError("event review inputs must remain no_order")
    matching_scans = [scan for scan in queue.scans if scan.symbol == normalized]
    if len(matching_scans) != 1 or len(queue.scans) != 1:
        raise ValueError("event review queue must contain exactly the requested symbol")

    reviews = build_disclosure_materiality_reviews(
        queue,
        intake,
        archive_root=archive,
    )
    batches = tuple(
        build_materiality_bridge_batch(review, namespace=NAMESPACE_ACTUAL)
        for review in reviews
    )
    output_root.mkdir(parents=True, exist_ok=True)
    files = {
        "intake": output_root / "intake.json",
        "reviews": output_root / "reviews.json",
        "bridge_batches": output_root / "bridge_batches.json",
    }
    write_new_json(files["intake"], intake.as_policy())
    write_new_json(
        files["reviews"],
        {"action": ACTION_NO_ORDER, "reviews": [item.as_policy() for item in reviews]},
    )
    write_new_json(
        files["bridge_batches"],
        {"action": ACTION_NO_ORDER, "batches": [item.as_policy() for item in batches]},
    )
    manifest = {
        "schema_version": "generic-event-review-result-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "command": "event_review",
        "symbol": normalized,
        "action": ACTION_NO_ORDER,
        "review_provenance": review_provenance,
        "provenance_authenticated": False,
        "requires_signed_approval_receipt_for_actual": True,
        "queue_sha256": sha256_file(queue_file),
        "queue_contract_sha256": disclosure_queue_sha256(queue),
        "intake_sha256": sha256_file(intake_file),
        "review_count": len(reviews),
        "event_count": sum(len(batch.events) for batch in batches),
        "events_not_applied": True,
        "files": {
            name: {"path": str(path), "sha256": sha256_file(path)}
            for name, path in files.items()
        },
    }
    manifest_path = output_root / "manifest.json"
    write_new_json(manifest_path, manifest)
    return {
        "result": manifest,
        "receipt": receipt(
            command="event_review",
            symbol=normalized,
            input_hashes={
                "queue": sha256_file(queue_file),
                "intake": sha256_file(intake_file),
            },
            output_path=manifest_path,
            output_bytes=None,
        )
        | {"output_sha256": sha256_file(manifest_path)},
    }
