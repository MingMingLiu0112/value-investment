"""Run a source-pinned, offline-only three-role research pilot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.common import load_json_object, require_inside
from value_investment_agent.application.research.agent_review.supervisor import (
    run_agent_research_pilot,
)
from value_investment_agent.application.research.agent_review.llm_pilot import run_llm_research_pilot
from value_investment_agent.infrastructure.agent_runtime.provider import (
    MockLLMProvider, OpenAICompatibleChatProvider,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--workbench", type=Path, required=True)
    parser.add_argument("--workbench-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("offline", "mock", "live"), default="offline")
    parser.add_argument("--mock-responses", type=Path)
    parser.add_argument("--mock-responses-sha256")
    parser.add_argument("--provider-config", type=Path)
    parser.add_argument("--provider-config-sha256")
    parser.add_argument("--authorize-paid-api", action="store_true")
    args = parser.parse_args()
    if args.mode == "offline":
        packet = run_agent_research_pilot(
            root=ROOT, symbol=args.symbol, workbench=ROOT / args.workbench,
            workbench_sha256=args.workbench_sha256, output=ROOT / args.output,
        )
    else:
        if args.mode == "mock":
            if not args.mock_responses or not args.mock_responses_sha256:
                parser.error("mock mode requires a pinned response fixture")
            fixture = require_inside(ROOT, ROOT / args.mock_responses, "mock responses")
            if sha256_file(fixture) != args.mock_responses_sha256:
                raise ValueError("Mock response fixture hash mismatch")
            values = load_json_object(fixture, "mock responses")
            provider = MockLLMProvider({key: json.dumps(value, ensure_ascii=False)
                                        for key, value in values.items()})
            limits = {}
        else:
            if not args.authorize_paid_api or not args.provider_config or not args.provider_config_sha256:
                parser.error("live mode requires explicit authorization and a pinned provider config")
            config_path = require_inside(ROOT, ROOT / args.provider_config, "provider config")
            if sha256_file(config_path) != args.provider_config_sha256:
                raise ValueError("Provider configuration hash mismatch")
            config = load_json_object(config_path, "provider config")
            provider = OpenAICompatibleChatProvider(
                endpoint=config["endpoint"], model_id=config["model_id"],
                api_key_env=config["api_key_env"],
                timeout_seconds=int(config.get("timeout_seconds", 20)),
            )
            limits = {
                "max_run_cost_usd": float(config["max_run_cost_usd"]),
                "input_usd_per_million": float(config["input_usd_per_million"]),
                "output_usd_per_million": float(config["output_usd_per_million"]),
                "live_authorized": True,
                "provider_input_sha256": args.provider_config_sha256,
            }
        packet = run_llm_research_pilot(
            root=ROOT, symbol=args.symbol, workbench=ROOT / args.workbench,
            workbench_sha256=args.workbench_sha256, output=ROOT / args.output,
            provider=provider, mode=args.mode, **limits,
        )
    print(json.dumps({
        "scope": packet["scope"], "symbol": packet["symbol"],
        "finding_count": len(packet["findings"]),
        "output": str(args.output),
        "output_sha256": sha256_file(ROOT / args.output),
        "action": "no_order",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
