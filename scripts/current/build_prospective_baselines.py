"""Write prospective public baseline cards and an append-only observation ledger."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from value_investment_agent.application.product.prospective_baseline import (  # noqa: E402
    build_prospective_baselines, build_verified_prospective_baselines,
)
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "config" / "prospective-baseline-verification-v3.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--legacy-v1", action="store_true", help="Reproduce the historical unverified v1 contract only")
    args = parser.parse_args()
    source = args.input if args.input.is_absolute() else ROOT / args.input
    output = args.output if args.output.is_absolute() else ROOT / args.output
    builder = build_prospective_baselines if args.legacy_v1 else build_verified_prospective_baselines
    print(json.dumps(builder(root=ROOT, input_path=source, output_path=output), ensure_ascii=False, indent=2))
    return 0
if __name__ == "__main__": raise SystemExit(main())
