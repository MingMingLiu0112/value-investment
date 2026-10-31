"""Opt-in retained-source integration: only the two registered real policies.

No generated financial fixture, source rewriting, network, quote fitting or
private-account access. Temporary variants are mutations of these real inputs.
Pytest keeps its normal system temporary directory. Variant inputs use a unique
repository .tmp directory; each fixture removes only its own directory. Proposal
outputs use a separate temporary runtime directory required by the entrance.
"""
from copy import deepcopy
from decimal import Decimal as D
from datetime import datetime
import json
import os
from pathlib import Path
import socket
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
import pytest

from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.neutral_valuation_proposal import (
    build_neutral_valuation_proposal,
)
from value_investment_agent.application.research.operating_earnings_bridge import (
    research_from_retained_sources,
)
from value_investment_agent.presentation.web_api.app import create_app


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "joint-capital-cash-path-proposal-v2"
PACKAGES = {
    "600519": "runtime/product-cash-allocation-consumer/20261026T090212419386Z/candidate/package.json",
    "600887": "runtime/cc1-companion-replay-20261023-v2-final/600887/package.json",
}
FACTS = "runtime/d2-real-admission-20261011/600887-current-facts-v1/facts.json"
ORIGINAL_SOCKET_CONNECT = socket.socket.connect


def input_path(symbol):
    return ROOT / f"config/research-assumptions/{symbol}-joint-capital-cash-path-v2.json"


def policy_path(symbol):
    return ROOT / f"config/research-proposals/{symbol}-joint-capital-cash-path-v2.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.fixture(autouse=True)
def retained_only(monkeypatch):
    required = [ROOT / p for p in [*PACKAGES.values(), FACTS]]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        reason = "Real retained packages unavailable: " + ", ".join(missing)
        if os.environ.get("JOINT_CASH_TWO_COMPANY_REAL_REQUIRED") == "1":
            pytest.fail(reason)
        pytest.skip(reason)

    def offline(instance, address, *args, **kwargs):
        if (isinstance(address, tuple) and address
                and address[0] in {"127.0.0.1", "::1"}):
            return ORIGINAL_SOCKET_CONNECT(instance, address, *args, **kwargs)
        raise AssertionError("Real replay must use retained sources without network")

    monkeypatch.setattr(socket.socket, "connect", offline)
    monkeypatch.setattr(socket, "create_connection", offline)


def run(symbol, path=None):
    package = ROOT / PACKAGES[symbol]
    policy = path or policy_path(symbol)
    # The production entrance requires output under root/runtime. Keep it
    # isolated and remove the JSON/Markdown after assertions consume the result.
    with TemporaryDirectory(prefix="joint-two-company-real-", dir=ROOT / "runtime") as out:
        return build_neutral_valuation_proposal(
            root=ROOT, package_path=package, package_sha256=sha256_file(package),
            policy_path=policy, policy_sha256=sha256_file(policy),
            output_path=Path(out) / "proposal.json",
        )


@pytest.mark.parametrize("symbol", PACKAGES)
def test_real_official_values_and_hypotheses_are_separate(symbol):
    policy, inputs = load(policy_path(symbol)), load(input_path(symbol))
    package = load(ROOT / PACKAGES[symbol])
    assert policy["schema_version"] == SCHEMA
    assert policy["symbol"] == inputs["symbol"] == package["symbol"] == symbol
    assert inputs["confidence"] == "LOW"
    assert policy["source_package_sha256"] == inputs["package_binding"]["sha256"] == sha256_file(ROOT / PACKAGES[symbol])
    assert policy["rationale_bindings"][0]["sha256"] == sha256_file(input_path(symbol))
    for ref in inputs["source_bindings"]:
        assert sha256_file(ROOT / ref["path"]) == ref["sha256"]
    actual = research_from_retained_sources(root=ROOT, specs=inputs["historical_statement_specs"],
        now=datetime.fromisoformat(inputs["historical_statement_replay"]["observed_at"]))
    assert actual == inputs["historical_statement_replay"]
    lines = actual["ttm"]["lines_cny"]
    assert inputs["observations"]["revenue"]["value"] == lines["operating_revenue"]
    assert inputs["observations"]["parent_profit"]["value"] == lines["parent_profit"]
    assert D(inputs["observations"]["parent_profit"]["value"]) - D(inputs["observations"]["nonrecurring"]["value"]) == D(package["research_case"]["financial_summary"]["ttm_ex_nonrecurring_parent_profit_cny"])
    for key in ("opening_cash", "opening_distribution_capacity", "cash_floor"):
        assert inputs["observations"][key]["classification"] == "ASSUMPTION"
    if symbol == "600887":
        facts = {row["id"]: row for row in load(ROOT / FACTS)["facts"]}
        assert inputs["observations"]["opening_cash"]["value"] == facts["h1_parent_closing_cash_equivalents"]["columns"][0]["value"]
        assert D(lines["minority_profit"]) < 0
        assert D(lines["parent_profit"]) > D(lines["net_profit"])
    for choice in policy["choices"]:
        for scenario in ("bear", "base", "bull"):
            bound = inputs["scenarios"][choice["id"]][scenario]
            assert bound == dict(drivers=choice["joint_drivers"][scenario], terminal_policy=choice["terminal_policy"][scenario], cost_of_equity=choice["cost_of_equity"][scenario])
            assert [row["year"] for row in bound["drivers"]["years"]] == list(range(1, 11))
            assert D(bound["terminal_policy"]["net_maintenance_cash_cny"]) > 0
            assert D(bound["terminal_policy"]["operating_wc_cash_cny"]) > 0
            assert bound["terminal_policy"]["commitment_cash_cny"] == "0"


