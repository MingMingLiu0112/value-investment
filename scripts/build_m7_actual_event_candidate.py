"""Render an isolated M7 candidate with the verified ACTUAL M5 read model."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m7_daily_workbench import write_daily_workbench  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--read-model", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    model_path = args.read_model.resolve()
    model = json.loads(model_path.read_text(encoding="utf-8"))
    if (model.get("schema_version") != "m5-actual-event-read-model-v1"
        or model.get("action") != "no_order" or model.get("pending_human_review") != 0):
        raise ValueError("Actual M5 read model is not complete or no_order")
    generated_at = datetime.now(timezone.utc)
    builder = runpy.run_path(str(source_root / "scripts" / "build_m7_daily_workbench_post_checkpoint_a.py"))
    packet = builder["build_packet"](generated_at)
    packet["as_of"] = generated_at.date().isoformat()
    queue = packet["m5"]["disclosure_queue_600519"]
    if queue["queue_id"] != model["queue_id"] or queue["symbol"] != model["symbol"]:
        raise ValueError("M7 disclosure queue does not match actual review read model")
    queue["pending_count"] = model["pending_human_review"]
    queue["pending_items"] = []
    packet["m5"]["actual_event_chain"] = model
    packet["stage_statuses"]["m5"] = [
        "M5", "ACTUAL_OFFLINE_PARTIAL", "PARTIAL", "BOUNDED_RECALCULATION_NOT_READY",
    ]
    packet["audit"]["artifacts"].append({
        "label": "M5 600519 ACTUAL 事件与有界重算状态",
        "path": str(model_path),
        "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
    })
    receipt = write_daily_workbench(packet, output=args.output, root=ROOT)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
