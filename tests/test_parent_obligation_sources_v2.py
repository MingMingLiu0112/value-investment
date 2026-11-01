from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.infrastructure.filings import parent_obligation_sources_v2 as adapter


def fake_original(tmp_path, monkeypatch):
    path = tmp_path / 'original.pdf'
    path.write_bytes(b'synthetic parser fixture, not issuer evidence')
    source = dict(id='fixture', path='original.pdf', symbol='000568',
        report_period='2026-06-30', sha256=sha256(path.read_bytes()).hexdigest(),
        identity_available_at='2026-10-31T12:00:00+00:00')
    packet = dict(sources={'fixture': source}, native_sha256='synthetic')
    monkeypatch.setattr(adapter, 'load_parent_facts', lambda *a, **kw: packet)
    pages = [''] * 46
    pages[37] = '母公司资产负债表 期末余额 期初余额'
    for page, label, amount in adapter._PARENT_ROWS.values():
        pages[page - 1] += '\n' + label + ' ' + amount
    monkeypatch.setattr(adapter, 'extract_pages', lambda *a, **kw: pages)
    return path, source, pages


def load(tmp_path):
    return adapter.load_parent_obligation_snapshot(root=tmp_path, native_path='unused',
        cutoff=datetime.now(timezone.utc))


def test_parent_cross_page_short_borrowing_and_current_rows_are_bound(tmp_path, monkeypatch):
    fake_original(tmp_path, monkeypatch)
    r = load(tmp_path)
    assert r['balances']['short_term_borrowings'] == '3001758333.34'
    assert r['facts']['short_term_borrowings']['physical_page'] == 39
    assert r['balances']['current_noncurrent_liabilities'] == '1510049088.62'
    assert r['balances']['current_liabilities_total'] == '17006819723.86'
    assert r['parent_debt_components_proven'] is False
    assert r['subsequent_repayment_proven'] is False


def test_original_tamper_header_loss_and_row_mismatch_rejected(tmp_path, monkeypatch):
    path, source, pages = fake_original(tmp_path, monkeypatch)
    path.write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        load(tmp_path)
    source['sha256'] = sha256(path.read_bytes()).hexdigest()
    pages[37] = '合并资产负债表 期末余额 期初余额'
    with pytest.raises(ValueError, match='header'):
        load(tmp_path)
    pages[37] = '母公司资产负债表 期末余额 期初余额'
    pages[38] = pages[38].replace('3001758333.34', '0')
    with pytest.raises(ValueError, match='row mismatch'):
        load(tmp_path)


def test_wrong_company_and_root_escape_rejected(tmp_path, monkeypatch):
    _, source, _ = fake_original(tmp_path, monkeypatch)
    source['symbol'] = '600519'
    with pytest.raises(ValueError, match='issuer'):
        load(tmp_path)
    source['symbol'] = '000568'
    source['path'] = '../outside.pdf'
    with pytest.raises(ValueError, match='outside root'):
        load(tmp_path)


def test_source_changed_during_parse_rejected(tmp_path, monkeypatch):
    path, _, pages = fake_original(tmp_path, monkeypatch)
    def change(*a, **kw):
        path.write_bytes(b'changed during parse')
        return pages
    monkeypatch.setattr(adapter, 'extract_pages', change)
    with pytest.raises(ValueError, match='changed during'):
        load(tmp_path)


def test_floor_assumption_cannot_be_backdated_or_presented_as_verified_need(tmp_path, monkeypatch):
    row = dict(value='60', unit='CNY', rationale='SYNTHETIC ASSUMPTION')
    packet = dict(generated_at='2026-11-01T00:00:00+00:00', source_bindings=[],
        historical_bindings=dict(cash_floor=dict(assumption=row)))
    path = tmp_path / 'floor.json'
    path.write_text(json.dumps(packet), encoding='utf-8')
    monkeypatch.setattr(adapter, '_FLOOR_SNAPSHOT_SHA', sha256(path.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match='not available'):
        adapter.load_frozen_cash_floor_assumption(root=tmp_path, relative_path='floor.json',
            cutoff=datetime(2026, 10, 31, tzinfo=timezone.utc))
    r = adapter.load_frozen_cash_floor_assumption(root=tmp_path, relative_path='floor.json',
        cutoff=datetime(2026, 11, 2, tzinfo=timezone.utc))
    assert r['debt_overlap_proven'] is False
    assert 'NOT_VERIFIED' in r['status']
    path.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='Unreviewed'):
        adapter.load_frozen_cash_floor_assumption(root=tmp_path, relative_path='floor.json',
            cutoff=datetime.now(timezone.utc))