@pytest.mark.parametrize("symbol", PACKAGES)
def test_real_neutral_entry_consumes_all_ten_year_cash_and_retention(symbol):
    before = {p: sha256_file(p) for p in (ROOT / PACKAGES[symbol], policy_path(symbol), input_path(symbol))}
    result = run(symbol)
    assert result["schema_version"] == result["input_mode"] == SCHEMA
    assert result["cash_funding_status"] == "PASS"
    assert result["action"] == "no_order" and result["normalized_profit"] is None
    assert result["position_guidance"] is None
    for flag in ("assumptions_approved", "g3_approved", "model_validity_approved", "price_admitted", "decision_changed", "canonical_written"):
        assert result[flag] is False
    assert len(result["choices"]) == 3
    for choice in result["choices"]:
        assert choice["valuation"]["status"] == "conditional_research_only"
        for name, ledger in choice["joint_capital_ledgers"].items():
            assert ledger["funding_status"] == "FUNDED"
            rows = ledger["rows"]
            annual = choice["annual_arithmetic"][name]
            assert len(rows) == len(annual["forecast_years"]) == 10
            assert len(choice["actual_calculation_inputs"]["scenarios"][name]["forecast_retentions"]) == 10
            assert abs(D(annual["cash_distribution_crosscheck"]["difference_cny"])) < D("0.01")
            for row, consumed in zip(rows, annual["forecast_years"], strict=True):
                assert abs(D(row["clean_surplus_residual"])) < D("0.01")
                assert abs(D(row["capital_identity_residual"])) < D("0.01")
                for left, right in (("profit", "net_income_assumption_cny"), ("distribution", "dividend_assumption_cny"), ("closing_book", "closing_book_equity_cny")):
                    assert abs(D(row[left]) - D(consumed[right])) < D("0.01")
            assert D(ledger["terminal"]["net_maintenance_cash_cny"]) > 0
            assert D(ledger["terminal"]["operating_wc_cash_cny"]) > 0
        print(symbol, choice["id"], "conditional per share", {k: choice["valuation"][k] for k in ("bear_value", "base_value", "bull_value")})
    assert before == {p: sha256_file(p) for p in before}


def test_two_real_companies_have_distinct_paths_and_valuations():
    a, b = (run(symbol)["choices"][0] for symbol in PACKAGES)
    assert a["joint_capital_ledgers"]["base"]["rows"] != b["joint_capital_ledgers"]["base"]["rows"]
    assert a["valuation"]["base_value"] != b["valuation"]["base_value"]
    assert a["calculation_inputs_sha256"] != b["calculation_inputs_sha256"]


def test_registered_real_candidates_reach_actual_decision_api():
    client = TestClient(create_app(ROOT, port=8791, bootstrap_secret="TEST_ONLY"),
        base_url="http://127.0.0.1:8791", client=("127.0.0.1", 51000))
    for symbol in PACKAGES:
        response = client.get("/api/v1/decisions/" + symbol)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["action"] == "no_order"
        assert body["review_replay"]["status"] == "VERIFIED_NEW_INPUT_CANDIDATE"
        assert body["review_replay"]["formal_eligibility"] is False
        plan = body["decision"]["price_action_plan"]
        assert plan["action"] == "no_order"
        assert plan["candidate_action"] == "NO_ACTION"
        assert plan["action_intent"] is None
        assert plan["research_analysis_status"] == "CONDITIONAL_ANALYSIS_VERIFIED"
        analysis = plan["research_analysis"]
        assert analysis["symbol"] == symbol
        assert analysis["joint_capital_review"]["schema_version"] == "joint-capital-cash-review-v2"
        assert len(analysis["joint_capital_review"]["scenarios"]) == 3


