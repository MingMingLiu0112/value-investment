"""Build a hash-pinned M2 ChannelVerificationResult packet.

The command is read-only with respect to AC8/AC9/M2 inputs, the WPS workbook,
production database and server projects. It writes one new runtime packet.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
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


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _write(output_dir: Path, name: str, payload: dict) -> Path:
    target = output_dir / name
    target.write_bytes(_json_bytes(payload))
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CHANNEL_VERIFICATION_PATH)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "runtime" / "m2-channel-verification-20260924-v1",
    )
    parser.add_argument(
        "--generated-at",
        type=lambda value: datetime.fromisoformat(value).astimezone(timezone.utc),
        default=datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    if not output_dir.is_relative_to(ROOT.resolve()):
        raise ValueError("M2 channel verification output escapes project root")
    if (output_dir / "report.json").exists():
        raise ValueError(f"M2 channel verification output already exists: {output_dir / 'report.json'}")
    output_dir.mkdir(parents=True, exist_ok=True)

    policy = load_m2_channel_verification_policy(args.config)
    batch = build_m2_channel_verification(
        policy,
        root=ROOT,
        generated_at=args.generated_at,
    )
    report_path = _write(output_dir, "report.json", batch.as_policy())
    report_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "m2-channel-verification-manifest-v1",
        "action": "no_order",
        "config": str(Path(args.config).resolve().relative_to(ROOT)),
        "report_sha256": report_sha256,
        "machine_status": batch.machine_status,
        "acceptance_status": batch.acceptance_status,
        "summary": batch.as_policy()["summary"],
    }
    _write(output_dir, "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
