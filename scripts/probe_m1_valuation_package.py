"""Build one M1 valuation descriptor and execute it through the shared app."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.m1_valuation_package_builder import (
    build_descriptor,
    load_descriptor_payloads,
)
from value_investment_agent.m1_reverse_valuation import reverse_for_descriptor
from value_investment_agent.research_application import ResearchApplicationService
from value_investment_agent.research_artifact_repository import (
    InMemoryResearchArtifactRepository,
)
from value_investment_agent.research_input import build_research_run_spec


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    args = parser.parse_args(argv)
    payload = load_descriptor_payloads(ROOT)[args.symbol]
    descriptor = build_descriptor(payload, root=ROOT)
    spec = build_research_run_spec(descriptor)
    outcome = ResearchApplicationService(
        InMemoryResearchArtifactRepository()
    ).run_company_research(spec)
    valuation = (
        json.loads(outcome.valuation.to_json())
        if outcome.valuation is not None else None
    )
    print(json.dumps({
        "symbol": descriptor.symbol,
        "input_sha256": descriptor.input_sha256,
        "distribution": (
            descriptor.distribution_result.as_policy()
            if descriptor.distribution_result is not None else None
        ),
        "reverse_valuations": [
            reverse.as_policy()
            for reverse in reverse_for_descriptor(descriptor)
        ],
        "run_status": outcome.status,
        "blockers": outcome.blockers,
        "valuation": valuation,
        "price_bridge": (
            json.loads(outcome.price_bridge.to_json())
            if outcome.price_bridge is not None else None
        ),
        "gate": (
            asdict(outcome.gate)
            if outcome.gate is not None else None
        ),
        "action": getattr(outcome.current_status, "action", None),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
