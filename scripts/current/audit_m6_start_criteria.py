"""Print the read-only M6 start-criteria matrix; never request authorization."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.operations.start_criteria import (  # noqa: E402
    load_m6_start_criteria_matrix,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matrix",
        type=Path,
        default=ROOT / "config" / "m6-start-criteria-matrix-v1.json",
    )
    args = parser.parse_args()
    matrix_path = args.matrix if args.matrix.is_absolute() else ROOT / args.matrix
    matrix = load_m6_start_criteria_matrix(matrix_path, root=ROOT)
    print(json.dumps(matrix.as_policy(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
