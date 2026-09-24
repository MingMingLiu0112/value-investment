"""Build the M2 Channel Verification human-review workbook candidate."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m2_channel_verification import (  # noqa: E402
    DEFAULT_CHANNEL_VERIFICATION_PATH,
    build_m2_channel_verification,
    load_m2_channel_verification_policy,
)
from value_investment_agent.m2_channel_verification_workbook import (  # noqa: E402
    write_channel_verification_workbook,
)


DEFAULT_OUTPUT = (
    ROOT / "A股价值投资_M2通道验证人工复核包候选_20260924.xlsx"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CHANNEL_VERIFICATION_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--generated-at",
        type=lambda value: datetime.fromisoformat(value).astimezone(timezone.utc),
        default=datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    policy = load_m2_channel_verification_policy(args.config)
    batch = build_m2_channel_verification(
        policy,
        root=ROOT,
        generated_at=args.generated_at,
    )
    result = write_channel_verification_workbook(
        batch,
        output=args.output,
        root=ROOT,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