@pytest.fixture
def variant_workspace():
    base = (ROOT / ".tmp").resolve()
    base.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="joint-two-company-variant-", dir=base) as directory:
        workspace = Path(directory).resolve()
        assert workspace.parent == base
        assert workspace.name.startswith("joint-two-company-variant-")
        yield workspace


def variant(symbol, workspace, mutate):
    data, policy = deepcopy(load(input_path(symbol))), deepcopy(load(policy_path(symbol)))
    mutate(data, policy)
    data_file, policy_file = workspace / f"{symbol}-inputs.json", workspace / f"{symbol}-policy.json"
    save(data_file, data)
    binding = policy["rationale_bindings"][0]
    binding.update(path=data_file.relative_to(ROOT).as_posix(), sha256=sha256_file(data_file))
    save(policy_file, policy)
    return data_file, policy_file


@pytest.mark.parametrize("symbol", PACKAGES)
def test_one_assumption_changes_bound_hash_and_result_without_cross_company_pollution(symbol, variant_workspace):
    other = next(s for s in PACKAGES if s != symbol)
    protected = [input_path(s) for s in PACKAGES] + [policy_path(s) for s in PACKAGES] + [ROOT / p for p in PACKAGES.values()]
    before_hashes = {p: sha256_file(p) for p in protected}
    original = run(symbol)["choices"][0]
    unaffected = run(other)["choices"][0]

    def mutate(data, policy):
        choice = policy["choices"][0]
        row = choice["joint_drivers"]["base"]["years"][0]
        row["revenue_growth"] = format(D(row["revenue_growth"]) + D("0.001"), "f")
        data["scenarios"][choice["id"]]["base"]["drivers"]["years"][0]["revenue_growth"] = row["revenue_growth"]

    data_file, policy_file = variant(symbol, variant_workspace, mutate)
    assert sha256_file(data_file) != sha256_file(input_path(symbol))
    assert sha256_file(policy_file) != sha256_file(policy_path(symbol))
    changed = run(symbol, policy_file)["choices"][0]
    assert changed["calculation_inputs_sha256"] != original["calculation_inputs_sha256"]
    assert changed["valuation"]["base_value"] != original["valuation"]["base_value"]
    assert changed["joint_capital_ledgers"]["base"]["rows"] != original["joint_capital_ledgers"]["base"]["rows"]
    repeated = run(other)["choices"][0]
    assert repeated["calculation_inputs_sha256"] == unaffected["calculation_inputs_sha256"]
    assert repeated["valuation"] == unaffected["valuation"]
    assert before_hashes == {p: sha256_file(p) for p in protected}


@pytest.mark.parametrize("symbol", PACKAGES)
@pytest.mark.parametrize("fault", ["missing_maintenance", "missing_year", "wrong_scope", "source_drift"])
def test_real_policy_missing_fields_scope_and_source_drift_are_rejected(symbol, fault, variant_workspace):
    def mutate(data, policy):
        choice = policy["choices"][0]
        if fault == "wrong_scope":
            policy["joint_historical"]["opening_cash"]["scope"] = "consolidated"
            data["observations"]["opening_cash"]["scope"] = "consolidated"
        elif fault == "missing_year":
            choice["joint_drivers"]["base"]["years"].pop()
            data["scenarios"][choice["id"]]["base"]["drivers"]["years"].pop()
        elif fault == "missing_maintenance":
            del choice["joint_drivers"]["base"]["years"][0]["net_maintenance_cash_cny"]
            del data["scenarios"][choice["id"]]["base"]["drivers"]["years"][0]["net_maintenance_cash_cny"]

    _, path = variant(symbol, variant_workspace, mutate)
    if fault == "source_drift":
        policy = load(path)
        policy["rationale_bindings"][0]["sha256"] = "0" * 64
        save(path, policy)
    expected = {
        "missing_maintenance": "Exact joint cash fields required",
        "missing_year": "Exactly ten ordered annual rows required",
        "wrong_scope": "unit/scope/rationale mismatch",
        "source_drift": "rationale path/hash mismatch",
    }[fault]
    with pytest.raises(ValueError, match=expected):
        run(symbol, path)
