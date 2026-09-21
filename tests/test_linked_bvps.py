"""Cross-page joins must stay in the same report and exact period."""
import pytest

from value_investment_agent.historical_bvps import extract_linked_bvps


EQUITY = '''主要会计数据
单位：元 币种：人民币
2023年末 2022年末 本年末比上年末增减 2021年末
调整后 调整前 调整后 调整前
归属于上市公
司股东的净资
产 215,668,571,607.43 197,480,041,239.46 197,506,672,396.00
(二) 主要财务指标
'''
SHARES = '截至2023年12月31日，公司总股本为125,619.78万股'


def test_current_equity_joins_exact_date_and_retains_both_pages():
    row, = extract_linked_bvps([SHARES, EQUITY])
    assert row['input_values']['attributable_net_assets_cny'] == '215668571607.43'
    assert row['input_values']['ending_total_shares'] == '1256197800.00'
    assert row['page'] == 2
    assert row['share_evidence'][0]['page'] == 1
    assert row['period_label'] == '2023-12-31'
    assert not row['comparatives_used']
    assert not row['backtest_ready']
    assert not row['equity_scope_verified']


@pytest.mark.parametrize('shares', [
    '', SHARES.replace('2023', '2024'),
    SHARES.replace('总股本', '参与分红股本'),
    SHARES + '\n' + SHARES.replace('125,619.78', '125,000'),
])
def test_missing_wrong_period_entitlement_or_conflicting_shares_block(shares):
    assert not extract_linked_bvps([shares, EQUITY])


def test_reports_cannot_supply_each_others_missing_evidence():
    assert not extract_linked_bvps([EQUITY])
    assert not extract_linked_bvps([SHARES])


def test_duplicate_agreeing_share_evidence_preserved():
    row, = extract_linked_bvps([SHARES, EQUITY, SHARES])
    assert len(row['share_evidence']) == 2
