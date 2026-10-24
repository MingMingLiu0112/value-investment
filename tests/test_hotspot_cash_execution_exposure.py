"""TEST_ONLY fixtures; optional actual source replay never grants PIT or trading."""
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.infrastructure.hotspot.sse_cash_entitlement import parse_sse_cash_entitlement
from value_investment_agent.application.hotspot import cash_execution_exposure as app
from value_investment_agent.quote_sessions import CHINA

PAGES = [
    '证券代码：000001 证券简称：TEST_ONLY 公告编号：临2026-027\n'
    '2025年年度权益分派实施公告 A股每股现金红利2元 差异化分红送转：否\n'
    '股份类别 股权登记日 最后交易日 除权（息）日 现金红利发放日\n'
    'A股 2026/6/25 － 2026/6/26 2026/6/26',
    '（三）分配方案：本次利润分配以方案实施前的公司总股本扣除回购专用账户内的股份'
    '100股为基数，每股派发现金红利2元（含税），共计派发现金红利200元。三、相关日期\n'
    'TEST_ONLY董事会2026年6月22日',
]


def test_explicit_eligible_shares_are_not_total_shares_or_ex_reference():
    with pytest.raises(ValueError, match='Explicit A-share subtotal'):
        parse_sse_cash_entitlement(PAGES, symbol='000001')


def _ah_pages():
    pages = deepcopy(PAGES)
    pages[1] = ('3.分配方案：本次利润分配以方案实施前的公司总股本1000股为基数，'
        '向全体股东每股派发现金红利人民币2元（含税），共计派发现金红利人民币2000元（含税）。'
        '其中：A股普通股股份数为800股，本次派发A股现金红利人民币1600元（含税）。'
        '公司已派发2025年中期现金红利每股人民币1元（含税），连同本次现金红利分配，'
        '2025年全年现金红利为每股人民币3元（含税），2025年全年现金红利总额为人民币3000元(含税)。'
        '三、相关日期\nTEST_ONLY董事会2026年6月22日')
    return pages


def test_a_subtotal_is_reconciled_independently_of_all_share_amount():
    terms = parse_sse_cash_entitlement(_ah_pages(), symbol='000001')
    assert terms['eligible_a_shares'] == '800'
    assert terms['declared_total_gross_cash_cny'] == '1600'
    assert terms['all_share_terms']['current_total_gross_cash_cny'] == '2000'
    assert terms['reference_deduction_per_total_a_share'] is None
    assert terms['body_payment_date_review']['status'] == 'UNKNOWN'


@pytest.mark.parametrize('day', [25, 27])
@pytest.mark.parametrize('prefix,suffix', [('（', '）'), ('为', '')])
def test_explicit_body_payment_date_conflicts_reject_without_changing_tables(day, prefix, suffix):
    pages = _ah_pages()
    pages[1] = pages[1].replace('TEST_ONLY董事会', '四、分配实施办法。'
        f'已办理指定交易的投资者可于红利发放日{prefix}2026年6月{day}日{suffix}'
        '在其指定的证券营业部领取现金红利，未办理指定交易的股东暂由结算保管。'
        '五、有关咨询办法。TEST_ONLY董事会')
    with pytest.raises(ValueError, match='Body payment date conflicts'):
        parse_sse_cash_entitlement(pages, symbol='000001')


@pytest.mark.parametrize('wording,status', [
    ('已办理指定交易的投资者可于红利发放日（2026年6月26日）在其指定的证券营业部领取现金红利，',
     'EXPLICIT_SUPPORTED_SENTENCE_MATCHES_TABLE'),
    ('预计现金将于2026年6月26日到账。', 'UNKNOWN'),
    ('并非已办理指定交易的投资者可于红利发放日（2026年6月26日）在其指定的证券营业部领取现金红利，', 'UNKNOWN'),
    ('咨询日期为2026年6月27日。', 'UNKNOWN'), ('图像不可读。', 'UNKNOWN')])
def test_only_explicit_supported_body_sentence_is_cross_checked(wording, status):
    pages = _ah_pages()
    pages[1] = pages[1].replace('TEST_ONLY董事会',
        '四、分配实施办法。' + wording + '五、有关咨询办法。TEST_ONLY董事会')
    result = parse_sse_cash_entitlement(pages, symbol='000001')
    assert result['body_payment_date_review']['status'] == status
    assert result['body_payment_date_review']['absence_of_conflict_proven'] is False


