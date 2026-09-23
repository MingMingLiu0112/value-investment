"""Build a standalone simulated M3 history-chain Excel candidate."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from value_investment_agent.m1_sample_preregistration import (
    load_m1_sample_preregistration,
)
from value_investment_agent.m3_history_read_model import (
    M3_HISTORY_INPUT_SCHEMA,
    build_decision_history_collection,
    build_history_chain_from_payloads,
)
from value_investment_agent.m3_history_workbook import write_history_workbook


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "tests" / "fixtures" / "m3_history_demo.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output workbook path. Defaults to a timestamped runtime candidate.",
    )
    return parser.parse_args()


def load_input(path: Path) -> tuple[dict, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("M3 history input must be a JSON object")
    if payload.get("schema_version") != M3_HISTORY_INPUT_SCHEMA:
        raise ValueError("Unknown M3 history input schema")
    if payload.get("action") != "no_order":
        raise ValueError("M3 history input must remain no_order")
    receipt = {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    return payload, receipt


def group_payloads(payload: dict) -> list[dict]:
    groups: dict[str, dict] = {}
    for entry in payload.get("entries") or ():
        symbol = str(entry.get("symbol") or "")
        if not symbol:
            raise ValueError("M3 history entry is missing symbol")
        if symbol in groups:
            raise ValueError(f"M3 history demo contains duplicate symbol: {symbol}")
        groups[symbol] = {
            "entry_payload": entry,
            "journal_payloads": [],
            "consistency_payloads": [],
        }
    for journal in payload.get("journals") or ():
        symbol = str(journal.get("symbol") or "")
        if symbol not in groups:
            raise ValueError(f"M3 history journal references unknown symbol: {symbol}")
        groups[symbol]["journal_payloads"].append(journal)
    for review in payload.get("consistency_reviews") or ():
        symbol = str(review.get("symbol") or "")
        if symbol not in groups:
            raise ValueError(
                f"M3 history consistency references unknown symbol: {symbol}"
            )
        groups[symbol]["consistency_payloads"].append(review)
    return list(groups.values())


def main() -> int:
    args = parse_args()
    payload, input_receipt = load_input(args.input.resolve())
    grouped = group_payloads(payload)
    chains = [
        build_history_chain_from_payloads(
            entry_payload=item["entry_payload"],
            journal_payloads=item["journal_payloads"],
            consistency_payloads=item["consistency_payloads"],
        )
        for item in grouped
    ]
    generated_at = datetime.fromtimestamp(
        args.input.resolve().stat().st_mtime,
        tz=timezone.utc,
    )
    collection = build_decision_history_collection(
        generated_at=generated_at,
        source_id=str(payload.get("source_id") or "simulated-m3-history"),
        chains=chains,
    )
    names = {
        entry.symbol: entry.name
        for entry in load_m1_sample_preregistration().companies
    }
    output = args.output
    if output is None:
        stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
        output = (
            ROOT
            / "runtime"
            / f"m3-history-candidate-{stamp}"
            / f"A股价值投资_M3历史链候选_{generated_at:%Y%m%d}.xlsx"
        )
    result = write_history_workbook(
        collection,
        output=output,
        root=output.resolve().parent,
        security_names=names,
    )
    manifest = {
        **result,
        "schema_version": collection.schema_version,
        "source_id": collection.source_id,
        "generated_at": generated_at.isoformat(),
        "input": input_receipt,
    }
    manifest_path = output.resolve().with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
