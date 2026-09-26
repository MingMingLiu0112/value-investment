#!/usr/bin/env python3
"""Build an explicitly requested historical preview; never a user frontend."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.build_m7_daily_workbench import build_packet  # noqa: E402
from value_investment_agent.application.product.common import (  # noqa: E402
    encode_json_bytes,
    sha256_bytes,
)
from value_investment_agent.application.product.product_workbench_candidate import (  # noqa: E402
    build_product_workbench_candidate_payload,
)
from value_investment_agent.presentation.excel.product_workbench import (  # noqa: E402
    write_product_workbench_candidate,
)
from value_investment_agent.presentation.read_models.product_workbench import (  # noqa: E402
    product_workbench_from_payload,
)


def _generated_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("generated-at must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--historical-preview",
        action="store_true",
        help="Required acknowledgement that this is a runtime-only historical preview.",
    )
    parser.add_argument(
        "--generated-at",
        type=_generated_at,
        default=datetime.now(timezone.utc),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.historical_preview:
        raise ValueError("refusing candidate creation without --historical-preview")
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if not output.resolve().is_relative_to(ROOT / "runtime"):
        raise ValueError("historical preview must remain under runtime/")
    packet = build_packet(args.generated_at)
    payload = build_product_workbench_candidate_payload(packet, root=ROOT)
    model = product_workbench_from_payload(payload)
    receipt = write_product_workbench_candidate(
        model,
        output=output,
        root=ROOT,
    )
    receipt.update(
        {
            "legacy_packet_schema_version": packet["schema_version"],
            "legacy_packet_sha256": sha256_bytes(encode_json_bytes(packet)),
            "legacy_evidence_count": len(packet["audit"]["artifacts"]),
        }
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
