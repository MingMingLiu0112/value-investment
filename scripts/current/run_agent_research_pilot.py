"""Run the legacy research pilot or a bounded daily Mock workflow (no publication)."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
from value_investment_agent.application.research.agent_review.daily_research import (
    run_daily_event_mock, run_daily_financial_mock,
)
from value_investment_agent.application.research.agent_review.daily_batch import run_daily_mock_batch
from value_investment_agent.application.research.agent_review.context_workflows import run_daily_context_mock
from value_investment_agent.application.research.agent_review.discovery import discover_daily_mock_inputs
from value_investment_agent.application.research.agent_review.daily_registration import register_daily_draft_results
from value_investment_agent.application.research.agent_review.source_context import ExcerptRequest
from value_investment_agent.infrastructure.agent_runtime.provider import (
    MockLLMProvider, OpenAICompatibleChatProvider,
)


def _pinned_json(path: Path, digest: str, label: str) -> dict:
    path = require_inside(ROOT, ROOT / path, label)
    if sha256_file(path) != digest:
        raise ValueError(label + " hash mismatch")
    return load_json_object(path, label)


def _daily_mock(args, parser) -> int:
    if args.mode != "mock":
        parser.error("daily workflows require explicit --mode mock")
    if args.provider_config or args.provider_config_sha256 or args.authorize_paid_api:
        parser.error("daily Mock workflows do not accept provider configuration or paid authorization")
    for key in ("source_requests", "transcription", "metric_workbench", "mock_responses", "context"):
        if (getattr(args, key) is None) != (getattr(args, key + "_sha256") is None):
            parser.error(key.replace("_", "-") + " requires both path and sha256")
    if args.workflow == "event" and (args.transcription or args.metric_workbench):
        parser.error("financial inputs require --workflow financial")
    if args.workflow == "financial" and args.mock_responses:
        parser.error("financial Mock questions are generated from verified rows, not response fixtures")
    if args.workflow in {"hotspot", "retrospective"}:
        if not args.context or any((args.mock_responses, args.transcription, args.metric_workbench)):
            parser.error("context workflows require pinned --context without other workflow inputs")
    elif args.context:
        parser.error("context requires --workflow hotspot or retrospective")
    requests = ()
    if args.source_requests:
        value = _pinned_json(args.source_requests, args.source_requests_sha256, "source requests")
        if (value.get("schema_version") != "agent-excerpt-requests-v1"
                or value.get("symbol") != args.symbol or value.get("action") != "no_order"):
            raise ValueError("Source request identity/scope mismatch")
        requests = tuple(ExcerptRequest(**item) for item in value["requests"])
    kwargs = dict(root=ROOT, workbench=ROOT / args.workbench,
                  workbench_sha256=args.workbench_sha256, symbol=args.symbol,
                  output=ROOT / args.output, source_requests=requests)
    if args.workflow == "event":
        if not args.mock_responses:
            parser.error("event Mock workflow requires a pinned response fixture")
        values = _pinned_json(args.mock_responses, args.mock_responses_sha256, "mock responses")
        result = run_daily_event_mock(**kwargs, responses={
            key: json.dumps(value, ensure_ascii=False) for key, value in values.items()})
    elif args.workflow in {"hotspot", "retrospective"}:
        result = run_daily_context_mock(**kwargs, workflow=args.workflow,
            context_path=ROOT / args.context, context_sha256=args.context_sha256)
    else:
        result = run_daily_financial_mock(**kwargs,
            transcription=None if args.transcription is None else ROOT / args.transcription,
            transcription_sha256=args.transcription_sha256,
            metric_workbench=None if args.metric_workbench is None else ROOT / args.metric_workbench,
            metric_workbench_sha256=args.metric_workbench_sha256)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("packet") else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol")
    parser.add_argument("--workbench", type=Path)
    parser.add_argument("--workbench-sha256")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--batch-plan", type=Path)
    parser.add_argument("--batch-plan-sha256")
    parser.add_argument("--discover-contexts", action="store_true",
                        help="Export a deterministic pinned Mock batch from server-owned public registries")
    parser.add_argument("--discovery-output", type=Path,
                        default=Path("runtime/agent-research-discovery"))
    parser.add_argument("--max-hotspots", type=int, default=3)
    parser.add_argument("--test-only-retrospective", type=Path)
    parser.add_argument("--test-only-retrospective-sha256")
    parser.add_argument("--register-drafts", action="store_true",
                        help="Explicit source-reverified display registration, never research approval")
    parser.add_argument("--mode", choices=("offline", "mock", "live"), default="offline")
    parser.add_argument("--mock-responses", type=Path)
    parser.add_argument("--mock-responses-sha256")
    parser.add_argument("--provider-config", type=Path)
    parser.add_argument("--provider-config-sha256")
    parser.add_argument("--authorize-paid-api", action="store_true")
    parser.add_argument("--workflow", choices=("legacy", "event", "financial", "hotspot", "retrospective"), default="legacy",
                        help="Daily workflows are Mock-only; batch registration is explicit and display-only")
    for name in ("source-requests", "transcription", "metric-workbench", "context"):
        parser.add_argument("--" + name, type=Path)
        parser.add_argument("--" + name + "-sha256")
    args = parser.parse_args()
    if args.discover_contexts:
        if (args.mode != "mock" or args.workflow != "legacy" or args.register_drafts
                or args.authorize_paid_api or any(getattr(args, key) is not None for key in (
                    "batch_plan", "batch_plan_sha256", "symbol", "workbench", "workbench_sha256", "output",
                    "provider_config", "provider_config_sha256", "mock_responses", "mock_responses_sha256",
                    "source_requests", "source_requests_sha256", "transcription", "transcription_sha256",
                    "metric_workbench", "metric_workbench_sha256", "context", "context_sha256"))):
            parser.error("discovery requires --mode mock and cannot run/register jobs or accept provider inputs")
        if bool(args.test_only_retrospective) != bool(args.test_only_retrospective_sha256):
            parser.error("TEST_ONLY retrospective requires both path and sha256")
        pin = None if args.test_only_retrospective is None else dict(
            path=args.test_only_retrospective.as_posix(), sha256=args.test_only_retrospective_sha256)
        result = discover_daily_mock_inputs(root=ROOT, output_directory=args.discovery_output,
            now=datetime.now(timezone.utc), max_hotspots=args.max_hotspots, retrospective=pin)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "READY" else 3 if result["status"] == "PARTIAL" else 2
    if args.test_only_retrospective or args.test_only_retrospective_sha256:
        parser.error("TEST_ONLY retrospective export requires --discover-contexts")
    if args.batch_plan is not None or args.batch_plan_sha256 is not None:
        if not args.batch_plan or not args.batch_plan_sha256 or args.mode != "mock":
            parser.error("batch requires pinned --batch-plan and explicit --mode mock")
        if args.workflow != "legacy" or args.authorize_paid_api or any(
                getattr(args, key) is not None for key in (
                    "symbol", "workbench", "workbench_sha256", "output", "provider_config",
                    "provider_config_sha256", "mock_responses", "mock_responses_sha256",
                    "source_requests", "source_requests_sha256", "transcription", "transcription_sha256",
                    "metric_workbench", "metric_workbench_sha256", "context", "context_sha256")):
            parser.error("batch plan cannot be mixed with single-job/provider arguments")
        result = run_daily_mock_batch(root=ROOT, plan=args.batch_plan,
                                      plan_sha256=args.batch_plan_sha256)
        if args.register_drafts:
            registration = register_daily_draft_results(root=ROOT, batch_result=result,
                                                       now=datetime.now(timezone.utc))
            result["display_registration"] = registration
            result["registered_or_published"] = any(item["status"] in {"REGISTERED", "UNCHANGED"}
                                                    for item in registration["items"])
            result["registration_scope"] = "DISPLAY_ONLY_NOT_RESEARCH_APPROVAL"
            if registration["status"] not in {"UPDATED", "UNCHANGED"} and result["status"] == "SUCCESS":
                result["status"] = "PARTIAL" if result["registered_or_published"] else "BLOCKED"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "SUCCESS" else 3 if result["status"] == "PARTIAL" else 2
    if args.register_drafts:
        parser.error("display registration requires a pinned batch plan")
    if not all((args.symbol, args.workbench, args.workbench_sha256, args.output)):
        parser.error("single job requires symbol, workbench, workbench-sha256 and output")
    if args.workflow != "legacy":
        return _daily_mock(args, parser)
    if any(getattr(args, key) is not None for key in (
            "source_requests", "source_requests_sha256", "transcription", "transcription_sha256",
            "metric_workbench", "metric_workbench_sha256", "context", "context_sha256")):
        parser.error("daily workflow inputs require a non-legacy --workflow")
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
                parser.error("LIVE_LLM_NOT_AUTHORIZED: live mode requires explicit authorization and a pinned provider config")
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
