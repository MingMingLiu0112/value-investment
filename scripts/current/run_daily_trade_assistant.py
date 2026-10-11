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
from value_investment_agent.application.product.daily_assets import inspect_daily_case_assets, recover_daily_case_assets  # noqa: E402
from value_investment_agent.application.product.daily_batch import run_daily_batch, previous_case_from_run  # noqa: E402
from value_investment_agent.presentation.daily_trade_assistant import run_daily_trade_assistant  # noqa: E402


def _collect_quote(symbol: str) -> tuple[Path | None, str | None]:
    try:
        completed = subprocess.run([sys.executable, str(ROOT / "scripts/collect_quote_sessions.py"),
            "--symbols", symbol], cwd=ROOT, capture_output=True, timeout=90, check=True)
        output_lines = completed.stdout.decode("utf-8", errors="replace").strip().splitlines()
        collected = json.loads(output_lines[-1])
        return Path(collected["path"]) / "bundle.json", None
    except (subprocess.SubprocessError, ValueError, KeyError, IndexError) as error:
        return None, f"双源行情采集未完成：{type(error).__name__}: {error}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--symbol", default=None)
    selection.add_argument("--symbols", help="Comma-separated registered companies; failures stay isolated.")
    selection.add_argument("--all-registered", action="store_true")
    parser.add_argument("--previous-run", type=Path,
                        help="Compare to a prior immutable daily receipt; its workbench hash is rechecked.")
    parser.add_argument("--quote-bundle", type=Path,
                        help="Existing quote archive; its source/date are revalidated.")
    parser.add_argument("--no-collect-quote", action="store_true",
                        help="Run without network collection and show the missing quote gate.")
    parser.add_argument("--agent-mode", choices=("offline", "mock", "none"), default="offline")
    parser.add_argument("--review-packet", action="store_true", help="Expose consumed assumptions and exact human-review gaps.")
    parser.add_argument("--monthly-review", action="store_true", help="Compare pinned research semantics without inventing new disclosures.")
    parser.add_argument("--collect-events", action="store_true", help="Archive an incremental official window; never auto-approve materiality or advance research dates.")
    parser.add_argument("--agent-excerpts", type=Path, help="Pinned original excerpt requests for a single registered company.")
    parser.add_argument("--agent-excerpts-sha256")
    parser.add_argument("--valuation-proposal-policy", type=Path,
                        help="Finite, unapproved economic alternatives through the existing model; single company only.")
    parser.add_argument("--valuation-proposal-policy-sha256")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--report-only", action="store_true",
                        help="Generate the same verified report/read model without requiring the Excel runtime.")
    parser.add_argument("--check-assets", action="store_true",
                        help="Inspect pinned inputs and original files without research or network calls.")
    parser.add_argument("--recover-assets-from", type=Path,
                        help="Restore missing identical assets from a project-local recovery directory; never overwrite.")
    args = parser.parse_args()
    if args.quote_bundle is not None and not args.no_collect_quote:
        parser.error("--quote-bundle requires --no-collect-quote")
    registry = load_json_object(ROOT / "config/daily-trade-assistant-v1.json", "daily cases")
    if registry.get("schema_version") != "daily-trade-assistant-cases-v1" or registry.get("action") != "no_order":
        raise ValueError("daily case registry is not a no-order contract")
    registry["cases"] = {symbol: {**case, "review_packet": args.review_packet,
        "monthly_review": args.monthly_review, "collect_events": args.collect_events} for symbol, case in registry["cases"].items()}
    symbols = list(registry["cases"]) if args.all_registered else (
        [value.strip() for value in args.symbols.split(",")] if args.symbols else [args.symbol or "600519"])
    if len(set(symbols)) != len(symbols) or any(symbol not in registry["cases"] for symbol in symbols):
        parser.error("each symbol must be distinct and have a registered daily case")
    if (args.agent_excerpts is None) != (args.agent_excerpts_sha256 is None):
        parser.error("agent excerpts require both path and SHA-256")
    if (args.valuation_proposal_policy is None) != (args.valuation_proposal_policy_sha256 is None):
        parser.error("valuation proposal policy requires both path and SHA-256")
    if args.valuation_proposal_policy is not None:
        if len(symbols) != 1:
            parser.error("valuation proposal requires one company")
        registry["cases"][symbols[0]].update(valuation_proposal_policy=args.valuation_proposal_policy.as_posix(),
            valuation_proposal_policy_sha256=args.valuation_proposal_policy_sha256)
    if args.agent_excerpts is not None:
        if len(symbols) != 1 or args.agent_mode == "none":
            parser.error("agent excerpts require one company and an enabled Agent mode")
        registry["cases"][symbols[0]].update(agent_excerpts=args.agent_excerpts.as_posix(),
            agent_excerpts_sha256=args.agent_excerpts_sha256)
    previous_run = None if args.previous_run is None else ROOT / args.previous_run
    if len(symbols) > 1:
        if args.check_assets or args.recover_assets_from:
            results = {symbol: (recover_daily_case_assets(root=ROOT, case=registry["cases"][symbol],
                            source_root=ROOT / args.recover_assets_from, agent_mode=args.agent_mode)
                        if args.recover_assets_from else inspect_daily_case_assets(root=ROOT,
                            case=registry["cases"][symbol], agent_mode=args.agent_mode)) for symbol in symbols}
            print(json.dumps({"cases": results, "action": "no_order"}, ensure_ascii=False, indent=2))
            if args.check_assets:
                return 2 if any(value["blockers"] for value in results.values()) else 0
        output_dir = ROOT / (args.output_dir or Path("runtime/daily-trade-assistant") /
                            (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-batch"))
        result = run_daily_batch(root=ROOT, cases=registry["cases"], symbols=symbols,
            output_dir=output_dir, run_case=run_daily_trade_assistant,
            quote_provider=None if args.no_collect_quote else _collect_quote,
            quote_bundle=None if args.quote_bundle is None else ROOT / args.quote_bundle,
            agent_mode=args.agent_mode, previous_run=previous_run, report_only=args.report_only)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result["failed_case_count"] or result["blocked_asset_count"] or result["partial_product_count"] else 0
    args.symbol = symbols[0]
    case = registry.get("cases", {}).get(args.symbol)
    if not isinstance(case, dict):
        parser.error("symbol has no registered source-bound daily research case")
    case = previous_case_from_run(root=ROOT, case=case, previous_run=previous_run, symbol=args.symbol)
    asset_index = (recover_daily_case_assets(root=ROOT, case=case,
                    source_root=ROOT / args.recover_assets_from, agent_mode=args.agent_mode)
                   if args.recover_assets_from else inspect_daily_case_assets(
                       root=ROOT, case=case, agent_mode=args.agent_mode))
    if args.check_assets:
        print(json.dumps({"symbol": args.symbol, **asset_index}, ensure_ascii=False, indent=2))
        return 0 if not asset_index["blockers"] else 2
    quote_bundle = None if args.quote_bundle is None else ROOT / args.quote_bundle
    quote_error = None
    if not args.no_collect_quote and not any(row["required_for_research"] for row in asset_index["blockers"]):
        quote_bundle, quote_error = _collect_quote(args.symbol)
    output_dir = args.output_dir or Path("runtime/daily-trade-assistant") / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + args.symbol
    )
    result = run_daily_trade_assistant(
        root=ROOT, symbol=args.symbol, case=case, output_dir=ROOT / output_dir,
        quote_bundle=quote_bundle, agent_mode=args.agent_mode, quote_error=quote_error,
        report_only=args.report_only,
    )
    quote_summary = {key: value for key, value in result["quote_check"].items()
                     if key != "source_evidence"}
    print(json.dumps({"symbol": args.symbol, "recommendation_type": result["recommendation_type"],
                      "status": result["status"], "preview_error": result.get("preview_error"),
                      "preview_generated": result.get("preview_generated", False),
                      "quote_check": quote_summary, "agent_scope": result["agent_scope"],
                      "agent_error": result["agent_error"],
                      "outputs": result["outputs"], "receipt": str((ROOT / output_dir / "receipt.json").resolve()),
                      "action": "no_order"}, ensure_ascii=False, indent=2))
    return 2 if result.get("status") == "BLOCKED_RESEARCH_ASSETS" or result.get("preview_error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
