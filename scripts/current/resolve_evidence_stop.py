"""Append an auditable Evidence Stop resolution after an admitted run completed."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.infrastructure.evidence.evidence_stop_schedule import (  # noqa: E402
    record_evidence_stop_resolution,
)


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule-id", required=True)
    parser.add_argument("--request", type=_path, required=True)
    parser.add_argument("--package", type=_path, required=True)
    parser.add_argument("--research-result", type=_path, required=True)
    parser.add_argument("--research-result-sha256", required=True)
    args = parser.parse_args()
    result = record_evidence_stop_resolution(
        root=ROOT,
        schedule_id=args.schedule_id,
        request_path=args.request,
        package_path=args.package,
        research_result_path=args.research_result,
        research_result_sha256=args.research_result_sha256,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