@pytest.mark.parametrize('old,new', [('1600元', '2000元'), ('2000元', '1600元'),
    ('人民币3元', '人民币4元'), ('3000元', '3001元'), ('800股', '1001股')])
def test_a_h_scope_and_interim_annual_arithmetic_conflicts_reject(old, new):
    with pytest.raises(ValueError):
        parse_sse_cash_entitlement([p.replace(old,new) for p in _ah_pages()], symbol='000001')


@pytest.mark.parametrize('old,new', [
    ('000001', '0000019'), ('1600元', '1601元'), ('每股现金红利2元', '每股现金红利3元'),
    ('差异化分红送转：否', '差异化分红送转：是'), ('1600元（含税）。', '1600元（含税），并转增股本。'),
    ('2026/6/26', '2026/6/24'), ('TEST_ONLY董事会', '更正TEST_ONLY董事会'),
])
def test_unsupported_or_conflicting_schemes_reject(old, new):
    with pytest.raises(ValueError):
        parse_sse_cash_entitlement([p.replace(old, new) for p in _ah_pages()], symbol='000001')


def _replay():
    intent = dict(id='test-buy', actual_execution_at='2026-06-25T14:00:01+08:00',
        decision_at='2026-06-25T14:00:00+08:00')
    fold = dict(fold='development', generated_intentions=[intent], simulator_inputs=dict(bars=[
        dict(time='2026-06-25T15:00:00+08:00'), dict(time='2026-06-26T15:00:00+08:00')]),
        fills=[dict(order_id='test-buy', quantity=100, side='BUY')])
    return dict(results=[dict(symbol='000001', strict=dict(folds=[dict(execution_observations=[
        dict(bar_label='2026-06-25 15:00:00'), dict(bar_label='2026-06-26 15:00:00')])]),
        scenarios=[dict(cost_multiplier='1', folds=[fold])])],
        source_bindings=[], implementation_bindings=[], content_sha256='TEST_ONLY', summary={})


def test_hypothetical_cash_is_reported_not_credited_or_turned_into_price_adjustment(tmp_path, monkeypatch):
    proof = dict(terms=parse_sse_cash_entitlement(_ah_pages(), symbol='000001'),
        source_binding=dict(path='cash.pdf', sha256='test'), acquired_at='2026-10-24T09:00:00+08:00')
    monkeypatch.setattr(app, 'load_sse_cash_entitlement', lambda **kw: deepcopy(proof))
    replay = _replay()
    original = deepcopy(replay)
    monkeypatch.setattr(app, 'build_strategy_execution_replay', lambda **kw: replay)
    monkeypatch.setattr(app, 'sha256_file', lambda p: 'test')
    monkeypatch.setattr(app, 'require_inside', lambda root, p, label: p)
    result = app.inspect_cash_execution_exposure(root=tmp_path, symbol='000001', cash_binding={},
        now=datetime(2026, 10, 24, 10, tzinfo=CHINA))
    assert result['lanes'][0]['declared_gross_entitlement_if_eligible_cny'] == '200'
    assert result['lanes'][0]['cash_credited_to_replay'] is False
    assert result['adjusted_strategy_return'] is None and result['price_comparability'] == 'UNKNOWN'
    assert result['formal_eligibility'] is False and result['action'] == 'no_order'
    assert replay == original
    replay['results'][0]['strict']['folds'][0]['execution_observations'].pop()
    with pytest.raises(ValueError, match='observed'):
        app.inspect_cash_execution_exposure(root=tmp_path, symbol='000001', cash_binding={},
            now=datetime(2026, 10, 24, 10, tzinfo=CHINA))


def test_original_changed_during_execution_replay_rejects(tmp_path, monkeypatch):
    from hashlib import sha256
    source = tmp_path / 'cash.pdf'
    source.write_bytes(b'TEST_ONLY original')
    proof = dict(terms=parse_sse_cash_entitlement(_ah_pages(), symbol='000001'),
        source_binding=dict(path='cash.pdf', sha256=sha256(source.read_bytes()).hexdigest()),
        acquired_at='2026-10-24T09:00:00+08:00')
    monkeypatch.setattr(app, 'load_sse_cash_entitlement', lambda **kw: deepcopy(proof))

    def changed(**kw):
        source.write_bytes(b'TEST_ONLY changed during replay')
        return _replay()

    monkeypatch.setattr(app, 'build_strategy_execution_replay', changed)
    with pytest.raises(ValueError, match='changed during read'):
        app.inspect_cash_execution_exposure(root=tmp_path, symbol='000001', cash_binding={},
            now=datetime(2026, 10, 24, 10, tzinfo=CHINA))


