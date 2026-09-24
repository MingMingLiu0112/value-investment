"""Build the blank human-review intake workbook from a pinned M5 queue."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.disclosures import SYMBOL_NAMES  # noqa: E402
from value_investment_agent.m5_disclosure_queue import (  # noqa: E402
    ACTION_NO_ORDER,
    disclosure_review_queue_from_payload,
)
from value_investment_agent.m5_disclosure_review import (  # noqa: E402
    DISCLOSURE_REVIEW_INTAKE_SCHEMA,
    disclosure_queue_sha256,
)
from value_investment_agent.m5_disclosure_briefing import (  # noqa: E402
    build_disclosure_review_briefing,
)
from value_investment_agent.m5_disclosure_review_workbook import (  # noqa: E402
    write_m5_disclosure_review_workbook,
)


DEFAULT_QUEUE = (
    ROOT
    / "runtime"
    / "m5-disclosure-review-20260923T213249Z"
    / "queue.json"
)
DEFAULT_OUTPUT = ROOT / "A股价值投资_M5真实披露人工复核回填_20260924.xlsx"
DEFAULT_WPS_DIR = Path("C:/Users/we/WPSDrive/197617831/WPS云盘/价投跟踪")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--wps-dir", type=Path, default=DEFAULT_WPS_DIR)
    parser.add_argument("--no-wps", action="store_true")
    return parser.parse_args()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_wps(workbook: Path, wps_dir: Path | None) -> dict | None:
    if wps_dir is None or not wps_dir.exists():
        return None
    wps_dir.mkdir(parents=True, exist_ok=True)
    target = wps_dir / workbook.name
    counter = 1
    while target.exists():
        target = wps_dir / f"{workbook.stem}_{counter}{workbook.suffix}"
        counter += 1
    shutil.copy2(workbook, target)
    return {
        "path": str(target.resolve()),
        "sha256": _digest(target),
    }


def main() -> int:
    args = parse_args()
    queue_path = args.queue.resolve()
    output = args.output.resolve()
    if output.exists():
        raise ValueError(f"Disclosure review workbook already exists: {output}")
    payload = json.loads(queue_path.read_text(encoding="utf-8"))
    if payload.get("action") != ACTION_NO_ORDER:
        raise ValueError("Disclosure review queue must remain no_order")
    queue = disclosure_review_queue_from_payload(payload)
    briefing = build_disclosure_review_briefing(queue, archive_root=ROOT)
    queue_receipt = {
        "path": str(queue_path),
        "sha256": _digest(queue_path),
        "queue_sha256": disclosure_queue_sha256(queue),
    }
    result = write_m5_disclosure_review_workbook(
        queue,
        output=output,
        root=ROOT,
        security_names=SYMBOL_NAMES,
        briefing=briefing,
    )
    wps_result = None if args.no_wps else _copy_wps(output, args.wps_dir)
    manifest = {
        **result,
        "schema_version": DISCLOSURE_REVIEW_INTAKE_SCHEMA,
        "queue": queue_receipt,
        "wps_workbook": wps_result,
        "decision_version": "20260924.1",
        "pending_candidate_count": len(queue.pending_candidates),
        "action": ACTION_NO_ORDER,
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
