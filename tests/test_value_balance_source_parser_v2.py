"""Direct source-bound balance parsing; synthetic fixtures are TEST_ONLY."""
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research import value_evidence_enrichment_v1 as app
from value_investment_agent.infrastructure.screening import value_evidence_enrichment_v1 as parser


NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


@pytest.fixture
def source(tmp_path, monkeypatch):
    pages = ['TEST_ONLY 2025年年度报告\n公司代码：600519',
             '公司的中文名称 测试股份有限公司',
             '合并资产负债表\n编制单位：测试股份有限公司\n'
             '2025年12月31日\n单位：元 币种：人民币\n'
             '项目 附注 2025年12月31日 2024年12月31日\n资产总计 100.00 80.00',
             '负债合计 70.00 55.00\n归属于母公司所有者权益（或股东权益）合计 20.00 15.00\n'
             '少数股东权益 10.00 10.00\n所有者权益（或股东权\n益）合计\n30.00 25.00\n'
             '负债和所有者权益（或股东权益）总计 100.00 80.00\n母公司资产负债表\n'
             '资产总计 999.00 888.00\n负债合计 666.00 555.00\n所有者权益合计 333.00 333.00']
    raw = tmp_path / 'original.pdf'
    raw.write_bytes(b'TEST_ONLY mocked extraction, not an actual PDF')
    src = parser.RetainedAnnualSource('600519', '2025-12-31', 'original.pdf',
        hashlib.sha256(raw.read_bytes()).hexdigest(), 'https://static.cninfo.com.cn/TEST_ONLY.pdf',
        '2026-10-30T10:00:00+00:00')
    monkeypatch.setattr(parser, 'extract_pages', lambda path, limit: pages[:limit])
    return src, pages


def enrich(root, source):
    return app.enrich_retained_company(root, source, [], evaluation_at=NOW,
                                      cache_dir=root / '.tmp/balance-v2')


@pytest.mark.parametrize('label', ['所有者权益合计 30.00 25.00',
    '所有者权益（或股东权益）合计 30.00 25.00',
    '所有者权益(或股东权益)合计 30.00 25.00',
    '所有者权益（或股东权\n益）合计\n30.00 25.00'])
def test_cross_page_identity_and_exact_total_equity(tmp_path, source, label):
    src, pages = source
    pages[3] = pages[3].replace('所有者权益（或股东权\n益）合计\n30.00 25.00', label)
    result = enrich(tmp_path, src)
    point, = result['adopted_points']
    assert point['field_name'] == 'debt_ratio' and Decimal(point['value']) == 70
    metadata = point['metadata']
    assert metadata['single_source_balance_verification'] is True
    assert metadata['automatic_cross_source_verification'] is False
    assert metadata['assurance_basis'] == 'source_reported_only'
    assert metadata['derivation_rule_pit_status'] == 'NOT_ADMITTED'
    assert metadata['economic_approval'] is False
    proof = metadata['balance_reconciliation']
    assert Decimal(proof['current_residual']) == Decimal(proof['prior_residual']) == 0
    owner = proof['owner_evidence']
    assert owner['security_code_page'] == 1 and owner['legal_name_page'] == 2
    assert owner['identity_page_scope'] == [1, 4]
    for field in ('legal_name_evidence', 'security_code_evidence'):
        for ref in owner[field]:
            assert ref['excerpt'] in pages[ref['page'] - 1]
    rows = proof['balance_rows']
    assert [r['field_name'] for r in rows] == ['total_assets', 'total_liabilities', 'total_equity']
    assert rows[-1]['source_label'] == '所有者权益合计'
    assert rows[-1]['excerpt'] == label
    if label == '所有者权益合计 30.00 25.00':
        assert 'printed_source_label' not in rows[-1]
    else:
        assert rows[-1]['printed_source_label']
    assert len({r['table_context_id'] for r in rows}) == 1
    assert result['source_extraction']['identity']['version'] == 'value-retained-enrichment-v2'
    assert result['formal_eligibility'] is False and result['action'] == 'no_order'
    assert result['debt_scope']['complete_debt_verified'] is False


@pytest.mark.parametrize('fault', ['conflicting_code_same_page', 'conflicting_code_other_page',
    'conflicting_name', 'code_only_page13', 'name_only_page13', 'unlabelled_name',
    'wrong_compiler', 'source_symbol_mismatch', 'name_in_other_original'])
