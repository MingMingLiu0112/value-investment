#!/usr/bin/env python3
"""Thin CLI for rebuilding the repository script inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "src"
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from value_investment_agent.application.architecture import (  # noqa: E402
    build_script_inventory,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    registry = json.loads(
        (root / "config" / "current-cli-entrypoints-v1.json").read_text(
            encoding="utf-8"
        )
    )
    entrypoints = {
        str(item["path"]): item for item in registry["entrypoints"]
    }
    inventory = build_script_inventory(root, current_entrypoints=entrypoints)
    text = json.dumps(inventory.as_dict(), ensure_ascii=False, indent=2) + "\n"
    output = (args.output or root / "docs" / "architecture" / "script-inventory-v1.json").resolve()
    if not output.is_relative_to(root):
        raise ValueError("Inventory output must remain under the project root")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
