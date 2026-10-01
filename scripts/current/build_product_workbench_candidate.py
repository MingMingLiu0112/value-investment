#!/usr/bin/env python3
"""Build an explicitly requested historical preview; never a user frontend."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.build_m7_daily_workbench import build_packet  # noqa: E402
from value_investment_agent.application.product.common import (  # noqa: E402
    encode_json_bytes,
    sha256_bytes,
    require_inside,
    load_json_object,
    sha256_file,
    write_new_json,
)
from value_investment_agent.application.product.workbench import load_existing_workbench_for_presentation  # noqa: E402
from value_investment_agent.presentation.read_models.existing_research_report import project_existing_research_workbench, public_workbench_payload_from_snapshot  # noqa: E402
from value_investment_agent.application.product.product_workbench_candidate import (  # noqa: E402
    build_product_workbench_candidate_payload,
)
from value_investment_agent.presentation.excel.product_workbench import (  # noqa: E402
    write_product_workbench_candidate,
)
from value_investment_agent.presentation.read_models.product_workbench import (  # noqa: E402
    product_workbench_from_payload,
)


def _generated_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("generated-at must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-payload", type=Path)
    parser.add_argument("--base-payload-sha256")
    parser.add_argument("--base-read-model-snapshot", action="store_true")
    parser.add_argument("--existing-workbench", type=Path)
    parser.add_argument("--existing-workbench-sha256")
    parser.add_argument("--integrate-canonical", action="store_true",
                        help="Retain all canonical sheets in a runtime-only reviewed preview.")
    parser.add_argument(
        "--historical-preview",
        action="store_true",
        help="Required acknowledgement that this is a runtime-only historical preview.",
    )
    parser.add_argument(
        "--generated-at",
        type=_generated_at,
        default=datetime.now(timezone.utc),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.historical_preview:
        raise ValueError("refusing candidate creation without --historical-preview")
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if not output.resolve().is_relative_to(ROOT / "runtime"):
        raise ValueError("historical preview must remain under runtime/")
    source_receipt = output.with_name(output.stem + ".source-bindings.json")
    if source_receipt.exists():
        raise FileExistsError("historical preview source receipt already exists")
    packet = None
    if args.base_payload is not None or args.base_payload_sha256 is not None:
        if args.base_payload is None or args.base_payload_sha256 is None:
            raise ValueError("base payload requires path and hash")
        base = require_inside(ROOT, ROOT / args.base_payload, "base payload")
        if sha256_file(base) != args.base_payload_sha256:
            raise ValueError("base payload hash mismatch")
        payload = load_json_object(base, "base payload")
        if args.base_read_model_snapshot:
            payload = public_workbench_payload_from_snapshot(payload)
    else:
        if args.base_read_model_snapshot:
            raise ValueError("snapshot mode requires pinned base payload")
        packet = build_packet(args.generated_at)
        payload = build_product_workbench_candidate_payload(packet, root=ROOT)
    model = product_workbench_from_payload(payload)
    if args.existing_workbench is not None or args.existing_workbench_sha256 is not None:
        if args.existing_workbench is None or args.existing_workbench_sha256 is None:
            raise ValueError("existing workbench requires path and hash")
        research = load_existing_workbench_for_presentation(
            root=ROOT, path=ROOT / args.existing_workbench,
            expected_sha256=args.existing_workbench_sha256,
        )
        model = project_existing_research_workbench(model, research)
    if getattr(args, "integrate_canonical", False):
        if args.base_payload is None or args.existing_workbench is None:
            raise ValueError("canonical integration requires pinned base and existing research")
        from scripts.current.publish_product_workbench_to_canonical import (
            _workbook_path, build_protected_research_preview,
        )
        receipt = build_protected_research_preview(ROOT, _workbook_path(), output, model)
    else:
        receipt = write_product_workbench_candidate(model, output=output, root=ROOT)
    receipt.update(
        {
            "legacy_packet_schema_version": None if packet is None else packet["schema_version"],
            "legacy_packet_sha256": None if packet is None else sha256_bytes(encode_json_bytes(packet)),
            "legacy_evidence_count": None if packet is None else len(packet["audit"]["artifacts"]),
            "existing_workbench_sha256": args.existing_workbench_sha256,
            "base_payload_sha256": args.base_payload_sha256,
        }
    )
    write_new_json(source_receipt, {
        "schema_version": "existing-workbench-preview-bindings-v1",
        "base_payload_path": None if args.base_payload is None else str(args.base_payload),
        "base_payload_sha256": args.base_payload_sha256,
        "base_is_read_model_snapshot": args.base_read_model_snapshot,
        "integrated_canonical": getattr(args, "integrate_canonical", False),
        "existing_workbench_path": None if args.existing_workbench is None else str(args.existing_workbench),
        "existing_workbench_sha256": args.existing_workbench_sha256,
        "output_manifest_sha256": receipt["manifest_sha256"],
        "workbook_sha256": receipt["workbook_sha256"],
        "historical_preview": True, "canonical_written": False, "action": "no_order",
    })
    receipt["source_receipt"] = str(source_receipt.relative_to(ROOT))
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
