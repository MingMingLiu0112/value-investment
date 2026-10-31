"""TEST_ONLY locator replay: fixed non-PDF bytes, mocked extracted text only.

No fixture represents an actual issuer filing or financial original. Rejection
tests assert the required contract without skips or expected-failure markers.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from value_investment_agent.infrastructure.filings import first_research_fact_replay_v1 as helper


NOW = datetime(2026, 10, 31, 1, tzinfo=timezone.utc)
RAW = b'TEST_ONLY non-PDF bytes: extract_pages is monkeypatched; not a financial original.\n'
HEADER = '项目 2025年12月31日 2024年12月31日'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def native(tmp_path, monkeypatch):
    directory = tmp_path / 'runtime/TEST_ONLY-first-research'
    directory.mkdir(parents=True)
    original = directory / 'TEST_ONLY-not-a-pdf.bin'
    original.write_bytes(RAW)
    pages = [
        'TEST_ONLY synthetic extracted text\n公司代码：000001\n测试股份有限公司\n2025年年度报告',
        '合并资产负债表\n单位：元 币种：人民币\n' + HEADER + '\n'
        '归属于母公司所有者权益合计 300.00 250.00\n少数股东权益 20.00 15.00',
        '母公司资产负债表\n单位：元 币种：人民币\n' + HEADER + '\n货币资金 100.00 80.00',
        '股份情况\n单位：股\n2025年12月31日\n总股数 1,000',
    ]
    source = dict(id='TEST_ONLY-source', path=original.relative_to(tmp_path).as_posix(),
        sha256=digest(RAW), symbol='000001', issuer_name='测试股份有限公司',
        available_at='2026-04-20T00:00:00+00:00', published_date='2026-04-17',
        report_period='2025-12-31', report_title='2025年年度报告',
        source_url='https://static.cninfo.com.cn/TEST_ONLY-not-an-actual-filing.PDF')

    def fact(ident, field, page, label, value, scope, marker):
        row = next(line for line in pages[page - 1].splitlines() if line.startswith(label))
        return dict(id=ident, field=field, source_id=source['id'], physical_page=page,
            excerpt=row, label=label, value=value, scope=scope, scope_marker=marker,
            period_end='2025-12-31', column_index=0,
            column_periods=['2025-12-31', '2024-12-31'], column_header=HEADER,
            unit='CNY', number_kind='money')

    cash = fact('TEST_ONLY-cash', 'parent_cash', 3, '货币资金', '100.00', 'parent', '母公司资产负债表')
    equity = fact('TEST_ONLY-equity', 'start_book_equity', 2, '归属于母公司所有者权益合计',
                  '300.00', 'consolidated_parent_equity', '合并资产负债表')
    shares = fact('TEST_ONLY-shares', 'ordinary_shares', 4, '总股数', '1000',
                  'issued_ordinary_shares', '股份情况')
    shares.update(column_periods=['2025-12-31'], column_header='2025年12月31日',
                  unit='shares', number_kind='shares')
    spec = dict(schema_version=helper.SCHEMA, action='no_order', symbol='000001',
        issuer_name='测试股份有限公司', financial_basis='2025-12-31',
        generated_at='2026-04-21T00:00:00+00:00', sources=[source], facts=[cash, equity, shares])
    manifest = directory / 'manifest.json'
    calls = []

    def extract(path):
        assert Path(path) == original
        assert original.read_bytes() == RAW
        calls.append(path)
        return list(pages)

    monkeypatch.setattr(helper, 'extract_pages', extract)

    def seal():
        raw = json.dumps(spec, ensure_ascii=False, sort_keys=True).encode('utf-8')
        manifest.write_bytes(raw)
        return dict(path=manifest.relative_to(tmp_path).as_posix(), sha256=digest(raw))

    return dict(root=tmp_path, spec=spec, pages=pages, seal=seal, original=original, calls=calls)


def replay(native, binding=None, now=NOW):
    """Fixture preparation precedes this boundary; replay must perform zero writes."""
    binding = native['seal']() if binding is None else binding
    root = native['root']

    def snapshot():
        return {p.relative_to(root).as_posix(): (digest(p.read_bytes()), p.stat().st_mtime_ns)
                for p in root.rglob('*') if p.is_file()}

    before = snapshot()
    original_open = Path.open

    def readonly_open(path, mode='r', *args, **kwargs):
        assert not any(flag in mode for flag in ('w', 'a', 'x', '+')), 'Replay attempted a write'
        return original_open(path, mode, *args, **kwargs)

    try:
        with patch.object(Path, 'open', readonly_open), \
             patch.object(Path, 'mkdir', side_effect=AssertionError('Replay attempted mkdir')), \
             patch.object(Path, 'unlink', side_effect=AssertionError('Replay attempted unlink')), \
             patch.object(Path, 'rename', side_effect=AssertionError('Replay attempted rename')), \
             patch.object(Path, 'replace', side_effect=AssertionError('Replay attempted replace')):
            return helper.replay_first_research_facts(root=root, binding=binding, now=now)
    finally:
        assert snapshot() == before, 'Replay changed the retained fixture'


def test_legal_cash_parent_equity_and_shares_are_reported_rows_only(native):
    binding = native['seal']()
    before = deepcopy(native['spec'])
    result = replay(native, binding)
    assert [(row['field'], row['value']) for row in result['facts']] == [
        ('parent_cash', '100.00'), ('start_book_equity', '300.00'), ('ordinary_shares', '1000')]
    assert result['schema_version'] == helper.SCHEMA
    assert result['action'] == 'no_order'
    assert result['formal_eligibility'] is False and result['strict_historical_pit'] is False
    assert result['by_id'] == {row['id']: row for row in result['facts']}
    for row in result['facts']:
        assert row['classification'] == 'REPORTED_NATIVE_ROW_NOT_ECONOMIC_ADMISSION'
        assert row['source_sha256'] == digest(RAW)
        assert row['available_at'] == native['spec']['sources'][0]['available_at']
    assert len(result['input_fingerprint']) == 64
    assert replay(native, binding) == result
    assert native['spec'] == before and native['original'].read_bytes() == RAW


def test_prior_column_uses_its_printed_value(native):
    cash = native['spec']['facts'][0]
    cash.update(column_index=1, period_end='2024-12-31', value='80.00')
    assert replay(native)['by_id'][cash['id']]['value'] == '80.00'


@pytest.mark.parametrize('index,value', [(0, '100.01'), (1, '300.01'), (2, '999'), (0, 'NaN')])
def test_declared_amount_tamper_rejected(native, index, value):
    native['spec']['facts'][index]['value'] = value
    with pytest.raises(ValueError, match='declared value differs'):
        replay(native)


@pytest.mark.parametrize('target', ['manifest_binding', 'source_binding', 'source_bytes', 'manifest_bytes'])
def test_hash_mismatch_rejected_without_extracting(native, target):
    if target == 'source_binding':
        native['spec']['sources'][0]['sha256'] = '0' * 64
    binding = native['seal']()
    if target == 'manifest_binding':
        binding['sha256'] = '0' * 64
    elif target == 'source_bytes':
        native['original'].write_bytes(RAW + b'TEST_ONLY changed')
    elif target == 'manifest_bytes':
        (native['root'] / binding['path']).write_bytes(b'TEST_ONLY altered manifest')
    with pytest.raises(ValueError, match='hash/size mismatch'):
        replay(native, binding)
    assert native['calls'] == []


@pytest.mark.parametrize('fault', ['index_period', 'reversed_periods', 'future_period', 'printed_year_order'])
def test_wrong_comparative_period_rejected(native, fault):
    cash = native['spec']['facts'][0]
    if fault == 'index_period':
        cash['column_index'] = 1
    elif fault == 'reversed_periods':
        cash.update(column_index=1, column_periods=['2024-12-31', '2025-12-31'], value='80.00')
    elif fault == 'future_period':
        cash['period_end'] = '2026-12-31'
    else:
        header = '项目 2024年12月31日 2025年12月31日'
        native['pages'][2] = native['pages'][2].replace(HEADER, header)
        cash['column_header'] = header
    with pytest.raises(ValueError, match='period|year order'):
        replay(native)


def test_printed_same_year_wrong_month_day_rejected(native):
    cash = native['spec']['facts'][0]
    header = '项目 2025年6月30日 2024年6月30日'
    native['pages'][2] = native['pages'][2].replace(HEADER, header)
    cash['column_header'] = header
    # Resealing a locator cannot relabel printed June balances as December.
    with pytest.raises(ValueError):
        replay(native)


def test_spaced_printed_wrong_month_day_rejected(native):
    cash = native['spec']['facts'][0]
    header = '项目 2025 年 6 月 30 日 2024 年 6 月 30 日'
    native['pages'][2] = native['pages'][2].replace(HEADER, header)
    cash['column_header'] = header
    with pytest.raises(ValueError):
        replay(native)


def test_ending_opening_header_with_spaced_native_basis_date_accepted(native):
    cash = native['spec']['facts'][0]
    header = '项目 期末余额 期初余额'
    native['pages'][2] = native['pages'][2].replace(HEADER, '2025 年 12 月 31 日\n' + header)
    cash['column_header'] = header
    result = replay(native)
    row = result['by_id'][cash['id']]
    assert row['value'] == '100.00' and row['period_end'] == '2025-12-31'
    assert row['column_periods'] == ['2025-12-31', '2024-12-31']
    assert result['formal_eligibility'] is False and result['strict_historical_pit'] is False


def relative_parent_balance(native, *, interim=True):
    """TEST_ONLY first main statements, with the parent date deliberately absent."""
    cash = native['spec']['facts'][0]
    native['spec']['facts'] = [cash]
    period = '2025-06-30' if interim else '2025-12-31'
    title = '2025年半年度报告' if interim else '2025年年度报告'
    native['spec']['financial_basis'] = period
    native['spec']['sources'][0].update(report_period=period, report_title=title)
    native['pages'][0] = native['pages'][0].replace('2025年年度报告', title)
    cash.update(period_end=period, column_periods=[period, '2024-12-31'],
                column_header='项目 期末余额 期初余额')
    native['pages'][1] = ('合并资产负债表\n2025 年 6 月 30 日\n单位：元 币种：人民币\n'
                           '项目 2025年6月30日 2024年12月31日\n资产总计 400.00 330.00')
    native['pages'][2] = ('母公司资产负债表\n单位：元 币种：人民币\n'
                           '项目 期末余额 期初余额\n货币资金 100.00 80.00')
    return cash


@pytest.mark.parametrize('continued', [False, True])
def test_relative_h1_parent_uses_same_report_primary_consolidated_date(native, continued):
    cash = relative_parent_balance(native)
    if continued:
        native['pages'][2] = native['pages'][2].replace('\n' + cash['excerpt'], '')
        native['pages'][3] = 'TEST_ONLY continued main statement\n' + cash['excerpt']
        cash.update(physical_page=4, header_pages=[3, 4])
    result = replay(native)
    row, = result['facts']
    assert row['value'] == '100.00' and row['scope'] == 'parent'
    assert row['period_end'] == '2025-06-30'
    assert row['column_periods'] == ['2025-06-30', '2024-12-31']
    assert row['period_basis'] == 'DERIVED_FROM_REPORT_PERIOD_CONVENTION'
    assert row['period_evidence'] == dict(physical_page=2, scope_marker='合并资产负债表',
                                         period_end='2025-06-30')
    assert row['classification'] == 'REPORTED_NATIVE_ROW_NOT_ECONOMIC_ADMISSION'
    assert row['source_sha256'] == digest(RAW)
    assert result['action'] == 'no_order'
    assert result['formal_eligibility'] is False and result['strict_historical_pit'] is False


def test_relative_annual_parent_cannot_inherit_june_primary_cutoff(native):
    relative_parent_balance(native, interim=False)
    # Annual title/declared December period cannot override the printed June date.
    with pytest.raises(ValueError, match='primary balance.*report cutoff'):
        replay(native)


@pytest.mark.parametrize('mode', ['current', 'wrong_column', 'no_geometry'])
def test_single_current_payable_requires_geometry_and_keeps_comparative_unknown(native, monkeypatch, mode):
    row = relative_parent_balance(native)
    native['pages'][2] = native['pages'][2].replace(row['excerpt'], '应付股利 123.45')
    row.update(id='TEST_ONLY-payable', field='parent_dividend_payable', label='应付股利',
               excerpt='应付股利 123.45', value='123.45')
    geometry = dict(header_page=3, labels=['期末余额', '期初余额'])
    if mode != 'no_geometry':
        row['column_geometry'] = geometry
    if mode == 'wrong_column':
        # Keep period/index internally consistent: only native placement rejects it.
        row.update(column_index=1, period_end='2024-12-31')
    calls = []

    def test_only_geometry_decoder(path, page_number, amount, supplied):
        assert mode != 'no_geometry', 'Missing geometry must not invoke the decoder'
        assert path == native['original'] and path.read_bytes() == RAW
        assert page_number == 3 and amount == '123.45' and supplied == geometry
        calls.append((page_number, amount))
        return 0  # TEST_ONLY decoder result; no PDF or real charbox claim.

    monkeypatch.setattr(helper, '_native_column', test_only_geometry_decoder)
    if mode == 'current':
        result = replay(native)
        fact, = result['facts']
        assert fact['value'] == '123.45' and fact['period_end'] == '2025-06-30'
        assert fact['missing_comparative_periods'] == ['2024-12-31']
        assert fact['classification'] == 'REPORTED_NATIVE_ROW_NOT_ECONOMIC_ADMISSION'
        assert fact['period_basis'] == 'DERIVED_FROM_REPORT_PERIOD_CONVENTION'
        assert len(result['by_id']) == 1  # No invented zero-valued comparative fact.
        assert result['formal_eligibility'] is False and result['strict_historical_pit'] is False
    else:
        with pytest.raises(ValueError, match='exact explicit comparative columns'):
            replay(native)
    assert calls == ([] if mode == 'no_geometry' else [(3, '123.45')])


@pytest.mark.parametrize('fault', ['later_page_repeat', 'same_page_repeat', 'adjusted', 'comparative'])
def test_relative_parent_rejects_later_or_adjusted_statement(native, fault):
    cash = relative_parent_balance(native)
    if fault == 'later_page_repeat':
        native['pages'][3] = native['pages'][2]
        cash['physical_page'] = 4
    elif fault == 'same_page_repeat':
        # The earlier primary heading must not authorize a later table on its page.
        native['pages'][2] = ('母公司资产负债表\n项目 期末余额 期初余额\n'
                               '资产总计 200.00 150.00\n' + native['pages'][2])
    else:
        note = '调整后' if fault == 'adjusted' else '比较附表'
        native['pages'][2] = native['pages'][2].replace('母公司资产负债表', '母公司资产负债表\n' + note)
    with pytest.raises(ValueError):
        replay(native)


@pytest.mark.parametrize('fault', ['consolidated_marker', 'missing_parent_marker', 'later_consolidated_heading'])
def test_parent_cash_rejects_wrong_statement_marker(native, fault):
    cash = native['spec']['facts'][0]
    if fault == 'consolidated_marker':
        native['pages'][2] = native['pages'][2].replace('母公司资产负债表', '合并资产负债表')
        cash['scope_marker'] = '合并资产负债表'
    elif fault == 'missing_parent_marker':
        native['pages'][2] = native['pages'][2].replace('母公司资产负债表', '合并资产负债表')
    else:
        native['pages'][2] = native['pages'][2].replace('货币资金', '合并资产负债表\n货币资金')
    with pytest.raises(ValueError, match='scope marker|consolidated table|different statement-scope'):
        replay(native)


def test_decorated_marker_cannot_bypass_later_consolidated_heading(native):
    cash = native['spec']['facts'][0]
    cash['scope_marker'] = '母公司资产负债表 单位：元'
    native['pages'][2] = native['pages'][2].replace('货币资金', '合并资产负债表\n货币资金')
    with pytest.raises(ValueError):
        replay(native)


def test_minority_equity_cannot_masquerade_as_parent_equity(native):
    row = native['spec']['facts'][1]
    row.update(label='少数股东权益', excerpt='少数股东权益 20.00 15.00', value='20.00')
    with pytest.raises(ValueError, match='semantic label mismatch'):
        replay(native)


@pytest.mark.parametrize('fault', ['available_at', 'published_date', 'generated_at', 'naive_available_at'])
def test_future_or_undated_source_rejected(native, fault):
    if fault == 'generated_at':
        native['spec'][fault] = '2027-01-01T00:00:00+00:00'
    elif fault == 'published_date':
        native['spec']['sources'][0][fault] = '2027-01-01'
    else:
        native['spec']['sources'][0]['available_at'] = (
            '2026-04-20T00:00:00' if fault == 'naive_available_at' else '2027-01-01T00:00:00+00:00')
    with pytest.raises(ValueError, match='timestamp|publication is future'):
        replay(native)


@pytest.mark.parametrize('currency', ['', ' 币种：美元'])
def test_unknown_or_foreign_printed_currency_rejected(native, currency):
    native['pages'][2] = native['pages'][2].replace(' 币种：人民币', currency)
    # A manifest declaring CNY cannot supply missing or contradictory original evidence.
    with pytest.raises(ValueError):
        replay(native)


def test_spaced_native_cny_currency_accepted(native):
    native['pages'][2] = native['pages'][2].replace('币种：人民币', '币种： 人民币')
    result = replay(native)
    row = result['by_id']['TEST_ONLY-cash']
    assert row['value'] == '100.00' and row['unit'] == 'CNY'
    assert row['classification'] == 'REPORTED_NATIVE_ROW_NOT_ECONOMIC_ADMISSION'
    assert result['formal_eligibility'] is False and result['action'] == 'no_order'


def test_explicit_table_usd_not_overridden_by_report_cny_functional_currency(native):
    native['pages'][2] = native['pages'][2].replace('币种：人民币', '币种：美元')
    native['pages'].append('本公司以人民币为记账本位币。')
    with pytest.raises(ValueError):
        replay(native)


def test_unknown_declared_currency_rejected(native):
    native['spec']['facts'][0]['unit'] = 'UNKNOWN'
    with pytest.raises(ValueError, match='currency/share unit mismatch'):
        replay(native)


@pytest.mark.parametrize('index', [0, 1])
def test_missing_comparative_amount_rejected(native, index):
    row = native['spec']['facts'][index]
    shortened = row['excerpt'].rsplit(' ', 1)[0]
    page = row['physical_page'] - 1
    native['pages'][page] = native['pages'][page].replace(row['excerpt'], shortened)
    row['excerpt'] = shortened
    with pytest.raises(ValueError, match='exact explicit comparative columns'):
        replay(native)


def test_original_row_locator_must_be_unique(native):
    native['pages'][2] += '\n货币资金 100.00 80.00'
    with pytest.raises(ValueError, match='absent or ambiguous'):
        replay(native)


@pytest.mark.parametrize('mode', ['bound_org', 'missing_binding', 'wrong_org'])
def test_optional_organization_requires_matching_bound_index(native, mode):
    source = native['spec']['sources'][0]
    index = native['root'] / 'runtime/TEST_ONLY-first-research/identity-index.json'
    raw = json.dumps(dict(TEST_ONLY=True, announcements=[
        dict(secCode='000001', orgId='TEST_ONLY-org', secName='测试')
    ]), ensure_ascii=False).encode('utf-8')
    index.write_bytes(raw)
    source.update(organization_id='TEST_ONLY-org', identity_available_at='2026-04-20T00:00:00+00:00',
        identity_index_binding=dict(path=index.relative_to(native['root']).as_posix(), sha256=digest(raw)))
    if mode == 'missing_binding':
        source.pop('identity_index_binding')
    elif mode == 'wrong_org':
        source['organization_id'] = 'TEST_ONLY-other-org'
    if mode == 'bound_org':
        result = replay(native)
        assert len(result['facts']) == 3
        assert result['sources'][0]['organization_id'] == 'TEST_ONLY-org'
        assert result['sources'][0]['identity_index_binding'] == source['identity_index_binding']
        assert result['formal_eligibility'] is False and result['action'] == 'no_order'
    else:
        with pytest.raises(ValueError, match=('bound official index' if mode == 'missing_binding'
                                              else 'organization differs from official index')):
            replay(native)
        assert native['calls'] == []
