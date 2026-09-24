"""Write a hash-verified, no-verdict reading brief for an M5 queue."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m5_disclosure_briefing import (  # noqa: E402
    build_disclosure_review_briefing,
)
from value_investment_agent.m5_disclosure_queue import (  # noqa: E402
    disclosure_review_queue_from_payload,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, default=ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    if output.exists():
        raise ValueError(f"Briefing output already exists: {output}")
    queue = disclosure_review_queue_from_payload(
        json.loads(args.queue.read_text(encoding="utf-8"))
    )
    briefing = build_disclosure_review_briefing(
        queue,
        archive_root=args.archive_root.resolve(),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(briefing, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), "candidate_count": briefing["candidate_count"], "action": "no_order"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
