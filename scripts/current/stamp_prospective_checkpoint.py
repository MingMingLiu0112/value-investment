"""Create or verify a forward-only timestamp chain for public research bytes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product.prospective_timestamp import (  # noqa: E402
    create_prospective_timestamp_chain,
    verify_prospective_timestamp_chain,
)
from value_investment_agent.infrastructure.rfc3161_tsa import (  # noqa: E402
    DIGICERT_POLICY_OID,
    DIGICERT_TSA_URL,
)


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="request, verify, and persist a new timestamp chain")
    create.add_argument("--payload", type=Path, required=True)
    create.add_argument("--output-dir", type=Path, required=True)
    create.add_argument("--ca-bundle", type=Path, required=True)
    create.add_argument("--tsa-url", default=DIGICERT_TSA_URL)
    create.add_argument("--policy-oid", default=DIGICERT_POLICY_OID)
    create.add_argument("--openssl-bin", type=Path)
    create.add_argument("--public-research-only", action="store_true", required=True)

    verify = commands.add_parser("verify", help="reverify a saved timestamp chain")
    verify.add_argument("--chain-dir", type=Path, required=True)
    verify.add_argument("--ca-bundle", type=Path, required=True)
    verify.add_argument("--policy-oid", default=DIGICERT_POLICY_OID)
    verify.add_argument("--openssl-bin", type=Path)

    args = parser.parse_args()
    if args.command == "create":
        result = create_prospective_timestamp_chain(
            root=ROOT,
            payload_path=_rooted(args.payload),
            output_dir=_rooted(args.output_dir),
            ca_bundle_path=_rooted(args.ca_bundle),
            expected_policy_oid=args.policy_oid,
            endpoint_url=args.tsa_url,
            openssl_binary=args.openssl_bin,
            public_research_only=args.public_research_only,
        )
    else:
        result = verify_prospective_timestamp_chain(
            chain_dir=_rooted(args.chain_dir),
            ca_bundle_path=_rooted(args.ca_bundle),
            expected_policy_oid=args.policy_oid,
            openssl_binary=args.openssl_bin,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
