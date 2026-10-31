"""Build a hash-bound, non-admitted M2 data-check queue."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product.common import require_inside, write_new_json
from value_investment_agent.application.research.value_research_queue import build_value_research_queue


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--report-sha256", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--budget", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--previous-sha256")
    parser.add_argument("--priority-version", choices=("v1", "v2"), default="v1")
    parser.add_argument("--financial-export", type=Path)
    parser.add_argument("--financial-export-sha256")
    parser.add_argument("--public-evidence-bundle", type=Path,
                        help="Optional v2 public-evidence bundle; PARTIAL gaps allowed, at least one verified original required; read-only")
    parser.add_argument("--public-evidence-sha256")
    parser.add_argument("--enrichment-budget", type=int, default=10)
    parser.add_argument("--execute-enrichment", action="store_true")
    parser.add_argument("--allow-public-evidence-downloads", action="store_true")
    parser.add_argument("--execution-budget", type=int, default=2)
    args = parser.parse_args()
    if (args.public_evidence_bundle is None) != (args.public_evidence_sha256 is None):
        parser.error("public evidence bundle requires path and hash")
    if args.public_evidence_bundle is not None and args.priority_version != "v2":
        parser.error("public evidence bundle requires --priority-version v2")
    if args.execute_enrichment and args.priority_version != 'v2':
        parser.error('enrichment execution requires v2')
    if args.allow_public_evidence_downloads and not args.execute_enrichment:
        parser.error('public downloads require explicit enrichment execution')
    if (args.previous is None) != (args.previous_sha256 is None):
        parser.error("previous queue requires path and hash")
    if args.priority_version == "v2" and (args.financial_export is None or args.financial_export_sha256 is None):
        parser.error("v2 requires financial export path and hash")
    if args.priority_version == "v1" and (args.financial_export is not None or args.financial_export_sha256 is not None):
        parser.error("financial export requires --priority-version v2")
    output = require_inside(ROOT / "runtime", ROOT / args.output, "value research queue")
    builder = build_value_research_queue
    options = {}
    if args.priority_version == "v2":
        from value_investment_agent.application.research.value_research_priority_v2 import build_value_research_priority_v2
        builder = build_value_research_priority_v2
        options = dict(financial_export_path=ROOT / args.financial_export,
            financial_export_sha256=args.financial_export_sha256, enrichment_budget=args.enrichment_budget)
        if args.public_evidence_bundle is not None:
            from value_investment_agent.application.research.public_evidence import validate_queue_public_evidence
            validate_queue_public_evidence(root=ROOT,
                bundle_path=ROOT / args.public_evidence_bundle,
                bundle_sha256=args.public_evidence_sha256,
                financial_export_path=ROOT / args.financial_export,
                financial_export_sha256=args.financial_export_sha256)
    queue = builder(root=ROOT, report_path=ROOT / args.report,
        report_sha256=args.report_sha256, receipt_path=ROOT / args.receipt,
        receipt_sha256=args.receipt_sha256, budget=args.budget,
        previous_path=ROOT / args.previous if args.previous else None,
        previous_sha256=args.previous_sha256, **options)
    write_new_json(output, queue)
    summary = {key: value for key, value in queue.items() if key not in
               {"entries", "deep_research_priority", "evidence_enrichment_work_queue"}}
    if args.execute_enrichment:
        from datetime import datetime, timezone
        from value_investment_agent.application.research.value_enrichment_batch import (
            execute_value_enrichment_batch, load_enrichment_research_contexts,
        )
        from value_investment_agent.application.product.common import sha256_file
        folder = output.with_name(output.stem + '-enrichment')
        repository, contexts, context_status = load_enrichment_research_contexts(root=ROOT,
            symbols=[row['symbol'] for row in queue['evidence_enrichment_work_queue']],
            evaluation_at=datetime.now(timezone.utc))
        execution = execute_value_enrichment_batch(root=ROOT, queue=queue,
            financial_export_path=ROOT / args.financial_export,
            financial_export_sha256=args.financial_export_sha256, output_dir=folder,
            budget=args.execution_budget, allow_network=args.allow_public_evidence_downloads,
            repository=repository, research_contexts=contexts)
        summary['research_context_loading'] = context_status
        summary['enrichment_execution'] = dict(status=execution['status'],
            path=(folder / 'execution.json').relative_to(ROOT).as_posix(),
            sha256=sha256_file(folder / 'execution.json'), attempted_count=execution['attempted_count'])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
