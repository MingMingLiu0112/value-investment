from decimal import Decimal
import pytest
from value_investment_agent.application.research.quarter_income_facts_v2 import _row_value

def row(text,x,y,confidence=.999):
    return {"text":text,"confidence":confidence,"box":[[x,y],[x+150,y],[x+150,y+20],[x,y+20]]}

def test_repeated_net_profit_uses_row_geometry_and_reconciles_occurrences():
    rows=[row("五、净利润",300,100),row("66,717.04",900,120),
          row("1.持续经营净利润",300,250),row("66,717.04",900,270)]
    assert _row_value(rows,"五、净利润","66,717.04 66,717.04",2026)==Decimal("66717.04")

def test_missing_native_occurrence_is_rejected():
    rows=[row("五、净利润",300,100),row("66,717.04",900,120),row("66,717.04",900,270)]
    with pytest.raises(ValueError,match="NATIVE_NUMBER_AMBIGUOUS"):
        _row_value(rows,"五、净利润","66,717.04",2026)

def test_same_row_duplicate_is_rejected():
    rows=[row("五、净利润",300,100),row("66,717.04",900,120),row("66,717.04",950,121)]
    with pytest.raises(ValueError,match="AMOUNT_UNVERIFIED"):
        _row_value(rows,"五、净利润","66,717.04 66,717.04",2026)

def test_low_confidence_is_not_silently_accepted():
    rows=[row("2.少数股东损益",300,100),row("2,249.09",900,120,.97053)]
    with pytest.raises(ValueError,match="AMOUNT_UNVERIFIED"):
        _row_value(rows,"2.少数股东损益","2,249.09",2026)

def test_complete_native_row_independently_verifies_low_confidence_amount():
    rows=[row("2.少数股东损益",300,100),row("2,249.09",900,120,.97053)]
    assert _row_value(rows,"2.少数股东损益",
                      "2.少数股东损益（净亏损以负号填列）\n2,249.09 2,272.99",2026)==Decimal("2249.09")

def test_different_native_row_cannot_rescue_low_confidence_amount():
    rows=[row("2.少数股东损益",300,100),row("2,249.09",900,120,.97053)]
    with pytest.raises(ValueError,match="AMOUNT_UNVERIFIED"):
        _row_value(rows,"2.少数股东损益","其他项目 2,249.09 2,272.99",2026)
