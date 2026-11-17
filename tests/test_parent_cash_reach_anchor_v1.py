"""The historical cash proxy must not join different periods or originals."""

from copy import deepcopy

from value_investment_agent.application.research.agent_review.parent_cash_reach_anchor_v1 import (
    historical_parent_cash_reach,
)


def _rows():
    base = dict(period="2025-12-31", period_basis="FY", unit="CNY",
                pdf_sha256="a" * 64, available_at="2026-04-01T00:00:00+08:00")
    return [
        dict(base, id="profit", field="parent_profit", scope="consolidated_parent",
             source_id="official:" + "a" * 64, value="100"),
        dict(base, id="cfo", field="cfo_cny", scope="ISSUER_PARENT_STANDALONE",
             source_id="cninfo:report", value="40"),
        dict(base, id="investment", field="investment_income_cash_cny",
             scope="ISSUER_PARENT_STANDALONE", source_id="cninfo:report", value="65"),
        dict(base, id="capex", field="gross_capex_cny", scope="ISSUER_PARENT_STANDALONE",
             source_id="cninfo:report", value="5"),
    ]


def test_same_original_historical_arithmetic_only():
    source = {"evidence": _rows()}
    before = deepcopy(source)
    result = historical_parent_cash_reach(source)
    assert result["scope"] == "HISTORICAL_PARENT_CASH_PROXY_NOT_DISTRIBUTABLE_CASH"
    assert result["action"] == "no_order"
    assert result["observations"][0]["historical_parent_cash_after_gross_capex_cny"] == "100"
    assert result["observations"][0]["historical_cash_proxy_to_profit_ratio"] == "1.0000"
    assert result["observations"][0]["evidence_ids"] == ["profit", "cfo", "investment", "capex"]
    assert "future accessible-profit ratio" in result["limitation"]
    assert source == before


def test_scope_period_source_and_duplicate_conflicts_fail_closed():
    for field, value in (("pdf_sha256", "b" * 64), ("period", "2024-12-31"),
                         ("available_at", "2026-04-02T00:00:00+08:00"),
                         ("scope", "consolidated"), ("source_id", "other")):
        rows = _rows()
        rows[2][field] = value
        assert historical_parent_cash_reach({"evidence": rows}) is None
    rows = _rows()
    rows.append(deepcopy(rows[2]))
    assert historical_parent_cash_reach({"evidence": rows}) is None


def test_no_half_year_extrapolation_or_missing_investment_cash():
    rows = _rows()
    for row in rows:
        row["period"] = "2026-06-30"
        row["period_basis"] = "H1"
    assert historical_parent_cash_reach({"evidence": rows}) is None
    assert historical_parent_cash_reach({"evidence": _rows()[:2] + _rows()[3:]}) is None


def test_future_observation_and_competing_originals_do_not_become_anchor():
    assert historical_parent_cash_reach({"source_as_of": "2026-03-31T00:00:00+08:00",
                                         "evidence": _rows()}) is None
    other = deepcopy(_rows())
    for row in other:
        row["pdf_sha256"] = "b" * 64
        row["id"] += "-other"
    assert historical_parent_cash_reach({"evidence": _rows() + other}) is None
