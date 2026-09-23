"""Build a hash-pinned M1 Application workbook candidate.

The candidate is derived from the shared Application outcome and the archived
dossier read model.  It is a presentation candidate only: no WPS publication,
no PostgreSQL and no order path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m1_application_workbook import (
    ACTION_NO_ORDER,
    APPLICATION_POINTER,
    APPLICATION_SCHEMA,
    build_application_workbook,
    write_application_workbook,
)
from value_investment_agent.m1_research_dossier_candidate import (
    load_candidate_pointer,
)
from value_investment_agent.research_read_model import DOSSIER_SCHEMA_VERSION
_APPLICATION_RUNNER = runpy.run_path(
    str(ROOT / "scripts" / "run_m1_research_application.py"),
    run_name="m1_application_runner",
)


MANIFEST_SCHEMA = "m1-research-application-workbook-v1"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Build in memory and print a summary without writing a workbook.",
    )
    return parser


def _report(payload, result, manifest) -> str:
    lines = [
        "M1 RESEARCH APPLICATION WORKBOOK CANDIDATE",
        f"generated_at: {manifest['generated_at']}",
        f"action: {manifest['action']}",
        f"packages: {payload['package_count']}",
        f"run_status_counts: {json.dumps(payload['run_status_counts'], ensure_ascii=False)}",
        f"workbook_sha256: {result['workbook_sha256']}",
        "",
        "Scope: local candidate only; no WPS publication and no orders.",
    ]
    return "\n".join(lines)


def main() -> int:
    args = _parser().parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    application = _APPLICATION_RUNNER["run_all"](args.root)
    runtime_paths = _APPLICATION_RUNNER["write_runtime"](application, args.root)
    collection = load_candidate_pointer(args.root)
    if application.get("action") != ACTION_NO_ORDER:
        raise ValueError("Application run violated the no_order contract")

    if args.no_write:
        workbook = build_application_workbook(application, collection)
        print(
            f"built workbook with {len(workbook.sheetnames)} sheets "
            f"for {application['package_count']} packages"
        )
        return 0

    result = write_application_workbook(
        root=args.root,
        application_payload=application,
        collection=collection,
        output=args.output,
    )
    target = args.root / result["workbook_path"]
    application_source = (args.root / runtime_paths["evidence_path"]).read_bytes()
    dossier_pointer = (
        args.root / "runtime/m1-research-dossier-candidate-latest.json"
    ).read_bytes()
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "generated_at": application["generated_at"],
        "action": ACTION_NO_ORDER,
        "application_schema": APPLICATION_SCHEMA,
        "application_pointer": APPLICATION_POINTER,
        "application_evidence_sha256": hashlib.sha256(application_source).hexdigest(),
        "dossier_schema": DOSSIER_SCHEMA_VERSION,
        "dossier_pointer": "runtime/m1-research-dossier-candidate-latest.json",
        "dossier_pointer_sha256": hashlib.sha256(dossier_pointer).hexdigest(),
        "workbook_path": result["workbook_path"],
        "workbook_sha256": result["workbook_sha256"],
        "package_count": application["package_count"],
    }
    (target.parent / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(_report(application, result, manifest))
    print(f"runtime workbook: {result['workbook_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
