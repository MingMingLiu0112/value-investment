"""Validate one encrypted M4 private portfolio input without printing its contents."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from value_investment_agent.private_portfolio_intake import load_private_portfolio_bundle


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an encrypted private portfolio input and print a non-sensitive receipt."
    )
    parser.add_argument("--encrypted", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument(
        "--forbidden-sync-root",
        type=Path,
        action="append",
        default=[],
        help="Additional cloud-sync root to reject; may be supplied more than once.",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    repository_root = Path(__file__).resolve().parents[1]
    _, receipt = load_private_portfolio_bundle(
        args.encrypted,
        args.key_file,
        private_root=args.private_root,
        repository_root=repository_root,
        forbidden_sync_roots=args.forbidden_sync_root,
    )
    print(json.dumps(receipt.as_policy(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
