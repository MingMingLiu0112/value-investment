"""Acquire or replay a bounded official report set; never approve research."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from value_investment_agent.application.research.public_evidence import (
    run_public_evidence, publish_public_evidence,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-public-downloads", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--previous-bundle")
    parser.add_argument("--previous-sha256")
    parser.add_argument("--publish-status", action="store_true")
    args = parser.parse_args()
    if bool(args.previous_bundle) != bool(args.previous_sha256):
        parser.error("previous bundle requires both path and hash")
    previous = dict(path=args.previous_bundle, sha256=args.previous_sha256) if args.previous_bundle else None
    binding = run_public_evidence(root=ROOT, requests=json.loads(args.requests.read_text(encoding="utf-8-sig")),
        output_dir=args.output, allow_network=args.allow_public_downloads,
        refresh=args.refresh, previous_binding=previous)
    if args.publish_status:
        publish_public_evidence(ROOT, binding)
    print(json.dumps(dict(bundle=binding, action="no_order"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
