"""Offline TEST_ONLY successor: sealed pages and typed source replay seams."""

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from pathlib import Path

import pytest

from test_direct_owner_cash_compilation_v1 import sample
from value_investment_agent.application.research import direct_owner_cash_compilation_v1 as compiler
from value_investment_agent.application.research import parent_remaining_year_successor as successor
from value_investment_agent.infrastructure.filings.quarterly_parent_cash_facts import parse_quarterly_parent_cash_facts


ROOT = Path(__file__).resolve().parents[1]
PAGES = json.loads((ROOT / "tests/fixtures/quarterly-parent-operating-600887-pages.json").read_text(encoding="utf-8"))["pages"]
ISSUER = "内蒙古伊利实业集团股份有限公司"
NOW = datetime(2026, 11, 18, tzinfo=timezone.utc)


def write_bound(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(successor._bytes(value))
    return {"path": relative, "sha256": sha256(path.read_bytes()).hexdigest()}


@pytest.fixture
def case(tmp_path, monkeypatch):
    old_spec = sample(monkeypatch)
    old_spec["symbol"] = "600887"
    old_spec["issuer_name"] = ISSUER
    old_spec["source_descriptors"][0]["issuer_identity"].update(
        security_code="600887", organization_id="gssh0600887", issuer_name="伊利股份")
    old_spec["source_descriptors"][0]["location"] = "https://static.cninfo.com.cn/finalpage/2026-04-30/TEST_ONLY.PDF"
    old_spec["source_descriptors"][0]["published_at"] = "2026-04-30T00:00:00+08:00"
    old_operating_reader = compiler.read_parent_direct_cash_research
    monkeypatch.setattr(compiler, "read_parent_direct_cash_research", lambda **kwargs:
        {"observed": [dict(row, symbol="600887")
                      for row in old_operating_reader(**kwargs)["observed"]]})
    compiled = compiler.compile_source_bound_owner_cash(root=tmp_path, spec=old_spec, now=NOW)
    compiled["source_bindings"] = []
    prior = {"compiled": compiled, "source_bindings": [], "symbol": "600887"}
    old_spec_binding = write_bound(tmp_path, "runtime/TEST_ONLY-old-spec.json", old_spec)
    predecessor = write_bound(tmp_path, "runtime/TEST_ONLY-old-receipt.json",
        {"spec_binding": old_spec_binding})
    monkeypatch.setattr(successor, "replay_direct_owner_cash_receipt", lambda **kwargs: deepcopy(prior))
    historical = dict(symbol="600887", scope=compiler.SCOPE, currency="CNY",
        classification="FACT", period_start="2025-01-01", period_end="2025-12-31",
        revenue="104899086044.77", cost="76032892468.00",
        customer_cash="115252588953.58", supplier_cash="96773109786.96",
        cfo="7150459122.43", source_refs=[{"id": "TEST_ONLY_FY"}])
    monkeypatch.setattr(successor, "read_parent_direct_cash_research",
        lambda **kwargs: {"observed": [historical]})
    source_bytes = b"TEST_ONLY original bytes; text supplied by sealed pages fixture"
    source_path = tmp_path / "runtime/TEST_ONLY-quarter.pdf"
    source_path.write_bytes(source_bytes)
    source = dict(path="runtime/TEST_ONLY-quarter.pdf", sha256=sha256(source_bytes).hexdigest(),
        url="https://static.cninfo.com.cn/finalpage/2026-10-30/1225644500.PDF",
        acquired_at="2026-11-18T00:00:00+00:00")
    monkeypatch.setattr(successor, "extract_pages", lambda path: list(PAGES))
    monkeypatch.setattr(successor, "replay_quarterly_parent_cash", lambda **kwargs:
        parse_quarterly_parent_cash_facts(PAGES, symbol="600887", issuer_name=ISSUER,
            period_end="2026-09-30"))
    # The Q4 cash residual is deliberately explicit: the synthetic annual
    # owner policy retains 100 CNY CFO after the reported nine months.
    current_cash = Decimal("39649908007.27")
    q4_revenue = Decimal("10000000000")
    q4_cost = Decimal("10000000000")
    prior_q4_customer = Decimal(historical["customer_cash"]) - Decimal("80433948590.47")
    prior_q4_supplier = Decimal(historical["supplier_cash"]) - Decimal("60220357917.43")
    prior_q4_revenue = Decimal(historical["revenue"]) - Decimal("82629405489.25")
    prior_q4_cost = Decimal(historical["cost"]) - Decimal("59327889043.07")
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        other = Decimal("100") - current_cash - q4_revenue * prior_q4_customer / prior_q4_revenue + q4_cost * prior_q4_supplier / prior_q4_cost
        annual_cfo = current_cash + q4_revenue * prior_q4_customer / prior_q4_revenue - q4_cost * prior_q4_supplier / prior_q4_cost + other
    scenarios = {}
    for name, row in compiled["scenarios"].items():
        years = deepcopy(row["years"])
        years[0]["policy"]["operating_cash"] = str(annual_cfo)
        years[0]["policy"]["maintenance_capex"] = "2000000000"
        years[0]["policy"]["investment_cash_received"] = "5000000000"
        changed = {f"years.2026.policy.{key}": dict(
            classification="FORECAST_ASSUMPTION", evidence_anchors=["Q3_PARENT_9M"],
            rationale="TEST_ONLY exact changed field", counter_evidence="TEST_ONLY downside",
            reopen_condition="TEST_ONLY next source")
            for key, value in years[0]["policy"].items()
            if Decimal(value) != Decimal(row["years"][0]["policy"][key])}
        scenarios[name] = dict(q4_forecast=dict(revenue=str(q4_revenue), cost=str(q4_cost),
            other_operating_cash=str(other), rationale="TEST_ONLY specified residual",
            parent_profit=str(Decimal(years[0]["policy"]["parent_profit"]) - Decimal("11224391992.81")),
            gross_capex=str(Decimal("2000000000") - Decimal("1410074492.50")),
            investment_cash_received=str(Decimal("5000000000") - Decimal("4987544886.74")),
            counter_evidence="TEST_ONLY adverse payments", reopen_condition="TEST_ONLY next report"),
            years=years, terminal=deepcopy(row["terminal"]), cost_of_equity=row["cost_of_equity"],
            field_provenance=changed,
            rationale="TEST_ONLY full policy", counter_evidence="TEST_ONLY capital risk",
            reopen_condition="TEST_ONLY new research")
    spec = dict(schema_version=successor.SCHEMA, action="no_order",
        predecessor_binding=predecessor, quarterly_source=source,
        period_end="2026-09-30", computed_at=NOW.isoformat(),
        research_as_of="2026-11-18", run_id="TEST_ONLY_remaining",
        research_version="TEST_ONLY_remaining", change_rationale="TEST_ONLY explicit",
        counter_evidence="TEST_ONLY reverse case", reopen_condition="TEST_ONLY next report",
        scenarios=scenarios)
    return tmp_path, spec, prior


def test_shared_service_receipt_and_cold_replay(case):
    root, spec, _ = case
    binding = write_bound(root, "runtime/TEST_ONLY-new-spec.json", spec)
    built = successor.build_parent_remaining_year_successor(root=root, spec_binding=binding,
        output_dir=root / "runtime/TEST_ONLY-output", now=NOW)
    result = successor.replay_parent_remaining_year_successor(
        root=root, receipt_binding=built["receipt_binding"], now=NOW)
    assert result["input_descriptor_sha256"] == built["result"]["input_descriptor_sha256"]
    assert result["successor_adopted"] is False
    assert result["symbol"] == "600887"
    assert result["research_case"]["run_id"] == "TEST_ONLY_remaining"
    assert result["compiled"]["scenarios"]["base"]["years"] == spec["scenarios"]["base"]["years"]
    assert result["compiled"]["operating_forecasts"]["base"][0]["annual_components"] == result["annual_recalculations"]["base"]
    assert result["compiled"]["assumptions"]["base"]["field_provenance"] == spec["scenarios"]["base"]["field_provenance"]
    assert result["compiled"]["assumptions"]["base"]["q4_forecast"] == spec["scenarios"]["base"]["q4_forecast"]
    quarter_source = result["package"]["sources"][-1]
    assert quarter_source["kind"] == "quarterly_report"
    assert quarter_source["location"] == spec["quarterly_source"]["url"]
    assert quarter_source["retrieved_at"] == spec["quarterly_source"]["acquired_at"]
    assert quarter_source["issuer_identity"]["issuer_name"] == "伊利股份"
    assert result["research_case"]["name"] == ISSUER
    assert "published_at" not in quarter_source
    assert result["package"]["source_contract"]["quarterly_source_context"] == dict(
        report_period="2026-09-30", published_date_from_official_url="2026-10-30",
        acquired_at=spec["quarterly_source"]["acquired_at"],
        publication_time_verified=False)
    assert result["valuation"]["assumptions"]["scenario_calculations"]["base"]
    assert Decimal(result["package"]["facts"]["scenario_inputs"]["base"]["years"][0]["policy"]["operating_cash"]) == Decimal(spec["scenarios"]["base"]["years"][0]["policy"]["operating_cash"])
    receipt = json.loads((root / built["receipt_binding"]["path"]).read_text(encoding="utf-8"))
    assert receipt["symbol"] == "600887" and receipt["action"] == "no_order"
    assert receipt["source_bindings"] == result["source_bindings"]
    result_path = root / receipt["result_binding"]["path"]
    original_result = result_path.read_bytes()
    result_path.write_bytes(original_result + b"tamper")
    with pytest.raises(ValueError, match="HASH_CHANGED"):
        successor.replay_parent_remaining_year_successor(root=root,
            receipt_binding=built["receipt_binding"], now=NOW)
    result_path.write_bytes(original_result)
    quarter = root / spec["quarterly_source"]["path"]
    quarter.write_bytes(quarter.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        successor.replay_parent_remaining_year_successor(root=root,
            receipt_binding=built["receipt_binding"], now=NOW)


@pytest.mark.parametrize("fault,error", [
    ("missing_reason", "EXPLAINED_Q4_ASSUMPTIONS"),
    ("missing_year", "ALL_ANNUAL_PERIODS_REQUIRED"),
    ("profit", "PROFIT_NOT_RECONCILED"),
    ("capex", "CAPEX_NOT_RECONCILED"),
    ("investment", "INVESTMENT_RECEIPTS_NOT_RECONCILED"),
    ("future_research", "TIME_OR_REASON_INVALID"),
    ("missing_provenance", "CHANGED_FIELD_PROVENANCE_REQUIRED"),
    ("bad_anchor", "CHANGED_FIELD_EVIDENCE_INVALID"),
    ("changed_cost", "CHANGED_FIELD_PROVENANCE_REQUIRED"),
    ("changed_terminal", "CHANGED_FIELD_PROVENANCE_REQUIRED"),
])
def test_incomplete_or_unreconciled_inputs_rejected(case, fault, error):
    root, spec, _ = case
    if fault == "missing_reason":
        spec["scenarios"]["base"]["q4_forecast"]["counter_evidence"] = ""
    elif fault == "missing_year":
        spec["scenarios"]["base"]["years"] = []
    elif fault == "profit":
        spec["scenarios"]["base"]["q4_forecast"]["parent_profit"] = "0"
    elif fault == "capex":
        spec["scenarios"]["base"]["q4_forecast"]["gross_capex"] = "0"
    elif fault == "investment":
        spec["scenarios"]["base"]["q4_forecast"]["investment_cash_received"] = "0"
    elif fault == "missing_provenance":
        spec["scenarios"]["base"]["field_provenance"] = {}
    elif fault == "bad_anchor":
        next(iter(spec["scenarios"]["base"]["field_provenance"].values()))["evidence_anchors"] = ["UNKNOWN"]
    elif fault == "changed_cost":
        spec["scenarios"]["base"]["cost_of_equity"] = "0.09"
    elif fault == "changed_terminal":
        spec["scenarios"]["base"]["terminal"]["max_transition_years"] = 99
    else:
        spec["research_as_of"] = "2026-11-19"
    binding = write_bound(root, "runtime/TEST_ONLY-bad-spec.json", spec)
    with pytest.raises(ValueError, match=error):
        successor.build_parent_remaining_year_successor(root=root, spec_binding=binding,
            output_dir=root / "runtime/TEST_ONLY-bad-output", now=NOW)


def test_disclosed_maturity_floor_precedes_domain_cash_compilation(case):
    root, spec, prior = case
    prior["compiled"]["evidence"]["constraints"] = {"issued_financing": [dict(
        classification="FACT", scope="ISSUER_FINANCING_DISCLOSURE", currency="CNY",
        code="TEST_ONLY_BOND", maturity="2026-12-30", principal_cny="100",
        outstanding_at_evaluation_cny="100", actual_settlement_verified=False)]}
    binding = write_bound(root, "runtime/TEST_ONLY-maturity-spec.json", spec)
    with pytest.raises(ValueError, match="DIRECT_INPUT_FINANCING_MATURITY_UNCOVERED"):
        successor.build_parent_remaining_year_successor(root=root, spec_binding=binding,
            output_dir=root / "runtime/TEST_ONLY-maturity-output", now=NOW)


def test_later_year_operating_cash_cannot_bypass_predecessor_forecast(case):
    root, spec, prior = case
    for name in ("bear", "base", "bull"):
        old_year = deepcopy(prior["compiled"]["scenarios"][name]["years"][0])
        old_year["year"] = 2027
        prior["compiled"]["scenarios"][name]["years"].append(old_year)
        prior["compiled"]["operating_forecasts"][name].append(
            deepcopy(prior["compiled"]["operating_forecasts"][name][0]))
        new_year = deepcopy(old_year)
        if name == "base":
            new_year["policy"]["operating_cash"] = "101"
        spec["scenarios"][name]["years"].append(new_year)
    binding = write_bound(root, "runtime/TEST_ONLY-later-cash-spec.json", spec)
    with pytest.raises(ValueError, match="LATER_OPERATING_FORECAST_MUST_INHERIT"):
        successor.build_parent_remaining_year_successor(root=root, spec_binding=binding,
            output_dir=root / "runtime/TEST_ONLY-later-cash-output", now=NOW)


@pytest.mark.parametrize("fault", ["organization_id", "issuer_name", "security_code",
                                  "venue", "location"])
def test_predecessor_registered_identity_rejects_wrong_official_metadata(case, fault):
    root, spec, _ = case
    receipt_path = root / spec["predecessor_binding"]["path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    old_spec_path = root / receipt["spec_binding"]["path"]
    old_spec = json.loads(old_spec_path.read_text(encoding="utf-8"))
    descriptor = old_spec["source_descriptors"][0]
    if fault == "location":
        descriptor["location"] = "https://unregistered.example.com/TEST_ONLY.PDF"
    else:
        descriptor["issuer_identity"][fault] = {
            "organization_id": "wrong-org", "issuer_name": "错误股份",
            "security_code": "600519", "venue": "SSE"}[fault]
    receipt["spec_binding"] = write_bound(root, receipt["spec_binding"]["path"], old_spec)
    spec["predecessor_binding"] = write_bound(root, spec["predecessor_binding"]["path"], receipt)
    binding = write_bound(root, "runtime/TEST_ONLY-wrong-identity-spec.json", spec)
    with pytest.raises(ValueError, match="SUCCESSOR_PREDECESSOR_ISSUER_IDENTITY_MISMATCH"):
        successor.build_parent_remaining_year_successor(root=root, spec_binding=binding,
            output_dir=root / "runtime/TEST_ONLY-wrong-identity-output", now=NOW)


def test_exact_48_digit_capex_split_accepts_and_one_digit_change_rejects(case):
    root, spec, _ = case
    maintenance = "1000000000.12345678901234567890123456789012345"
    growth = "1000000000"
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        q4_gross = str(Decimal(maintenance) + Decimal(growth) - Decimal("1410074492.50"))
    declaration = dict(classification="FORECAST_ASSUMPTION",
        evidence_anchors=["Q3_PARENT_9M"], rationale="TEST_ONLY exact split",
        counter_evidence="TEST_ONLY alternative capex", reopen_condition="TEST_ONLY new filing")
    for row in spec["scenarios"].values():
        row["years"][0]["policy"].update(maintenance_capex=maintenance, growth_capex=growth)
        row["q4_forecast"]["gross_capex"] = q4_gross
        row["field_provenance"]["years.2026.policy.growth_capex"] = declaration
    binding = write_bound(root, "runtime/TEST_ONLY-precise-spec.json", spec)
    with localcontext() as caller_arithmetic:
        caller_arithmetic.prec = 12
        built = successor.build_parent_remaining_year_successor(root=root, spec_binding=binding,
            output_dir=root / "runtime/TEST_ONLY-precise-output", now=NOW)
    assert successor.replay_parent_remaining_year_successor(
        root=root, receipt_binding=built["receipt_binding"], now=NOW)["symbol"] == "600887"
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        spec["scenarios"]["base"]["q4_forecast"]["gross_capex"] = str(
            Decimal(q4_gross) + Decimal("0.00000000000000000000000000000000001"))
    bad = write_bound(root, "runtime/TEST_ONLY-precise-bad-spec.json", spec)
    with pytest.raises(ValueError, match="SUCCESSOR_CAPEX_NOT_RECONCILED"):
        successor.build_parent_remaining_year_successor(root=root, spec_binding=bad,
            output_dir=root / "runtime/TEST_ONLY-precise-bad-output", now=NOW)


def test_quarterly_financing_opt_in_replays_parent_only_and_rejects_missing_row(tmp_path, monkeypatch):
    from value_investment_agent.application.research.agent_review import quarterly_parent_cash_source as source

    original = write_bound(tmp_path, "runtime/TEST_ONLY-financing-original.json", {"fixture": True})
    original.update(
        url="https://static.cninfo.com.cn/finalpage/2026-10-30/1225644500.PDF",
        acquired_at=NOW.isoformat(),
    )
    kwargs = dict(root=tmp_path, source=original, symbol="600887", issuer_name=ISSUER,
                  period_end="2026-09-30", now=NOW)
    pages = list(PAGES)
    monkeypatch.setattr(source, "extract_pages", lambda path: pages)
    legacy = source.replay_quarterly_parent_cash(**kwargs)
    observed = source.replay_quarterly_parent_cash(**kwargs, include_financing=True)
    financing = observed.pop("financing")
    assert observed == legacy
    assert financing["borrowings_received_cny"]["current"] == "182711547658.23"
    repayment = financing["debt_repayments_paid_cny"]
    assert repayment["current"] == "202501881888.99"
    assert repayment["comparative"] == "128240500000.00"
    assert repayment["scope"] == "ISSUER_PARENT_STANDALONE"
    assert repayment["physical_page"] == legacy["fields"]["cfo"]["physical_page"]
    index = repayment["physical_page"] - 1
    pages[index] = pages[index].replace(repayment["excerpt"], "")
    assert source.replay_quarterly_parent_cash(**kwargs) == legacy
    with pytest.raises(ValueError, match="PARENT_QUARTER_FINANCING_ROW_MISSING_OR_AMBIGUOUS"):
        source.replay_quarterly_parent_cash(**kwargs, include_financing=True)
