"""Run one manual no-order research, quote, Agent and Excel preview cycle."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from value_investment_agent.application.product.common import load_json_object  # noqa: E402
from value_investment_agent.presentation.daily_trade_assistant import run_daily_trade_assistant  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="600519")
    parser.add_argument("--quote-bundle", type=Path,
                        help="Existing quote archive; its source/date are revalidated.")
    parser.add_argument("--no-collect-quote", action="store_true",
                        help="Run without network collection and show the missing quote gate.")
    parser.add_argument("--agent-mode", choices=("offline", "mock", "none"), default="offline")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.quote_bundle is not None and not args.no_collect_quote:
        parser.error("--quote-bundle requires --no-collect-quote")
    registry = load_json_object(ROOT / "config/daily-trade-assistant-v1.json", "daily cases")
    if registry.get("schema_version") != "daily-trade-assistant-cases-v1" or registry.get("action") != "no_order":
        raise ValueError("daily case registry is not a no-order contract")
    case = registry.get("cases", {}).get(args.symbol)
    if not isinstance(case, dict):
        parser.error("symbol has no registered source-bound daily research case")
    quote_bundle = None if args.quote_bundle is None else ROOT / args.quote_bundle
    quote_error = None
    if not args.no_collect_quote:
        try:
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts/collect_quote_sessions.py"),
                 "--symbols", args.symbol], cwd=ROOT, capture_output=True,
                timeout=90, check=True,
            )
            output_lines = completed.stdout.decode("utf-8", errors="replace").strip().splitlines()
            collected = json.loads(output_lines[-1])
            quote_bundle = Path(collected["path"]) / "bundle.json"
        except (subprocess.SubprocessError, ValueError, KeyError, IndexError) as error:
            quote_error = f"双源行情采集未完成：{type(error).__name__}: {error}"
    output_dir = args.output_dir or Path("runtime/daily-trade-assistant") / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + args.symbol
    )
    result = run_daily_trade_assistant(
        root=ROOT, symbol=args.symbol, case=case, output_dir=ROOT / output_dir,
        quote_bundle=quote_bundle, agent_mode=args.agent_mode, quote_error=quote_error,
    )
    quote_summary = {key: value for key, value in result["quote_check"].items()
                     if key != "source_evidence"}
    print(json.dumps({"symbol": args.symbol, "recommendation_type": result["recommendation_type"],
                      "quote_check": quote_summary, "agent_scope": result["agent_scope"],
                      "agent_error": result["agent_error"],
                      "outputs": result["outputs"], "receipt": str((ROOT / output_dir / "receipt.json").resolve()),
                      "action": "no_order"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