def test_identity_conflicts_or_out_of_scope_cannot_bind(tmp_path, source, fault):
    src, pages = source
    if fault == 'conflicting_code_same_page':
        pages[0] += '\n证券代码：600887'
    elif fault == 'conflicting_code_other_page':
        pages.append('股票代码：600887')
    elif fault == 'conflicting_name':
        pages.append('公司中文全称 另一股份有限公司')
    elif fault in {'code_only_page13', 'name_only_page13'}:
        index = 0 if fault == 'code_only_page13' else 1
        value = pages[index]
        pages[index] = '2025年年度报告' if index == 0 else 'TEST_ONLY'
        pages.extend(['TEST_ONLY'] * (12 - len(pages)))
        pages.append(value)
    elif fault in {'unlabelled_name', 'name_in_other_original'}:
        pages[1] = '测试股份有限公司'
        # An identity from a different call must never be cached into this original.
        parser._issuer_legal_owner(['公司代码：600519\n公司的中文名称 测试股份有限公司'])
    elif fault == 'wrong_compiler':
        pages[2] = pages[2].replace('编制单位：测试股份有限公司', '编制单位：另一股份有限公司')
    else:
        pages[0] = pages[0].replace('600519', '600887')
    try:
        result = enrich(tmp_path, src)
    except ValueError as exc:
        assert fault in {'code_only_page13', 'source_symbol_mismatch'}
        assert 'security identity' in str(exc)
    else:
        assert result['adopted_points'] == []


def test_identity_at_page12_is_bounded_and_retains_all_evidence(source):
    _, pages = source
    legal = pages.pop(1)
    pages.extend(['TEST_ONLY'] * (11 - len(pages)))
    pages.append(legal)
    owner = parser._issuer_legal_owner(pages)
    assert owner['legal_name_page'] == 12 and owner['identity_page_scope'] == [1, 12]
    pages[10] += '\n股票代码：600887'
    assert parser._issuer_legal_owner(pages) is None


@pytest.mark.parametrize('prefix', ['归属于\n母公司', '归属\n于\n母公司',
                                    '归\n属\n于\n母\n公\n司'])
def test_multiline_parent_prefix_rejected_before_arithmetic(tmp_path, source, prefix):
    src, pages = source
    pages[3] = pages[3].replace('所有者权益（或股东权\n益）合计\n30.00 25.00',
                                prefix + '\n所有者权益合计 30.00 25.00')
    rows = parser.extract_debt_balance_candidates(pages, src.period, balance_totals=True, include_equity=True)
    assert [r['field_name'] for r in rows] == ['total_assets', 'total_liabilities']
    # Amounts would balance exactly if wrongly admitted as total group equity.
    assert Decimal('100') == Decimal('70') + Decimal('30')
    assert Decimal('80') == Decimal('55') + Decimal('25')
    assert enrich(tmp_path, src)['adopted_points'] == []


def test_legacy_same_page_owner_and_plain_equity_have_no_new_metadata(tmp_path, source):
    src, pages = source
    pages[0] += '\n' + pages[1]
    pages[1] = 'TEST_ONLY'
    pages[3] = pages[3].replace('所有者权益（或股东权\n益）合计\n30.00 25.00',
                                '所有者权益合计 30.00 25.00')
    expected = dict(legal_name='测试股份有限公司', security_code='600519',
        legal_name_page=1, legal_name_excerpt='公司的中文名称 测试股份有限公司',
        security_code_page=1, security_code_excerpt='公司代码：600519')
    assert parser._issuer_legal_owner(pages) == expected
    result = enrich(tmp_path, src)
    point, = result['adopted_points']
    proof = point['metadata']['balance_reconciliation']
    assert proof['owner_evidence'] == dict(expected, compiler_name='测试股份有限公司',
        compiler_page=3, compiler_excerpt='编制单位：测试股份有限公司')
    assert all('printed_source_label' not in row for row in proof['balance_rows'])
    assert Decimal(point['value']) == 70


@pytest.mark.parametrize('footer,header', [('', ''), ('58 / 143', '测试股份有限公司2025 年年度报告\n59 / 143'),
    ('第58页', '第59页'), ('2025 年年度报告全文\n58', '2025 年年度报告全文\n59')])
@pytest.mark.parametrize('prefix', ['归属于母公司', '归属于\n母公司'])
def test_cross_page_parent_prefix_rejects_equity_before_reconciliation(tmp_path, source, footer, header, prefix):
    src, pages = source
    pages[3:] = ['负债合计 70.00 55.00\n' + prefix + '\n' + footer,
                 header + '\n所有者权益合计 30.00 25.00\n负债和所有者权益总计 100.00 80.00']
    rows = parser.extract_debt_balance_candidates(pages, src.period, balance_totals=True, include_equity=True)
    assert [r['field_name'] for r in rows] == ['total_assets', 'total_liabilities']
    assert enrich(tmp_path, src)['adopted_points'] == []