@pytest.mark.skipif(not os.environ.get('HOTSPOT_CASH_EXPOSURE_SOURCE'), reason='Optional new official original')
def test_real_excluded_repurchase_body_is_out_of_scope_not_guessed_as_a_share_total():
    from value_investment_agent.infrastructure.hotspot.sse_cash_entitlement import load_sse_cash_entitlement
    root = Path(os.environ['HOTSPOT_CASH_EXPOSURE_ROOT'])
    binding = json.loads((root / os.environ['HOTSPOT_CASH_EXPOSURE_SOURCE']).read_bytes())
    with pytest.raises(ValueError, match='Explicit A-share subtotal'):
        load_sse_cash_entitlement(root=root, binding=binding, symbol='600519', now=datetime.now(CHINA))


@pytest.mark.parametrize('suffix', ['A股2026/6/24－2026/6/252026/6/25',
    'A股2026/6/25－2026/6/262026/6/26', 'A股2026/6/24未知日期'])
def test_additional_or_partial_a_date_rows_are_not_ignored(suffix):
    pages = _ah_pages()
    pages[0] += suffix
    with pytest.raises(ValueError, match='date tables'):
        parse_sse_cash_entitlement(pages, symbol='000001')


@pytest.mark.skipif(not os.environ.get('HOTSPOT_CASH_EXPOSURE_OBSERVATION'), reason='Optional fixed-five real exposure')
def test_real_fixed_sample_signal_crosses_ex_date_without_adjusting_returns():
    from datetime import date
    from hashlib import sha256
    from value_investment_agent.application.product.daily_event_observation import verify_retained_event_coverage
    root = Path(os.environ['HOTSPOT_CASH_EXPOSURE_ROOT'])
    observation = json.loads((root / os.environ['HOTSPOT_CASH_EXPOSURE_OBSERVATION']).read_bytes())
    now = datetime.now(CHINA)
    verified = verify_retained_event_coverage(root, observation, symbol='600030',
        required_from=date(2026,6,3), required_to=date(2026,6,10), now=now)
    scan = json.loads((root / verified['scan_binding']['path']).read_bytes())
    row = next(r for r in scan['announcements'] if r['announcement_id'] == '1225348864')
    binding = dict(row['evidence_refs'][0], url=row['source_url'], available_at=observation['acquired_at'])
    assert binding['sha256'] == '12923c8bd35dcc7411639d2393893464b6153e1f8afd2285f98f446d6aa54be3'
    from value_investment_agent.infrastructure.hotspot.cash_implementation import _pdf
    pages, _ = _pdf(root, binding, now)
    needle = '（2026年6月10日）'
    assert pages[1].count(needle) == 1
    changed = list(pages)
    changed[1] = changed[1].replace(needle, '（2026年6月11日）')
    with pytest.raises(ValueError, match='Body payment date conflicts'):
        parse_sse_cash_entitlement(changed, symbol='600030')
    before = {r['path']: sha256((root/r['path']).read_bytes()).hexdigest() for r in observation['source_bindings']}
    result = app.inspect_cash_execution_exposure(root=root, symbol='600030', cash_binding=binding, now=now)
    assert result['cash_proof']['terms']['gross_cash_per_eligible_a_share'] == '0.41'
    assert result['cash_proof']['terms']['eligible_a_shares'] == '12200469974'
    assert result['cash_proof']['provider_url_date'] == '2026-06-04'
    assert result['cash_proof']['terms']['published_date'] == '2026-06-03'
    assert result['cash_proof']['terms']['body_payment_date_review']['status'] == 'EXPLICIT_SUPPORTED_SENTENCE_MATCHES_TABLE'
    assert result['original_replay_summary']['signal_event_count'] == 161
    applicable = [lane for lane in result['lanes'] if lane['event_dates_within_partition']]
    assert len(applicable) == 3
    for lane in applicable:
        assert lane['hypothetical_record_close_quantity'] == 0
        assert len(lane['ex_date_intentions']) == 1
        assert lane['ex_date_intentions'][0]['six_bar_lookback_present'] is True
        assert lane['ex_date_intentions'][0]['raw_lookback_crosses_ex_date'] is True
        assert lane['cash_credited_to_replay'] is False
    assert result['strict_pit_admitted'] is result['strict_oos_admitted'] is False
    assert result['adjusted_strategy_return'] is None and result['action'] == 'no_order'
    assert before == {p: sha256((root/p).read_bytes()).hexdigest() for p in before}
