#!/usr/bin/env python3
"""Build a source-pinned readable historical company closure."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.historical_validation.historical_company_closure import (  # noqa: E402
    build_historical_company_closure,
)
from value_investment_agent.application.product.common import write_new_json  # noqa: E402
from value_investment_agent.presentation.read_models.historical_company_closure import (  # noqa: E402
    render_historical_company_closure,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    report = args.report.resolve()
    runtime = (ROOT / "runtime").resolve()
    if not output.is_relative_to(runtime) or not report.is_relative_to(runtime):
        raise ValueError("historical closure outputs must remain under runtime")
    if output.exists() or report.exists():
        raise FileExistsError("refusing to overwrite historical closure output")
    payload = build_historical_company_closure(
        root=ROOT,
        input_path=args.input,
        input_sha256=args.input_sha256,
    )
    write_new_json(output, payload)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_historical_company_closure(payload), encoding="utf-8")
    print(json.dumps({
        "symbol": payload["symbol"],
        "output": str(output),
        "report": str(report),
        "engineering_delivery": payload["engineering_delivery"],
        "current_research_admission": payload["current_research_admission"],
        "strict_pit_admitted": payload["strict_pit_admitted"],
        "historical_execution_validated": payload["historical_execution_validated"],
        "action": payload["action"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
