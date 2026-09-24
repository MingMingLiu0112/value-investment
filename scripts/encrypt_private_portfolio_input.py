"""Validate and encrypt one private M4 portfolio JSON input without printing it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from value_investment_agent.private_portfolio_intake import (
    encrypt_private_portfolio_payload,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Encrypt a private portfolio JSON input and print a non-sensitive receipt."
    )
    parser.add_argument("--input", type=Path, required=True)
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


def _load_private_payload(input_path: Path, private_root: Path) -> dict:
    source = input_path.resolve()
    root = private_root.resolve()
    if not source.is_file() or source.is_symlink():
        raise ValueError("private portfolio input must be a regular file")
    try:
        source.relative_to(root)
    except ValueError as error:
        raise ValueError("private portfolio input must live under private_root") from error
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("private portfolio input must be valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("private portfolio input must be a JSON object")
    return payload


def main() -> int:
    args = _arguments()
    repository_root = Path(__file__).resolve().parents[1]
    payload = _load_private_payload(args.input, args.private_root)
    receipt = encrypt_private_portfolio_payload(
        payload,
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
