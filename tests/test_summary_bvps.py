import pytest
from value_investment_agent.historical_bvps import extract_summary_bvps

PAGE = '''主要会计数据
单位：元 币种：人民币
2018年末 2017年末
归属于上市公司股东的净资产 112,838,564,332.05 91,451,522,828.96
总资产 159,846,674,736.01 134,610,116,875.08
期末总股本 1,256,197,800.00 1,256,197,800.00
(二) 主要财务指标
'''


def test_same_period_summary_derivation_retains_inputs_not_approval():
    row, = extract_summary_bvps([PAGE])
    assert row['value'] == '89.82547520147702853802163959'
    assert row['period_label'] == '2018-12-31'
    assert row['input_values']['ending_total_shares'] == '1256197800.00'
    assert not row['equity_scope_verified']


@pytest.mark.parametrize('old,new', [
    ('单位：元', '单位：万元'), ('2018年末 2017年末', '2017年末 2018年末'),
    ('期末总股本', '股本'), ('归属于上市公司股东的净资产', '所有者权益合计'),
    ('1,256,197,800.00', '0.00'), ('1,256,197,800.00', '1,256,197,800.50'),
])
def test_wrong_scope_units_dates_or_share_count_reject(old, new):
    assert extract_summary_bvps([PAGE.replace(old,new)]) == []


def test_no_cross_page_or_next_section_join():
    before, after = PAGE.split('期末总股本')
    assert not extract_summary_bvps([before, '期末总股本'+after])
    assert not extract_summary_bvps([before+'(二) 下一节\n期末总股本'+after])
