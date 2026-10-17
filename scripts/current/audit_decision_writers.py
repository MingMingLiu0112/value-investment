#!/usr/bin/env python3
"""Read-only audit of the decision-writer registry (thin CLI wrapper)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.operations.decision_writer_registry import (  # noqa: E402
    audit,
    load_registry,
)


def _observed(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return {str(key): str(value) for key, value in payload.items()}
    result: dict[str, str] = {}
    for item in payload:
        name = item.get("TaskName") or item.get("task_name")
        if not name:
            raise ValueError("observed task entry requires TaskName")
        result[str(name)] = str(item.get("State") or item.get("state") or "")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=ROOT / "config" / "decision-writers-registry-v1.json")
    parser.add_argument("--observed-tasks-json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    observed = _observed(args.observed_tasks_json) if args.observed_tasks_json else None
    report = audit(load_registry(args.registry), observed=observed)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())