"""Run every M1 valuation package through the shared research application.

Malformed descriptors stay isolated.  The local runtime output is a replayable
application evidence bundle; it does not use PostgreSQL, WPS or an order path.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m1_reverse_valuation import reverse_for_descriptor
from value_investment_agent.m1_valuation_package_builder import (
    build_package_descriptor_attempts,
)
from value_investment_agent.research_application import ResearchApplicationService
from value_investment_agent.research_artifact_repository import (
    InMemoryResearchArtifactRepository,
)
from value_investment_agent.research_input import build_research_run_spec


SCHEMA_VERSION = "m1-research-application-run-v1"
POINTER_NAME = "m1-research-application-latest.json"


def _json_object(value, serializer=None):
    if value is None:
        return None
    return json.loads(serializer()) if serializer else value


def run_all(root: Path) -> dict:
    attempts = build_package_descriptor_attempts(root)
    service = ResearchApplicationService(InMemoryResearchArtifactRepository())
    results = []
    for attempt in attempts:
        item = {
            "package_id": attempt.package_id,
            "symbol": attempt.symbol,
            "descriptor_error": attempt.error,
            "input_sha256": (
                attempt.descriptor.input_sha256
                if attempt.descriptor is not None else None
            ),
            "run_status": None,
            "blockers": [],
            "action": None,
            "distribution": None,
            "reverse_valuations": [],
            "valuation": None,
            "price_bridge": None,
            "gate": None,
            "model_validity": None,
            "current_data_status": None,
            "research_conclusion": None,
        }
        if attempt.descriptor is None or attempt.error is not None:
            results.append(item)
            continue
        descriptor = attempt.descriptor
        item["distribution"] = (
            descriptor.distribution_result.as_policy()
            if descriptor.distribution_result is not None else None
        )
        item["reverse_valuations"] = [
            result.as_policy() for result in reverse_for_descriptor(descriptor)
        ]
        outcome = service.run_company_research(build_research_run_spec(descriptor))
        item["run_status"] = outcome.status
        item["blockers"] = outcome.blockers
        item["action"] = getattr(outcome.current_status, "action", None)
        item["valuation"] = _json_object(
            outcome.valuation,
            serializer=outcome.valuation.to_json,
        )
        item["price_bridge"] = _json_object(
            outcome.price_bridge,
            serializer=outcome.price_bridge.to_json,
        )
        item["gate"] = asdict(outcome.gate) if outcome.gate is not None else None
        item["model_validity"] = (
            _json_object(outcome.model_validity, serializer=outcome.model_validity.to_json)
            if outcome.model_validity is not None else None
        )
        item["current_data_status"] = (
            outcome.current_status.current_data_status.as_policy()
            if outcome.current_status is not None
            and outcome.current_status.current_data_status is not None
            else None
        )
        item["research_conclusion"] = outcome.current_status.research_conclusion
        results.append(item)

    statuses = {}
    for item in results:
        key = item["run_status"] or ("DESCRIPTOR_FAILED" if item["descriptor_error"] else "UNKNOWN")
        statuses[key] = statuses.get(key, 0) + 1
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "action": "no_order",
        "package_count": len(results),
        "run_status_counts": statuses,
        "results": results,
    }


def write_runtime(payload: dict, root: Path) -> dict[str, str]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = root / "runtime" / f"m1-research-application-{timestamp}"
    target.mkdir(parents=True, exist_ok=False)
    evidence = target / "evidence.json"
    evidence.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": payload["generated_at"],
        "action": "no_order",
        "package_count": payload["package_count"],
        "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    pointer = {
        "path": str(target.relative_to(root)),
        "sha256": manifest["evidence_sha256"],
    }
    (root / "runtime" / POINTER_NAME).write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "evidence_path": str(evidence.relative_to(root)),
        "manifest_path": str((target / "manifest.json").relative_to(root)),
        "pointer_path": str((root / "runtime" / POINTER_NAME).relative_to(root)),
    }


def _report(payload: dict) -> str:
    lines = [
        "M1 RESEARCH APPLICATION RUN",
        f"generated_at: {payload['generated_at']}",
        f"packages: {payload['package_count']}",
        "run_status_counts: " + json.dumps(
            payload["run_status_counts"], ensure_ascii=False
        ),
        "",
        f"{'symbol':<8} {'run_status':<25} action",
    ]
    for item in payload["results"]:
        status = item["run_status"] or item["descriptor_error"]
        lines.append(
            f"{item['symbol'] or '-':<8} {status:<25} {item['action']}"
        )
    lines.append("")
    lines.append("Scope: local runtime JSON only; no PostgreSQL, WPS or orders.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    payload = run_all(args.root)
    paths = {} if args.no_write else write_runtime(payload, args.root)
    if args.json_only:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_report(payload))
        if paths:
            print("")
            print("runtime outputs:")
            for key in ("evidence_path", "manifest_path", "pointer_path"):
                print(f"- {paths[key]}")
    if payload["action"] != "no_order":
        print("ERROR: no_order contract violated", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