def test_complete_parent_row_does_not_block_next_page_real_total(tmp_path, source):
    src, pages = source
    pages[3:] = ['负债合计 70.00 55.00\n归属于母公司所有者权益合计 20.00 15.00\n58 / 143',
                 '测试股份有限公司2025 年年度报告\n59 / 143\n少数股东权益 10.00 10.00\n'
                 '所有者权益合计 30.00 25.00\n负债和所有者权益总计 100.00 80.00']
    point, = enrich(tmp_path, src)['adopted_points']
    assert point['field_name'] == 'debt_ratio' and Decimal(point['value']) == 70


@pytest.mark.parametrize('blank_count', [1, 2])
@pytest.mark.parametrize('furniture', ['', '测试股份有限公司2025 年年度报告\n第59页'])
def test_pending_parent_survives_consecutive_empty_continuations(tmp_path, source, blank_count, furniture):
    src, pages = source
    pages[3:] = ['负债合计 70.00 55.00\n归属于母公司\n58 / 143',
                 *([furniture] * blank_count),
                 '测试股份有限公司2025 年年度报告\n60 / 143\n'
                 '所有者权益合计 30.00 25.00\n负债和所有者权益总计 100.00 80.00']
    rows = parser.extract_debt_balance_candidates(pages, src.period, balance_totals=True, include_equity=True)
    assert [r['field_name'] for r in rows] == ['total_assets', 'total_liabilities']
    assert enrich(tmp_path, src)['adopted_points'] == []


@pytest.mark.parametrize('resolution', ['complete_row', 'table_end'])
def test_pending_parent_after_empty_pages_resolves_only_at_row_or_table_end(tmp_path, source, resolution):
    src, pages = source
    pages[3:] = ['负债合计 70.00 55.00\n归属于母公司',
                 '测试股份有限公司2025 年年度报告\n58 / 143', '第59页',
                 ('归属于母公司所有者权益合计 20.00 15.00' if resolution == 'complete_row'
                  else '母公司资产负债表'),
                 '所有者权益合计 30.00 25.00\n负债和所有者权益总计 100.00 80.00']
    points = enrich(tmp_path, src)['adopted_points']
    if resolution == 'complete_row':
        point, = points
        assert point['field_name'] == 'debt_ratio' and Decimal(point['value']) == 70
    else:
        assert points == []


def test_old_fact_identity_drift_is_rejected_not_resigned(tmp_path, source, monkeypatch):
    from dataclasses import asdict
    src, _ = source
    result = enrich(tmp_path, src)
    packet = result['source_extraction']
    from copy import deepcopy
    historical = deepcopy(packet)
    historical['identity']['implementation_sha256'] = '0' * 64
    old_points, _ = app._reconcile_official_balance_ratio(src, [], historical)
    assert old_points[0]['data_point_id'] != result['adopted_points'][0]['data_point_id']
    before = deepcopy(old_points)
    with pytest.raises(ValueError, match='does not match cold-revalidated original'):
        app.consume_retained_enrichment(tmp_path, old_points, [asdict(src)], evaluation_at=NOW)
    assert old_points == before


@pytest.mark.parametrize('fault', ['parent_equity', 'wrapped_parent_equity', 'across_table', 'across_page',
    'intervening_text', 'extra_column', 'single_amount', 'duplicate_total',
    'current_cent', 'prior_cent', 'reverse_columns', 'unknown_currency',
    'different_currency', 'different_owner_on_continuation'])
def test_equity_reassembly_preserves_scope_and_exact_arithmetic(tmp_path, source, fault):
    src, pages = source
    label = '所有者权益（或股东权\n益）合计\n30.00 25.00'
    changes = {
        'parent_equity': '归属于母公司所有者权益（或股东权益）合计 30.00 25.00',
        'wrapped_parent_equity': '归属于母公司\n所有者权益合计 30.00 25.00',
        'across_table': '所有者权益（或股东权益）合计\n母公司资产负债表\n30.00 25.00',
        'intervening_text': '所有者权益（或股东权益）合计\n少数股东权益\n30.00 25.00',
        'extra_column': '所有者权益（或股东权益）合计 30.00 25.00 20.00',
        'single_amount': '所有者权益（或股东权益）合计 30.00',
        'duplicate_total': label + '\n所有者权益合计 30.00 25.00',
        'current_cent': label.replace('30.00', '30.01'),
        'prior_cent': label.replace('25.00', '25.01'),
    }
    if fault in changes:
        pages[3] = pages[3].replace(label, changes[fault])
    elif fault == 'across_page':
        before, after = pages[3].split('30.00 25.00', 1)
        pages[3:] = [before, '30.00 25.00' + after]
    elif fault == 'reverse_columns':
        pages[2] = pages[2].replace('项目 附注 2025年12月31日 2024年12月31日',
                                    '项目 附注 2024年12月31日 2025年12月31日')
        # Remove the standalone date so it cannot masquerade as column evidence.
        pages[2] = pages[2].replace('2025年12月31日\n单位', '单位')
    elif fault == 'unknown_currency':
        pages[2] = pages[2].replace(' 币种：人民币', '')
        pages.append('本公司采用人民币为记账本位币。')
    elif fault == 'different_currency':
        pages[3] = '币种：美元\n' + pages[3]
    else:
        pages[3] = '编制单位：另一股份有限公司\n' + pages[3]
    result = enrich(tmp_path, src)
    assert result['adopted_points'] == []
    if fault in {'current_cent', 'prior_cent'}:
        assert result['official_balance_reconciliation']['issues'] == ['TWO_PERIOD_BALANCE_IDENTITY_FAILED']


