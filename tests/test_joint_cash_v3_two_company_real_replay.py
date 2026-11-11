"""Opt-in real-source v3 reuse and cross-company isolation acceptance."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.neutral_valuation_proposal import (
    build_neutral_valuation_proposal,
)
from value_investment_agent.application.product.pending_research_candidate import (
    prepare_pending_research_candidate,
    verify_pending_research_candidate,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "joint-capital-cash-path-proposal-v3"
CASES = {
    "600519": (
        "runtime/product-cash-allocation-consumer/20261026T090212419386Z/candidate/package.json",
        "ADVANTAGE_CONTINUITY",
    ),
    "600887": (
        "runtime/cc1-companion-replay-20261023-v2-final/600887/package.json",
        "DAIRY_STABILIZATION",
    ),
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def policy_path(symbol: str) -> Path:
    return ROOT / f"config/research-proposals/{symbol}-joint-capital-cash-path-v3.json"


def input_path(symbol: str) -> Path:
    return ROOT / f"config/research-assumptions/{symbol}-joint-capital-cash-path-v3.json"


@pytest.fixture(autouse=True)
def retained_sources_required():
    required = [ROOT / package for package, _ in CASES.values()]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        reason = "v3 retained-source prerequisites unavailable: " + ", ".join(missing)
        if os.environ.get("JOINT_CASH_V3_REAL_REQUIRED") == "1":
            pytest.fail(reason)
        pytest.skip(reason)


def proposal(symbol: str, output: Path, policy: Path | None = None):
    package = ROOT / CASES[symbol][0]
    chosen = policy or policy_path(symbol)
    return build_neutral_valuation_proposal(
        root=ROOT,
        package_path=package,
        package_sha256=sha256_file(package),
        policy_path=chosen,
        policy_sha256=sha256_file(chosen),
        output_path=output,
    )


def candidate(symbol: str, output: Path):
    package = ROOT / CASES[symbol][0]
    policy = policy_path(symbol)
    request = {
        "schema_version": "research-schedule-request-v1",
        "symbol": symbol,
        "source_id": "CNINFO",
        "period": load(package)["point_in_time"]["report_period"],
        "research_question_id": "TEST_ONLY_v3_real_replay",
        "blocker_id": "none",
        "reopen_condition_met": False,
        "new_evidence_ids": [],
    }
    request_hash = sha256(json.dumps(
        request, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    result = prepare_pending_research_candidate(
        root=ROOT,
        package_path=package,
        package_sha256=sha256_file(package),
        policy_path=policy,
        policy_sha256=sha256_file(policy),
        choice_id=CASES[symbol][1],
        output_dir=output,
        schedule_request=request,
        schedule_request_sha256=request_hash,
    )
    verified = verify_pending_research_candidate(
        root=ROOT,
        path=output / "candidate.json",
        expected_sha256=sha256_file(output / "candidate.json"),
    )
    assert verified == result
    return result


def test_two_real_companies_use_one_v3_shared_consumption_path():
    with TemporaryDirectory(prefix="joint-v3-real-", dir=ROOT / "runtime") as directory:
        base = Path(directory)
        results = {symbol: candidate(symbol, base / symbol) for symbol in CASES}
    for symbol, result in results.items():
        assert result["symbol"] == symbol
        assert result["input_mode"] == SCHEMA
        assert result["model_context_scope"] == "ACTUALLY_CONSUMED"
        assert result["candidate_valuation"]["model_version"] == "residual-income-equity-path-v3"
        assert result["action"] == "no_order"
        assert result["research_admitted"] is False and result["position_guidance"] is None
    assert results["600519"]["model_context"] != results["600887"]["model_context"]
    assert results["600519"]["candidate_valuation"] != results["600887"]["candidate_valuation"]


def test_600519_legal_input_revision_does_not_change_600887():
    protected = [policy_path(symbol) for symbol in CASES] + [input_path(symbol) for symbol in CASES]
    before = {path: sha256_file(path) for path in protected}
    with TemporaryDirectory(prefix="joint-v3-update-", dir=ROOT / ".tmp") as scratch_name, \
            TemporaryDirectory(prefix="joint-v3-proposal-", dir=ROOT / "runtime") as output_name:
        scratch, output = Path(scratch_name), Path(output_name)
        first_519 = proposal("600519", output / "600519-before.json")
        first_887 = proposal("600887", output / "600887-before.json")

        inputs = deepcopy(load(input_path("600519")))
        policy = deepcopy(load(policy_path("600519")))
        scenario = inputs["scenarios"]["ADVANTAGE_CONTINUITY"]["base"]
        scenario["drivers"]["new_operating_return"] = "0.055"
        chosen = next(row for row in policy["choices"] if row["id"] == "ADVANTAGE_CONTINUITY")
        chosen["joint_drivers"]["base"]["new_operating_return"] = "0.055"
        revised_input = scratch / "600519-v3-revised-input.json"
        revised_policy = scratch / "600519-v3-revised-policy.json"
        save(revised_input, inputs)
        binding = policy["rationale_bindings"][0]
        binding.update(path=revised_input.relative_to(ROOT).as_posix(),
                       sha256=sha256_file(revised_input))
        save(revised_policy, policy)

        changed_519 = proposal("600519", output / "600519-after.json", revised_policy)
        second_887 = proposal("600887", output / "600887-after.json")

    selected_before = next(row for row in first_519["choices"]
                           if row["id"] == "ADVANTAGE_CONTINUITY")
    selected_after = next(row for row in changed_519["choices"]
                          if row["id"] == "ADVANTAGE_CONTINUITY")
    assert selected_after["calculation_inputs_sha256"] != selected_before["calculation_inputs_sha256"]
    assert selected_after["valuation"] != selected_before["valuation"]
    assert second_887["choices"] == first_887["choices"]
    assert before == {path: sha256_file(path) for path in protected}
