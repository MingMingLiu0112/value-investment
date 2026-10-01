from dataclasses import replace
from test_product_workbench_read_model import _payload
from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload
from value_investment_agent.presentation.read_models.conditional_expectations import render_company_review_cards


def test_reading_order_exposes_counterevidence_before_audit_and_preserves_all_details():
    model = product_workbench_from_payload(_payload())
    card = model.companies[0]
    details = (('核心研究论点（非买入批准）', 'Brand thesis, not approval'),
        ('最强反证', 'Profit declined; historical ROE is not forecast ROE'),
        ('经营现金流变化合计（描述性）', '-73.96亿元'),
        ('股息记录 FY2025-final 实施公告记录', '0.90 CNY; unknown. 原件：runtime/dividend.pdf；SHA256=abc'),
        ('待复核公告 123 回购', 'Pending review, not intrinsic value'),
        ('财报原件入口（fixture）', 'https://example.test/original.pdf'))
    model = replace(model, companies=(replace(card, decision_review=details),))
    text = render_company_review_cards(model)
    assert text.index('先看研究结论与反证') < text.index('为什么目前不能作为买入依据')
    assert text.index('现金与股息摘要') < text.index('公告原件与待复核事项')
    quick = text.split('### 现金与股息摘要')[1].split('### 决策过程')[0]
    assert 'runtime/dividend.pdf' not in quick
    assert 'unknown' in quick
    for label, value in details:
        assert f'{label}：{value}' in text
    assert 'action=no_order' in text


def test_missing_cash_research_is_explicit_not_zero_yield():
    model = product_workbench_from_payload(_payload())
    model = replace(model, companies=(replace(model.companies[0], decision_review=()),))
    assert '尚未接入已核验的现金与股息研究' in render_company_review_cards(model)
