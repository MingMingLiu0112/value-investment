"""TEST_ONLY numbered-source compiler integration with the existing cash domain."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from value_investment_agent.application.research import direct_owner_cash_compilation_v2 as compiler
from test_direct_owner_cash_compilation_v1 import sample


NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)


def _numbered_spec(monkeypatch):
    spec = sample(monkeypatch)
    spec["source_adapter_version"] = "NUMBERED_CNINFO_V2"
    spec["operating_sources"] = []
    spec["ordinary_shares"]["classification"] = "DERIVED_FACT"
    statement = {
        "period_start": "2025-01-01", "period_end": "2025-12-31",
        "period_basis": "FY", "symbol": spec["symbol"],
        "scope": compiler.SCOPE, "currency": "CNY",
        "balance_sheet": {}, "income": {}, "cash_flow": {},
        "ordinary_shares_evidence": {
            "classification": "DERIVED_FACT", "period_end": "2025-12-31",
            "unit": "shares", "scope": "TOTAL_ISSUED_ORDINARY_SHARES",
            "count": "100", "source_refs": [{"path": "runtime/TEST_ONLY.pdf",
                                              "sha256": "a" * 64}]},
    }
    row_ref = {"path": "runtime/TEST_ONLY.pdf", "sha256": "a" * 64,
               "physical_page": 1, "excerpt": "TEST_ONLY"}
    for name, ref in spec["fact_anchors"].items():
        value = ("1000" if name == "book_equity_cny" else
                 "20" if name == "closing_cash_and_equivalents_cny" else
                 "80" if name == "profit" else "100")
        statement[ref["section"]][ref["field"]] = {
            "current": value, "comparative": value,
            "source_refs": row_ref,
        }
    statement["income"].update(
        revenue={"current": "200", "source_refs": row_ref},
        cost={"current": "100", "source_refs": row_ref})
    statement["cash_flow"].update(
        customer_cash_cny={"current": "200", "source_refs": row_ref},
        supplier_cash_cny={"current": "100", "source_refs": row_ref},
        cfo_cny={"current": "100", "source_refs": row_ref})
    monkeypatch.setattr(compiler, "read_parent_direct_owner_cash_sources_v2",
                        lambda **_kwargs: {"statements": [statement],
                                           "constraints": None})
    return spec, statement


@pytest.mark.parametrize("share_class", ["FACT", "DERIVED_FACT"])
def test_numbered_report_compiles_existing_cash_model(monkeypatch, tmp_path, share_class):
    spec, statement = _numbered_spec(monkeypatch)
    spec["ordinary_shares"]["classification"] = share_class
    statement["ordinary_shares_evidence"]["classification"] = share_class
    result = compiler.compile_source_bound_owner_cash_v2(
        root=tmp_path, spec=spec, now=NOW)
    assert result["ordinary_shares"] == "100"
    assert result["scenarios"]["base"]["years"][0]["policy"]["operating_cash"] == "100"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False


def test_numbered_report_rejects_share_and_cash_source_gaps(monkeypatch, tmp_path):
    spec, statement = _numbered_spec(monkeypatch)
    wrong = deepcopy(spec)
    wrong["ordinary_shares"]["classification"] = "FACT"
    with pytest.raises(ValueError, match="SHARE_UNIT_SCOPE_OR_PROOF_MISSING"):
        compiler.compile_source_bound_owner_cash_v2(root=tmp_path, spec=wrong, now=NOW)
    del statement["cash_flow"]["customer_cash_cny"]
    with pytest.raises(ValueError, match="NUMBERED_OPERATING_FACT_MISSING"):
        compiler.compile_source_bound_owner_cash_v2(root=tmp_path, spec=spec, now=NOW)


def test_quarter_bridge_is_consumed_and_source_is_retained(monkeypatch, tmp_path):
    from value_investment_agent.application.research.agent_review import quarterly_parent_cash_source

    spec, _ = _numbered_spec(monkeypatch)
    spec["first_year_operating_cash_method"] = "OBSERVED_9M_PLUS_CONDITIONAL_Q4_V1"
    source = {"path": "runtime/TEST_ONLY_q3.pdf", "sha256": "b" * 64}
    calls = []

    def project(*, forecast, **kwargs):
        calls.append(forecast["period_end"])
        if not forecast["period_end"].startswith("2026-"):
            return compiler.forecast_parent_operating_cash(
                historical=kwargs["historical"], forecast=forecast)
        return {
            "operating_cash": "101",
            "assumptions": forecast,
            "remaining_year_bridge": {"quarter_source": source},
        }

    monkeypatch.setattr(quarterly_parent_cash_source, "project_parent_annual_operating_cash", project)
    result = compiler.compile_source_bound_owner_cash_v2(root=tmp_path, spec=spec, now=NOW)
    assert calls.count("2026-12-31") == 3
    for scenario, detail in result["scenarios"].items():
        assert detail["years"][0]["policy"]["operating_cash"] == "101"
        assert result["operating_forecasts"][scenario][0]["assumptions"]["revenue"]
    assert source in result["source_bindings"]
    assert result["action"] == "no_order" and result["formal_eligibility"] is False



def test_bound_distribution_is_consumed_before_valuation(monkeypatch, tmp_path):
    from value_investment_agent.application.research import parent_owner_distribution_successor_v2

    spec, _ = _numbered_spec(monkeypatch)
    binding = {"path": "runtime/TEST_ONLY_distribution.json", "sha256": "b" * 64}
    report = {"symbol": spec["symbol"], "distribution": {"paid_date": "2026-06-05", "total_cny": "1"},
              "distribution_evidence": {"notice": {"path": "runtime/TEST_ONLY_notice.pdf", "sha256": "c" * 64}}}

    def replay(**kwargs):
        assert kwargs == {"root": tmp_path, "receipt_binding": binding, "now": NOW}
        return report

    monkeypatch.setattr(parent_owner_distribution_successor_v2,
                        "replay_parent_owner_distribution_successor", replay)
    result = compiler.compile_source_bound_owner_cash_v2(
        root=tmp_path, spec=spec, now=NOW, implemented_distribution=binding)
    for scenario in result["scenarios"].values():
        assert scenario["calculation"]["annual_rows"][0]["scheduled_owner_distribution_cny"] == "1"
    assert binding in result["source_bindings"]
    report["distribution"]["paid_date"] = "2026-12-01"
    with pytest.raises(ValueError, match="IMPLEMENTED_DISTRIBUTION_MISMATCH"):
        compiler.compile_source_bound_owner_cash_v2(
            root=tmp_path, spec=spec, now=NOW, implemented_distribution=binding)




def test_optional_payout_reserves_next_year_debt_without_changing_cash_floor():
    from decimal import Decimal
    from test_direct_parent_owner_cash_v1 import inputs
    from value_investment_agent.domain.valuation.direct_parent_owner_cash_v2 import compile_direct_owner_cash_path

    data = inputs()
    data["opening"].update(cash="40", debt="15", capacity="80")
    first = deepcopy(data["years"][0])
    first["policy"].update(operating_cash="20", cash_floor="20", payout_ratio="0.5")
    first["scheduled_owner_distribution_cny"] = "5"
    second = deepcopy(first)
    second.update(year=first["year"] + 1, scheduled_owner_distribution_cny="0")
    second["policy"].update(debt_repayment="15", payout_ratio="0")
    data["years"] = [first, second]

    reservations = compiler._reserve_annual_cash_before_optional_payout(
        data["opening"], data["years"], Decimal(data["ordinary_shares"]),
        Decimal(data["cost_of_equity"]))
    assert Decimal(reservations[0]["target_ratio"]) == Decimal("0.5")
    assert Decimal(reservations[0]["applied_ratio"]) == 0
    assert Decimal(reservations[0]["minimum_closing_cash_cny"]) == 35
    assert Decimal(reservations[0]["original_cash_floor_cny"]) == 20
    result = compile_direct_owner_cash_path(**data)
    assert Decimal(result["annual_rows"][0]["scheduled_owner_distribution_cny"]) == 5
    assert Decimal(result["annual_rows"][0]["conditional_distribution_cny"]) == 0
    assert Decimal(result["annual_rows"][1]["closing_cash_cny"]) == 20
    assert first["policy"]["cash_floor"] == "20"
