"""Build the hash-pinned M2 second-stage ChannelVerificationResult v2 packet.

The command consumes the immutable AC8/AC9/M2 receipt plus the retained
financial and dividend evidence. It applies explicit channel-specific rules and
never promotes a PENDING_DEEP_RESEARCH report merely because evidence exists.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m2_channel_verification_v2 import (  # noqa: E402
    DEFAULT_CHANNEL_VERIFICATION_V2_PATH,
    build_m2_channel_verification_v2,
    load_m2_channel_verification_policy_v2,
)


DEFAULT_OUTPUT = ROOT / "runtime" / "m2-channel-verification-20260924-v2"
DEFAULT_GENERATED_AT = datetime(
    2026,
    9,
    24,
    10,
    0,
    0,
    tzinfo=timezone(timedelta(hours=8)),
)


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _write(output_dir: Path, name: str, payload: dict) -> Path:
    target = output_dir / name
    target.write_bytes(_json_bytes(payload))
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CHANNEL_VERIFICATION_V2_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--generated-at", type=datetime.fromisoformat, default=DEFAULT_GENERATED_AT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    output_dir = args.output_dir.resolve()
    if not output_dir.is_relative_to(ROOT.resolve()):
        raise ValueError("M2 channel verification v2 output escapes project root")
    if output_dir.exists():
        raise ValueError(f"M2 channel verification v2 output already exists: {output_dir}")

    policy = load_m2_channel_verification_policy_v2(args.config)
    batch = build_m2_channel_verification_v2(
        policy,
        root=ROOT,
        generated_at=args.generated_at,
    )
    output_dir.mkdir(parents=True)
    payload = batch.as_policy(
        {
            "universe_count": 5568,
            "financial_evidence_count": 873,
            "pass_count": 0,
        }
    )
    report_path = _write(output_dir, "report.json", payload)
    report_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "m2-channel-verification-manifest-v2",
        "action": "no_order",
        "config": str(Path(args.config).resolve().relative_to(ROOT)),
        "report_sha256": report_sha256,
        "machine_status": batch.machine_status,
        "acceptance_status": batch.acceptance_status,
        "v1_status": batch.source_binding["v1_status"],
        "pit_status": batch.source_binding["pit_status"],
        "summary": payload["summary"],
    }
    _write(output_dir, "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
