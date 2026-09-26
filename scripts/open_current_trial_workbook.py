"""Resolve and optionally open the one configured canonical user workbook."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POINTER = ROOT / "config" / "current-trial-workbook.json"
CANONICAL_NAME = "A股价值投资_Agent前端智能跟踪模板.xlsx"


def _canonical_workbook() -> Path:
    value = os.environ.get("WORKBOOK_PATH")
    env_file = ROOT / ".env"
    if not value and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("WORKBOOK_PATH"):
                value = line.split("=", 1)[1].strip()
                break
    if not value:
        raise ValueError("CANONICAL_WORKBOOK_NOT_RESOLVED")
    workbook = Path(value).expanduser().resolve()
    if not workbook.is_file() or workbook.suffix.lower() != ".xlsx" or workbook.name != CANONICAL_NAME:
        raise ValueError("CANONICAL_WORKBOOK_NOT_RESOLVED")
    return workbook


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the current read-only M7 trial workbook.")
    parser.add_argument("--open", action="store_true", help="Open the verified workbook with the default Windows application.")
    args = parser.parse_args()
    contract = json.loads(POINTER.read_text(encoding="utf-8"))
    if contract.get("workbook_source") != "WORKBOOK_PATH" or contract.get("action") != "no_order":
        raise ValueError("current workbook pointer is not a canonical no_order contract")
    workbook = _canonical_workbook()
    actual_sha = __import__("hashlib").sha256(workbook.read_bytes()).hexdigest()
    result = {
        "status": contract["status"],
        "workbook": str(workbook),
        "sha256": actual_sha,
        "m6_operational_status": contract.get("m6_operational_status"),
        "initial_assisted_use": contract.get("initial_assisted_use"),
        "action": "no_order",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.open:
        if os.name != "nt":
            raise ValueError("--open is supported only on Windows")
        os.startfile(workbook)  # type: ignore[attr-defined]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