def test_new_version_never_relabels_or_overwrites_old_cache(tmp_path, source, monkeypatch):
    src, _ = source
    with monkeypatch.context() as old:
        old.setattr(parser, 'VERSION', 'value-retained-enrichment-v1')
        old_packet = parser.extract_retained_annual(tmp_path, src, evaluation_at=NOW,
                                                   cache_dir=tmp_path / '.tmp/balance-v2')
    old_files = {p: p.read_bytes() for p in (tmp_path / '.tmp/balance-v2').glob('*.json')}
    new = enrich(tmp_path, src)['source_extraction']
    assert old_packet['identity']['version'] != new['identity']['version']
    assert all(p.read_bytes() == raw for p, raw in old_files.items())
    assert len(list((tmp_path / '.tmp/balance-v2').glob('*.json'))) == len(old_files) + 1
    assert json.loads(next(iter(old_files.values())))['packet']['identity']['version'].endswith('-v1')


@pytest.mark.parametrize('index,symbol,digest,assets,liabilities,pages', [
    (0, '600519', '474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288',
     '303834844021.44', '49875590112.37', [57, 58, 59]),
    (1, '600887', 'd17b8c541c42f65d092317093eb0cfbb5aeed4f44eafa2d2f6182041cdcdbaac',
     '152098516632.34', '93554239954.18', [82, 83, 83]),
    (2, '000544', '55bac5078b18dfe1c7ff5bf79c90bf985e2635a7432c1aed2de579a63fe55002',
     None, None, []),
])
def test_optin_actual_three_sources_keep_old_evidence(tmp_path, monkeypatch, index, symbol,
                                                     digest, assets, liabilities, pages):
    configured = os.environ.get('BALANCE_SOURCE_REAL_ROOT')
    if not configured:
        pytest.skip('Explicit public-original root required; no downloads')
    root = Path(configured).resolve()
    assert tmp_path.resolve().is_relative_to(root / '.tmp'), 'Use a basetemp under real root/.tmp'
    directory = root / 'runtime/public-evidence/20261030-a-first' / str(index)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    old = json.loads((directory / 'fact-snapshot.json').read_bytes())
    src = parser.RetainedAnnualSource(**old['source_extraction']['identity']['source'])
    assert src.symbol == symbol and src.sha256 == digest
    assert hashlib.sha256((root / src.path).read_bytes()).hexdigest() == digest
    import requests
    monkeypatch.setattr(requests.sessions.Session, 'request',
                        lambda *a, **k: pytest.fail('Real retained source attempted network'))
    result = app.enrich_retained_company(root, src, [], evaluation_at=datetime.now(timezone.utc),
                                        cache_dir=tmp_path / 'cache', name=old['company_name'])
    assert [r['page'] for r in result['source_extraction']['balance_reconciliation_candidates']] == pages
    if assets is None:
        assert result['adopted_points'] == []
        assert result['official_balance_reconciliation']['status'] == 'REJECTED_WITH_REASON'
        assert parser._consolidated_currency_context(result['source_extraction']['page_texts']) == []
    else:
        point, = result['adopted_points']
        assert point['field_name'] == 'debt_ratio'
        with localcontext() as context:
            context.prec = 48
            assert Decimal(point['value']) == Decimal(liabilities) / Decimal(assets) * 100
        meta = point['metadata']
        assert meta['single_source_balance_verification'] is True
        assert meta['automatic_cross_source_verification'] is False
        assert meta['assurance_basis'] == 'source_reported_only'
        assert meta['derivation_rule_pit_status'] == 'NOT_ADMITTED' and not meta['economic_approval']
        proof = meta['balance_reconciliation']
        assert proof['current_residual'] == proof['prior_residual'] == '0.00'
        assert proof['owner_evidence']['identity_page_scope'] == [1, 12]
        for row in proof['balance_rows']:
            assert row['excerpt'] in result['source_extraction']['page_texts'][row['page'] - 1]
        assert old['adopted_points'] == []  # Old observations are never re-signed.
    assert result['action'] == 'no_order' and result['formal_eligibility'] is False
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before}
    (tmp_path / 'new-enrichment.json').write_text(json.dumps(result, ensure_ascii=False, default=str), encoding='utf-8')
