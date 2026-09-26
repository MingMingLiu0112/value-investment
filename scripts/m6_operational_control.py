#!/usr/bin/env python3
"""Read or change the local M6 operational-control state.

The state file is local evidence only. Advancing modes is disabled until an
authorization receipt can be verified; emergency stop is always allowed. This command never
touches production, publishes a workbook or creates an order.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m6_operational_control import (  # noqa: E402
    MODE_SHADOW,
    MODE_STAGING,
    apply_emergency_stop,
    control_state_lock,
    initial_state,
    read_control_state,
    transition,
    write_control_state,
)
from value_investment_agent.m6_shadow_receipts import (  # noqa: E402
    verify_shadow_authorization_for_control,
)


DEFAULT_STATE = ROOT / "runtime" / "m6-operational-control-state.json"


def _load(path: Path) -> object:
    if not path.exists():
        return initial_state(operator_id="unattended-local-run")
    return read_control_state(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="print the current local state")
    stop = subparsers.add_parser("stop", help="write an emergency-stop state")
    stop.add_argument("--reason", required=True)
    stop.add_argument("--operator", required=True)
    advance = subparsers.add_parser("advance", help="advance local state using an externally approved signed authorization")
    advance.add_argument("--target", required=True, choices=[MODE_STAGING, MODE_SHADOW])
    advance.add_argument("--authorization-bundle", type=Path, required=True)
    advance.add_argument("--authorization-trust-root", type=Path, required=True)
    advance.add_argument("--reason", required=True)
    advance.add_argument("--operator", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = args.state.resolve()
    now = datetime.now(timezone.utc)
    authorization = None
    if args.command == "advance":
        bundle = json.loads(args.authorization_bundle.read_text(encoding="utf-8"))
        trust_root = json.loads(args.authorization_trust_root.read_text(encoding="utf-8"))
        authorization = verify_shadow_authorization_for_control(
            bundle,
            trust_root,
            target_mode=args.target,
            operator_id=args.operator,
            at=now,
        )

    with control_state_lock(path):
        state = _load(path)
        if args.command == "stop":
            state = apply_emergency_stop(
                state,
                reason=args.reason,
                operator_id=args.operator,
                changed_at=now,
            )
            write_control_state(path, state, at=now)
        elif args.command == "advance":
            state = transition(
                state,
                target_mode=args.target,
                authorization=authorization,
                reason=args.reason,
                operator_id=args.operator,
                changed_at=now,
            )
            write_control_state(path, state, at=now)
    print(json.dumps(state.as_dict(at=now), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
