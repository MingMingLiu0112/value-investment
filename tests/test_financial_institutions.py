from value_investment_agent.financial_institutions import financial_gate_message, provisional_financial_type


def test_only_obvious_financial_issuer_names_get_a_provisional_model() -> None:
    assert provisional_financial_type('平安银行', '待行业映射') == 'bank'
    assert provisional_financial_type('新华保险', None) == 'insurer'
    assert provisional_financial_type('中信证券', None) == 'broker'
    assert provisional_financial_type('贵州茅台', '酿酒行业') is None


def test_financial_gate_never_uses_general_enterprise_signal() -> None:
    action, reason = financial_gate_message('bank')

    assert action == '银行专用模型待核验'
    assert '禁止套用通用企业现金流' in reason
