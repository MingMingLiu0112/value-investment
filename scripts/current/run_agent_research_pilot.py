"""Run a source-pinned, offline-only three-role research pilot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.research.agent_review.supervisor import (
    run_agent_research_pilot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--workbench", type=Path, required=True)
    parser.add_argument("--workbench-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packet = run_agent_research_pilot(
        root=ROOT, symbol=args.symbol, workbench=ROOT / args.workbench,
        workbench_sha256=args.workbench_sha256, output=ROOT / args.output,
    )
    print(json.dumps({
        "scope": packet["scope"], "symbol": packet["symbol"],
        "finding_count": len(packet["findings"]),
        "output": str(args.output),
        "output_sha256": sha256_file(ROOT / args.output),
        "action": "no_order",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