def constraint_fixture(tmp_path, monkeypatch, *, acquired='2026-11-01T00:00:00+00:00'):
    original = tmp_path / 'law.html'
    original.write_text('<p>规则&amp; 条文</p>', encoding='utf-8')
    source = dict(source_id='synthetic-law', path=str(original),
        official_url='https://www.gov.cn/synthetic-test-only',
        sha256=sha256(original.read_bytes()).hexdigest(), actual_acquired_at=acquired,
        statement_scope='LAW_TEXT_ONLY', locators=[dict(physical_page_1based=None,
            article_locator='TEST_ONLY', needle='规则&条文')],
        supports_only=['Rule text only'], does_not_support=['Company compliance'])
    manifest = dict(created_at='2026-11-01T00:00:00+00:00', symbol='123456', sources=[source])
    path = tmp_path / 'minimal-new-sources-v1.json'
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(adapter, '_CONSTRAINT_MANIFEST_SHA', sha256(path.read_bytes()).hexdigest())
    return path, original


def test_supplemental_rule_text_is_verified_without_becoming_company_approval(tmp_path, monkeypatch):
    manifest, original = constraint_fixture(tmp_path, monkeypatch)
    cutoff = datetime(2026, 11, 2, tzinfo=timezone.utc)
    r = adapter.load_official_parent_constraint_disclosures(bundle_root=tmp_path, cutoff=cutoff)
    assert r['legal_distribution_certified'] is False
    assert r['parent_debt_decomposition_proven'] is False
    assert r['receivables_offset_against_payables_allowed'] is False
    assert r['action'] == 'no_order'
    original.write_text('tampered', encoding='utf-8')
    with pytest.raises(ValueError, match='hash mismatch'):
        adapter.load_official_parent_constraint_disclosures(bundle_root=tmp_path, cutoff=cutoff)
    manifest.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='manifest'):
        adapter.load_official_parent_constraint_disclosures(bundle_root=tmp_path, cutoff=cutoff)


def test_supplemental_new_acquisition_and_review_cannot_be_used_in_older_cutoff(tmp_path, monkeypatch):
    constraint_fixture(tmp_path, monkeypatch, acquired='2026-11-03T00:00:00+00:00')
    with pytest.raises(ValueError, match='source not available'):
        adapter.load_official_parent_constraint_disclosures(bundle_root=tmp_path,
            cutoff=datetime(2026, 11, 2, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match='review not available'):
        adapter.load_official_parent_constraint_disclosures(bundle_root=tmp_path,
            cutoff=datetime(2026, 10, 31, tzinfo=timezone.utc))


def test_real_original_obligation_stress_when_source_root_explicitly_supplied():
    root = os.environ.get('PARENT_OBLIGATION_SOURCE_ROOT')
    if not root:
        pytest.skip('Requires separately acquired, hash-bound public originals')
    from value_investment_agent.application.research.parent_obligation_review_v2 import review_parent_obligations_v2
    r = review_parent_obligations_v2(root=Path(root),
        native_path='runtime/e2-first-input-000568-20261031/native-facts-v5.json',
        floor_assumption_path='runtime/e2-first-input-000568-20261031/assumptions-20261031T111006911210Z.json',
        cutoff=datetime.now(timezone.utc), hypothetical_additional_distribution_cny='8500000000',
        future_investment_reserve_cny='0')
    rows = {s['scenario_id']: s for s in r['scenarios']}
    assert rows['IDENTIFIED_CURRENT_DEBT_ONLY_FLOOR_ADDITIONAL']['conditional_cash_residual_cny'] == '6504403911.65'
    assert rows['ALL_CURRENT_BOOK_RESERVE_FLOOR_ADDITIONAL']['conditional_cash_residual_cny'] == '510959260.32'
    assert rows['ALL_CURRENT_BOOK_RESERVE_FLOOR_INCLUDES_DEBT']['conditional_cash_residual_cny'] == '5022766682.28'
    assert rows['IDENTIFIED_CURRENT_DEBT_ONLY_FLOOR_INCLUDES_DEBT']['conditional_cash_residual_cny'] == '11016211333.61'
    assert r['current_distribution_capacity_cny'] is None and r['capacity_proven'] is False
    assert r['action'] == 'no_order'


def test_real_new_constraint_originals_when_bundle_explicitly_supplied():
    root = os.environ.get('PARENT_OBLIGATION_CONSTRAINT_BUNDLE')
    if not root:
        pytest.skip('Requires separately acquired official supplementary originals')
    r = adapter.load_official_parent_constraint_disclosures(bundle_root=root,
        cutoff=datetime.now(timezone.utc))
    assert len(r['sources']) == 4
    assert r['legal_distribution_certified'] is False
    assert r['operating_cash_floor_proven'] is False
