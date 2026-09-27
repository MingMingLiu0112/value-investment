"""Register a bounded public research observation plan without observing outcomes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product.prospective_registration import (  # noqa: E402
    register_prospective_research_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan", type=Path, default=ROOT / "config" / "prospective-research-observation-plan-v2.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = args.plan if args.plan.is_absolute() else ROOT / args.plan
    output = args.output if args.output.is_absolute() else ROOT / args.output
    print(json.dumps(
        register_prospective_research_plan(root=ROOT, plan_path=plan, output_path=output),
        ensure_ascii=False, indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
