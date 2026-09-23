"""Run official-filing point-in-time replay for the three M1 valuation packages."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m1_pit_replay import (  # noqa: E402
    ACTION_NO_ORDER,
    build_pit_replay_payload,
    write_pit_replay_runtime,
)
from value_investment_agent.m1_valuation_package_builder import (  # noqa: E402
    load_package_specs,
)


REPLAY_SYMBOLS = ("000651", "600741", "600887")


def _report(payload: dict, paths: dict[str, str]) -> str:
    lines = [
        "M1 OFFICIAL FILING PIT REPLAY",
        f"generated_at: {payload['generated_at']}",
        f"packages: {payload['package_count']}",
        f"action: {payload['action']}",
        "",
        f"{'symbol':<8} {'filings':<8} {'decision_points':<16} future_rejections",
    ]
    for item in payload["packages"]:
        lines.append(
            f"{item['symbol']:<8} {len(item['official_filings']):<8} "
            f"{len(item['decision_points']):<16} "
            f"{len(item['future_disclosure_rejections'])}"
        )
    lines.extend(
        [
            "",
            "Scope: retained official filing source availability only; "
            "no later facts, no PostgreSQL and no orders.",
            f"evidence: {paths['evidence_path']}",
            f"manifest: {paths['manifest_path']}",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--symbols", nargs="*", default=REPLAY_SYMBOLS)
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    specs = load_package_specs(args.root)
    selected = {
        str(item["symbol"]): item
        for item in specs
        if item.get("symbol") in args.symbols
    }
    missing = sorted(set(args.symbols) - set(selected))
    if missing:
        raise ValueError(f"Missing valuation packages: {', '.join(missing)}")
    payload = build_pit_replay_payload(
        selected,
        root=args.root,
        generated_at=datetime.now(timezone.utc),
    )
    if payload["action"] != ACTION_NO_ORDER:
        raise ValueError("PIT replay violated the no_order contract")
    paths = (
        {}
        if args.no_write
        else write_pit_replay_runtime(
            payload,
            root=args.root,
            package_payloads=selected,
            script_path=Path(__file__).resolve(),
        )
    )
    if args.json_only:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_report(payload, paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
