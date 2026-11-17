from copy import deepcopy
from decimal import Decimal
import pytest
from value_investment_agent.domain.research.liability_settlement_schedule_v1 import compile_liability_settlements

def sample():
    return [
        dict(obligation_id="debt", opening_balance_cny="100", payment_year=1, source_refs=[{"id":"TEST_ONLY"}]),
        dict(obligation_id="declared_dividend", opening_balance_cny="50", payment_year=2, source_refs=[{"id":"TEST_ONLY"}]),
        dict(obligation_id="unpaid", opening_balance_cny="30", payment_year=None, source_refs=[{"id":"TEST_ONLY"}]),
    ]

def test_payments_reduce_liabilities_once_not_new_dividends_or_productive_assets():
    inputs=sample(); before=deepcopy(inputs)
    result=compile_liability_settlements(obligations=inputs)
    assert inputs==before
    assert result["classification"]=="NONPRODUCTIVE_LIABILITY_SETTLEMENT"
    assert result["new_shareholder_distribution"] is False
    assert result["productive_capital_addition"] is False
    assert result["terminal_outstanding_cny"]=="30"
    assert [r["payment_cny"] for r in result["rows"]]==["100","50"]+["0"]*8
    for row in result["rows"]:
        assert Decimal(row["opening_outstanding_cny"])-Decimal(row["payment_cny"])==Decimal(row["closing_outstanding_cny"])
    assert result["action"]=="no_order" and result["maturity_dates_proven"] is False

@pytest.mark.parametrize("amount",["-1","NaN","Infinity",True,None,[],1.2])
def test_invalid_amount_rejected(amount):
    rows=sample(); rows[0]["opening_balance_cny"]=amount
    with pytest.raises(ValueError): compile_liability_settlements(obligations=rows)

@pytest.mark.parametrize("year",[True,0,-1,11,1.1,"1"])
def test_invalid_payment_year_rejected(year):
    rows=sample(); rows[0]["payment_year"]=year
    with pytest.raises(ValueError): compile_liability_settlements(obligations=rows)

def test_duplicated_book_liability_cannot_be_paid_twice():
    rows=sample(); rows.append(deepcopy(rows[0]))
    with pytest.raises(ValueError,match="UNIQUE"): compile_liability_settlements(obligations=rows)

def test_missing_source_or_extra_field_rejected():
    for damage in ("source","extra"):
        rows=sample()
        if damage=="source": rows[0]["source_refs"]=[]
        else: rows[0]["future_interest"]="999"
        with pytest.raises(ValueError): compile_liability_settlements(obligations=rows)
