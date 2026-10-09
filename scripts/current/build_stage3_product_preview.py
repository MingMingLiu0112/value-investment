"""Render a non-canonical product Excel preview from a verified read model and pinned v3 decision."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from value_investment_agent.application.product.common import require_inside, sha256_file
from value_investment_agent.application.product.decision_surface import project_verified_decision_workbench
from value_investment_agent.application.product.agent_research_surface import project_verified_agent_packet
from value_investment_agent.application.product.research_publication_input import load_research_publication_input
from value_investment_agent.presentation.excel.product_workbench import write_product_workbench_candidate
from value_investment_agent.presentation.read_models.existing_research_report import public_workbench_payload_from_snapshot
from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication-input", type=Path, required=True)
    parser.add_argument("--publication-input-sha256", required=True)
    parser.add_argument("--decision-workbench", type=Path, required=True)
    parser.add_argument("--decision-workbench-sha256", required=True)
    parser.add_argument("--agent-research-packet", type=Path)
    parser.add_argument("--agent-research-packet-sha256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (args.agent_research_packet is None) != (args.agent_research_packet_sha256 is None):
        parser.error("agent research packet and hash must be supplied together")

    verified = load_research_publication_input(
        root=ROOT,
        path=ROOT / args.publication_input,
        expected_sha256=args.publication_input_sha256,
    )
    payload = public_workbench_payload_from_snapshot(verified["snapshot"])
    # The pinned snapshot was generated before the pinned v3 workbench; re-stamp only
    # the generation instant so the temporal gate can be evaluated. as_of is unchanged.
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    project_verified_decision_workbench(
        payload,
        root=ROOT,
        path=(ROOT / args.decision_workbench).resolve(),
        expected_sha256=args.decision_workbench_sha256,
    )
    if args.agent_research_packet is not None:
        project_verified_agent_packet(
            payload, root=ROOT, path=(ROOT / args.agent_research_packet).resolve(),
            expected_sha256=args.agent_research_packet_sha256,
        )
    model = product_workbench_from_payload(payload)
    output = require_inside(ROOT / "runtime", ROOT / args.output, "product preview output")
    receipt = write_product_workbench_candidate(model, output=output, root=ROOT)
    receipt["publication_input_sha256"] = args.publication_input_sha256
    receipt["decision_workbench_sha256"] = args.decision_workbench_sha256
    receipt["agent_research_packet_sha256"] = args.agent_research_packet_sha256
    receipt["scope"] = "NON_CANONICAL_STAGE3_PREVIEW_NOT_USER_ACCEPTANCE"
    (output.with_suffix(".receipt.json")).write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(json.dumps({
        "workbook": str(output.relative_to(ROOT).as_posix()),
        "workbook_sha256": sha256_file(output),
        "company_symbols": [company.symbol for company in model.companies],
        "action": "no_order",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
