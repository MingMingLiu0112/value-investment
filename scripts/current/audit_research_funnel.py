"""Write an immutable W6 audit of a hash-pinned M2 research funnel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.research.research_funnel_audit import (  # noqa: E402
    audit_research_funnel,
    build_human_review_packet,
    write_research_funnel_audit,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    result = audit_research_funnel(
        root=ROOT,
        receipt_path=args.receipt,
        manifest_path=args.manifest,
        queue_path=args.queue,
    )
    packet = build_human_review_packet(result)
    manifest = write_research_funnel_audit(
        result,
        packet,
        root=ROOT,
        output_dir=args.output_dir,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

