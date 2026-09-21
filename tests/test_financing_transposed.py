import pytest
from value_investment_agent.financing_transposed import extract_transposed_balances

PAGE = '''金额单位为人民币千元
四 合并财务报表项目附注(续)
(f) 筹资活动产生的各项负债的变动情况
银行借款及其他 应付债券 租赁负债
(含一年内到期) (含一年内到期) (含一年内到期) 合计
2024 年 12 月 31 日 80,245,742 3,266,775 2,947,366 86,459,883
现金变动 (23,204,792) - (1,587,045) (24,791,837)
2025 年 12 月 31 日 61,080,579 3,194,774 3,296,359 67,571,712
(i) 附注
'''


def test_units_and_unknown_movements_are_preserved():
    result = extract_transposed_balances(PAGE)
    assert result['balances'][1]['total_cny'] == '67571712000'
    assert ' - ' in result['movements_raw']
    assert not result['full_movements_reconcile']
    assert not result['complete_debt_verified']
    assert result['statement_scope'] == 'consolidated_note_explicit'


@pytest.mark.parametrize('old,new', [('人民币千元','人民币元'), ('2024 年','2023 年'),
    ('67,571,712','67,571,713'), ('租赁负债\n','其他负债\n'), ('3,194,774','-')])
def test_unknown_scope_or_bad_balances_rejected(old, new):
    assert extract_transposed_balances(PAGE.replace(old, new)) is None


@pytest.mark.parametrize('replacement', ['', '母公司财务报表项目附注', '预测合并财务报表项目附注'])
def test_consolidated_scope_must_be_explicit(replacement):
    assert extract_transposed_balances(PAGE.replace('合并财务报表项目附注', replacement)) is None


def test_conflicting_parent_scope_fails_even_with_consolidated_heading():
    assert extract_transposed_balances(PAGE.replace('(f)', '母公司报表\n(f)')) is None


MOVEMENTS = '''筹资活动产生的现金流量
净额 (23,204,792) - (1,587,045) (24,791,837)
本年支付的借款利息 (1,950,879) (92,897) - (2,043,776)
本年计提的利息 1,959,690 92,861 158,780 2,211,331
其他非现金变动 (i) 4,030,818 (71,965) 1,777,258 5,736,111'''


def movement_page(text=MOVEMENTS):
    return PAGE.replace('现金变动 (23,204,792) - (1,587,045) (24,791,837)', text)


def test_total_movements_do_not_approve_unknown_component_cells():
    result = extract_transposed_balances(movement_page())
    assert result['total_movement_check']['reconciles']
    assert not result['full_movements_reconcile']


@pytest.mark.parametrize('text', [MOVEMENTS.replace('5,736,111', '5,736,112'),
    MOVEMENTS.replace('5,736,111', '-'), MOVEMENTS + '\n额外变动 0 0 0 0'])
def test_mismatch_or_unrecognized_movements_do_not_pass(text):
    assert not extract_transposed_balances(movement_page(text))['total_movement_check']['reconciles']
