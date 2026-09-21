from value_investment_agent.financing_year_layout import extract_year_financing
from value_investment_agent.financing_table import TITLE
import pytest

TEXT = '\n'.join(['（除特别注明外，金额单位为人民币元）', TITLE,
    '项目 年初数 本年增加 本年减少 年末数',
    '现金变动 非现金变动 现金变动 非现金变动',
    '一年内到期的 100.0020.00 - 10.00 - 110.00', '非流动负债',
    '合计 100.0020.00 0.00 10.00 0.00 110.00', '（4） 下一节'])


def test_touching_amounts_and_wrapped_label():
    result = extract_year_financing(TEXT)
    assert result['balances_reconcile']
    assert result['rows'][0]['label'] == '一年内到期的非流动负债'
    assert result['rows'][0]['amounts']['noncash_increase'] is None
    assert not result['complete_debt_verified']


@pytest.mark.parametrize('old,new', [('人民币元', '人民币万元'), ('年初数', '年末数'),
    ('非流动负债', '其他行'), ('100.0020.00', '100.00x20.00'), ('110.00', '111.00')])
def test_invalid_scope_or_table_rejected(old,new):
    assert extract_year_financing(TEXT.replace(old,new)) is None
