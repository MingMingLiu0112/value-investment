"""Build and inspect the M1 dossier candidate in local runtime only.

This report is a research workbench view.  It does not open or publish the WPS
workbook, does not use the production database, and emits no order instruction.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from value_investment_agent.m1_research_dossier_candidate import (
    ROOT,
    build_default_candidate,
    write_candidate,
)
from value_investment_agent.research_dossier_workbook import (
    write_dossier_workbook,
)
from value_investment_agent.research_read_model import (
    ACTION_NO_ORDER,
    DOSSIER_BLOCKED,
    DOSSIER_NOT_STARTED,
    DOSSIER_PARTIAL,
    DOSSIER_READABLE,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Project root. Runtime output is always written below this path.",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Build and print only; do not refresh the runtime candidate.",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print only the candidate JSON payload.",
    )
    return parser


def _report(collection) -> str:
    lines = [
        "M1 FIXED-SAMPLE RESEARCH WORKBENCH: W3 READ MODEL CANDIDATE",
        f"generated_at: {collection.generated_at.isoformat()}",
        f"action: {collection.action}",
        f"dossiers: {len(collection.dossiers)}",
    ]
    counts = {
        DOSSIER_READABLE: 0,
        DOSSIER_PARTIAL: 0,
        DOSSIER_BLOCKED: 0,
        DOSSIER_NOT_STARTED: 0,
    }
    for dossier in collection.dossiers:
        counts[dossier.readiness] += 1
    lines.append(
        "readiness: "
        + ", ".join(f"{status}={counts[status]}" for status in counts)
    )
    lines.append("")
    lines.append(
        f"{'symbol':<8} {'company':<12} {'profile':<22} {'readiness':<12} first blocker"
    )
    for dossier in collection.dossiers:
        first = dossier.research_gaps.blockers[0] if dossier.research_gaps.blockers else "-"
        if len(first) > 58:
            first = first[:55] + "..."
        lines.append(
            f"{dossier.symbol:<8} {dossier.name:<12} "
            f"{dossier.profile_id:<22} {dossier.readiness:<12} {first}"
        )
    if collection.input_failures:
        lines.append("")
        lines.append("input failures:")
        for failure in collection.input_failures:
            lines.append(f"- {failure.symbol or '<unknown>'}: {failure.error}")
    lines.append("")
    lines.append("Scope: local runtime JSON only; no WPS publication and no orders.")
    return "\n".join(lines)


def main() -> int:
    args = _parser().parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    generated_at = datetime.now(timezone.utc)
    collection = build_default_candidate(
        generated_at=generated_at,
        root=args.root,
    )
    result = None
    if not args.no_write:
        result = write_candidate(collection, root=args.root)
        workbook_result = write_dossier_workbook(collection, root=args.root)
        result.update(workbook_result)
    if args.json_only:
        print(json.dumps(collection.as_policy(), ensure_ascii=False, indent=2))
        return 0
    print(_report(collection))
    if result is not None:
        print("")
        print("runtime outputs:")
        for key in (
            "evidence_path",
            "manifest_path",
            "pointer_path",
            "workbook_path",
        ):
            print(f"- {result[key]}")
    if collection.action != ACTION_NO_ORDER:
        print("ERROR: no_order contract violated", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
