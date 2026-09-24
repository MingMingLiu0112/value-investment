#!/usr/bin/env python3
"""Package or verify a local encrypted backup without touching production.

This is an M6 readiness command. It only reads/writes paths supplied on the
command line. It never connects to PostgreSQL, a server service, a cloud
destination or a broker, and it never creates an order.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.backup_security import (  # noqa: E402
    decrypt_package,
    encrypt_package,
    load_policy,
)


def _policy_path(value: Path) -> Path:
    return (ROOT if not value.is_absolute() else Path()).resolve() / value


def _code_version(root: Path) -> str:
    payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(payload.get("project", {}).get("version", "unknown"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    package = subparsers.add_parser("package", help="create an encrypted backup package")
    package.add_argument("--source", type=Path, required=True)
    package.add_argument("--key", type=Path, required=True)
    package.add_argument("--output", type=Path, required=True)
    package.add_argument("--root", type=Path, default=ROOT)
    package.add_argument("--policy", type=Path, default=Path("config/m6-backup-security-v1.json"))
    package.add_argument("--config-file", action="append", type=Path, default=[])
    package.add_argument("--release-file", action="append", type=Path, default=[])
    package.add_argument("--offsite-staging", type=Path)
    verify = subparsers.add_parser("verify", help="decrypt and hash-verify a backup package")
    verify.add_argument("--input", type=Path, required=True)
    verify.add_argument("--key", type=Path, required=True)
    verify.add_argument("--output-dir", type=Path, required=True)
    verify.add_argument("--policy", type=Path, default=Path("config/m6-backup-security-v1.json"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "package":
        policy = load_policy(_policy_path(args.policy))
        config_paths = args.config_file or [args.root / item for item in policy.config_inventory]
        release_paths = args.release_file or [args.root / item for item in policy.release_inventory]
        result = encrypt_package(
            args.source,
            args.output,
            args.key,
            _policy_path(args.policy),
            config_paths=config_paths,
            release_paths=release_paths,
            offsite_staging=args.offsite_staging,
            code_version=_code_version(args.root),
        )
    else:
        result = decrypt_package(
            args.input,
            args.output_dir,
            args.key,
            _policy_path(args.policy),
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
