from scripts.current.audit_tracked_xlsx_privacy import classify


def test_private_context_takes_precedence():
    assert classify("1234567890123456", context="股票账户 总资产", cell_type="n", number_format="General", formula=False) == "REQUIRES_PRIVATE_REVIEW"


def test_public_financial_context_requires_numeric_cell():
    assert classify("1234567890123456", context="营业收入", cell_type="n", number_format="General", formula=False) == "POTENTIAL_PUBLIC_FINANCIAL_OR_MARKET_VALUE"
    assert classify("1234567890123456", context="营业收入", cell_type="s", number_format="General", formula=False) == "UNKNOWN_LONG_NUMERIC"


def test_unlabeled_number_stays_unknown():
    assert classify("1234567890123456", context="Sheet1", cell_type="n", number_format="General", formula=False) == "UNKNOWN_LONG_NUMERIC"
