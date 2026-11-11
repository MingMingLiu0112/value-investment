"""TEST_ONLY layouts and explicitly opted-in retained official source replay."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

import pytest

from test_official_balance_reconciliation import pages as balance_pages
from value_investment_agent.application.research import value_evidence_enrichment_v1 as app
from value_investment_agent.infrastructure.screening import value_evidence_enrichment_v1 as parser
from value_investment_agent.financial_quality import _accepted

NOW = datetime(2026, 10, 25, 4, tzinfo=timezone.utc)


def pages():
    result = balance_pages()
    result[0] += ('\n短期借款 12.00 10.00\n一年内到期的非流动负债 5.00 4.00\n'
        '长期借款 15.00 14.00\n应付债券 10.00 8.00\n租赁负债 3.00 2.00\n'
        '长期应付款 2.00 1.00\n财务附注中报表的单位为：元')
    result += ['七、合并财务报表项目注释\n32、短期借款\n单位：元\n'
        '项目 期末余额 期初余额\n信用借款 12.00 10.00\n合计 12.00 10.00\n其他说明：',
        '43、一年内到期的非流动负债\n单位：元\n项目 期末余额 期初余额\n'
        '一年内到期的长期借款 4.00 3.00\n一年内到期的租赁负债 1.00 1.00\n'
        '合计 5.00 4.00\n其他说明：\n47、租赁负债\n单位：元\n项目 期末余额 期初余额\n'
        '租赁付款额 4.00 3.00\n减：一年以内到期的租赁负债 -1.00 -1.00\n合计 3.00 2.00',
        '52、其他非流动负债\n单位：元\n项目 期末余额 期初余额\n质押借款 7.00\n合计 7.00',
        '十、与金融工具相关的风险\n①2025年12月31日\n金融负债项目 其他金融负债 合计\n'
        '其他非流动负债 7.00 7.00\n②2024年12月31日\n其他非流动负债\n'
        '本集团的带息债务主要为人民币浮动利率借款合同，金额合计为0.01万元，'
        '及人民币计价的固定利率合同，金额合计为0.02万元。\n'
        '筹资活动产生的各项负债变动情况\n□适用 不适用',
        '十九、母公司财务报表主要项目注释\n32、短期借款\n单位：元\n'
        '项目 期末余额 期初余额\n信用借款 999.00 888.00\n合计 999.00 888.00']
    return result


@pytest.fixture
def retained(tmp_path, monkeypatch):
    original = tmp_path / 'official.pdf'
    original.write_bytes(b'TEST_ONLY original decoder seam; not official evidence')
    text = pages()
    monkeypatch.setattr(parser, 'extract_pages', lambda path, limit: text[:limit])
    source = parser.RetainedAnnualSource('000498', '2025-12-31', 'official.pdf',
        hashlib.sha256(original.read_bytes()).hexdigest(),
        'https://static.cninfo.com.cn/TEST_ONLY.pdf', '2026-10-25T01:00:00+00:00')
    return source, text


def enrich(root, source):
    return app.enrich_retained_company(root, source, [], evaluation_at=NOW,
        cache_dir=root / '.tmp/financing-tests')


def composition(result):
    return result['source_financial_funding_scope']['industrial_financing_composition']


def test_six_bucket_arithmetic_current_leases_not_added_twice(tmp_path, retained):
    result = enrich(tmp_path, retained[0])
    review = composition(result)
    assert review['six_balance_buckets_cny'] == '47.00'
    assert review['six_buckets_plus_other_noncurrent_cny'] == '54.00'
    assert review['current_lease_dedup_residuals'] == dict(value='0.00', prior_value='0.00')
    assert review['balance_subset_minus_reported_interest_contracts_cny'] == '-246.00'
    assert all(r['status'] == 'EXACT_PARSED_COMPONENT_SUM' for r in review['note_reconciliations'][:3])
    unknown = [r for r in review['rows'] if r['note'] == '其他非流动负债']
    assert all(r['value'] is None and r['prior_value'] is None for r in unknown)
    assert all(r['single_printed_amount'] == '7.00' for r in unknown)
    assert not review['complete_debt_verified'] and review['interest_bearing_debt'] is None
    assert not result['debt_scope']['complete_debt_verified']
    assert result['after']['calculation_details']['accepted_fields'] == ['debt_ratio']
    observation, = [p for p in result['sourced_arithmetic_points']
        if p['field_name'] == 'financing_liability_composition']
    assert observation['metadata']['financing_composition_review'] == review
    assert not _accepted(observation)
    assert all(p['field_name'] != 'interest_bearing_debt' for p in result['adopted_points'])
    assert result['action'] == 'no_order' and not result['formal_eligibility']


@pytest.mark.parametrize('fault', ['owner', 'currency', 'unit', 'reversed', 'missing_component',
    'wrong_total', 'third_column', 'parent', 'conflicting_continuation'])
def test_source_context_failures_never_prove_components(tmp_path, retained, fault):
    source, text = retained
    if fault == 'owner': text[3] = '编制单位：另一子公司有限公司\n' + text[3]
    elif fault == 'currency': text[3] = text[3].replace('单位：元', '单位：元 币种：美元')
    elif fault == 'unit': text[3] = text[3].replace('单位：元', '')
    elif fault == 'reversed': text[3] = text[3].replace('期末余额 期初余额', '期初余额 期末余额')
    elif fault == 'missing_component': text[3] = text[3].replace('信用借款 12.00 10.00', '')
    elif fault == 'wrong_total': text[3] = text[3].replace('合计 12.00 10.00', '合计 13.00 10.00')
    elif fault == 'third_column': text[3] = text[3].replace('信用借款 12.00 10.00', '信用借款 12.00 10.00 8.00')
    elif fault == 'parent': text[3] = '十九、母公司财务报表主要项目注释\n' + text[3]
    elif fault == 'conflicting_continuation':
        text[3:4] = [text[3].split('信用借款')[0],
            '编制单位：另一子公司有限公司\n信用借款 12.00 10.00\n合计 12.00 10.00']
    review = composition(enrich(tmp_path, source))
    matching = [r for r in review.get('note_reconciliations', []) if r['note'] == '短期借款']
    assert not matching or all(r['status'] != 'EXACT_PARSED_COMPONENT_SUM' for r in matching)
    assert not review['complete_debt_verified']


def test_source_hash_and_actual_cutoff_rechecked(tmp_path, retained):
    source, _ = retained
    enrich(tmp_path, source)
    with pytest.raises(ValueError, match='cutoff'):
        enrich(tmp_path, replace(source, available_at='2027-01-01T00:00:00+00:00'))
    (tmp_path / source.path).write_bytes(b'TAMPERED TEST_ONLY')
    with pytest.raises(ValueError, match='hash mismatch'):
        enrich(tmp_path, source)


def test_dated_financial_table_cannot_borrow_unit_or_prior_date():
    text = pages()
    text[0] = text[0].replace('财务附注中报表的单位为：元', '')
    assert parser.extract_financing_note_candidates(text, '2025-12-31')['current_financial_liabilities'] == []
    text = pages()
    text[-2] = text[-2].replace('①2025年12月31日', '①2024年12月31日')
    assert parser.extract_financing_note_candidates(text, '2025-12-31')['current_financial_liabilities'] == []


@pytest.mark.parametrize('declaration', ['', '编制单位：测试股份有限公司\n'])
def test_same_owner_continuation_retains_explicit_period_and_units(declaration):
    text = pages()
    prefix, suffix = text[3].split('信用借款', 1)
    text[3:4] = [prefix, declaration + '信用借款' + suffix]
    result = parser.extract_financing_note_candidates(text, '2025-12-31')
    matching = [r for r in result['rows'] if r['note'] == '短期借款']
    assert [r['value'] for r in matching] == ['12.00', '12.00']
    assert all(r['unit_evidence_page'] == 4 and r['page'] == 5 for r in matching)


@pytest.mark.parametrize('declaration', ['编制单位：测试股份有限公司子公司有限公司\n',
    '单位：元 币种：美元\n', '项目 期初余额 期末余额\n'])
def test_conflicting_continuation_cannot_borrow_parent_context(declaration):
    text = pages()
    prefix, suffix = text[3].split('信用借款', 1)
    text[3:4] = [prefix, declaration + '信用借款' + suffix]
    result = parser.extract_financing_note_candidates(text, '2025-12-31')
    assert not [r for r in result['rows'] if r['note'] == '短期借款']


def test_core_balance_buckets_use_same_strict_issuer_context():
    text = pages()
    text[0] = text[0].replace('短期借款 12.00 10.00', '')
    text[1] = '编制单位：测试子公司有限公司\n短期借款 999.00 888.00\n' + text[1]
    result = parser.extract_financing_note_candidates(text, '2025-12-31')
    assert not [r for r in result['balance_rows'] if r['field_name'] == 'short_term_borrowings']


@pytest.mark.parametrize('declaration', ['币种：美元\n单位：元',
    '币种：美元\n币种：人民币\n单位：元',
    '2024年12月31日\n单位：元',
    '2024年12月31日\n2025年12月31日\n单位：元',
    '2026年12月31日\n单位：元'])
def test_table_currency_and_date_conflicts_survive_unit_and_header_repetition(
        tmp_path, retained, declaration):
    source, text = retained
    formerly_accepted = [r for r in parser.extract_financing_note_candidates(text, source.period)['rows']
        if r['note'] == '短期借款']
    text[3] = text[3].replace('单位：元', declaration)
    # A repeated header/unit on the following page is not a new table boundary.
    prefix, suffix = text[3].split('项目 期末余额 期初余额', 1)
    text[3:4] = [prefix, '单位：元\n项目 期末余额 期初余额'+suffix]
    result = enrich(tmp_path, source)
    review = composition(result)
    assert not [r for r in review['rows'] if r['note'] == '短期借款']
    assert not [r for r in review['note_reconciliations'] if r['note'] == '短期借款']
    # A genuinely new note/table must still be usable, not globally quarantined.
    assert any(r['note'] == '租赁负债' for r in review['rows'])
    register_and_reverify(tmp_path, result, tmp_path/'runtime/TEST_ONLY-local-conflict',
        rejected_rows=formerly_accepted)


@pytest.mark.parametrize('declaration', ['币种：人民币\n单位：元',
    '2025年12月31日\n单位：元',
    '2025年12月31日 2024年12月31日\n单位：元'])
def test_matching_explicit_local_context_is_allowed(declaration):
    text = pages()
    text[3] = text[3].replace('单位：元', declaration)
    result = parser.extract_financing_note_candidates(text, '2025-12-31')
    assert [r['value'] for r in result['rows'] if r['note'] == '短期借款'] == ['12.00', '12.00']


@pytest.mark.parametrize('new_unit,expected', [('', []), ('单位：元\n', ['12.00', '12.00'])])
def test_new_subtable_must_not_inherit_conflicting_unit(new_unit, expected):
    text = pages()
    text[3] = text[3].replace('单位：元',
        '币种：美元\n单位：元\n（2）新的分类表\n'+new_unit)
    result = parser.extract_financing_note_candidates(text, '2025-12-31')
    assert [r['value'] for r in result['rows'] if r['note'] == '短期借款'] == expected


def test_signed_dedup_failure_is_not_hidden(tmp_path, retained):
    source, text = retained
    text[4] = text[4].replace('-1.00 -1.00', '1.00 1.00')
    result = composition(enrich(tmp_path, source))
    assert result['current_lease_dedup_residuals'] == dict(value='2.00', prior_value='2.00')
    assert any(r['status'] == 'MISSING_OR_NONRECONCILING_COMPONENTS' for r in result['note_reconciliations'])
    assert not result['complete_debt_verified']


@pytest.mark.parametrize('vat,residual', [('3.00 2.00', '0.00'), ('4.00 2.00', '-1.00'), ('', None)])
def test_other_current_vat_exclusion_is_observed_not_full_financing(tmp_path, retained, vat, residual):
    source, text = retained
    text[5] += ('\n44、其他流动负债\n单位：元\n项目 期末余额 期初余额\n'
        '未终止确认的应收票据 2.00 2.00\n待结转增值税 '+vat+'\n合计 5.00 4.00')
    text[6] = text[6].replace('其他非流动负债 7.00 7.00',
        '其他非流动负债 7.00 7.00\n其他流动负债 2.00 2.00')
    result = composition(enrich(tmp_path, source))
    assert result['other_current_financial_table_residual_cny'] == residual
    assert not result['complete_debt_verified'] and result['interest_bearing_debt'] is None


def register_and_reverify(root, result, runtime, *, rejected_rows=None):
    from value_investment_agent.research_case import ResearchCase
    from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository
    from value_investment_agent.research_artifacts import parse_stored_artifact_payload
    from value_investment_agent.valuation_models.fcff import FinancialFacts
    source = parser.RetainedAnnualSource(**result['source_extraction']['identity']['source'])
    case = ResearchCase(symbol=source.symbol, name='SOURCE_REPLAY_NOT_APPROVED', as_of=NOW.date(),
        generated_at=NOW, run_id='financing-test', research_version='unapproved', industry='UNASSESSED',
        investment_path='UNASSESSED', thesis='UNASSESSED', return_driver='UNASSESSED',
        mispricing_hypothesis='UNASSESSED', financial_summary={}, positives=[], counter_evidence=[],
        thesis_breakers=[], next_events=[], evidence_status='PARTIAL', valuation_status='NOT_ASSESSED',
        research_status='DATA_CHECK', blockers=['MISSING_ECONOMIC_INPUTS'], evidence_refs=[],
        quote_date=None, financial_period=date(2025, 12, 31),
        missing_date_reasons={'quote_date': 'No price used by financing observations'})
    facts = FinancialFacts(source.symbol, NOW.date(), False, [], ['MISSING_ECONOMIC_INPUTS'])
    repository = InMemoryResearchArtifactRepository()
    registered = app.register_enriched_research(result, root=root, points=[], repository=repository,
        case=case, facts=facts, run_id='financing-test')
    payload = parse_stored_artifact_payload(repository.load_by_id(registered['research_case_artifact_id']))
    observations = payload['financial_summary']['value_enrichment']['sourced_arithmetic_observations']
    assert observations == result['sourced_arithmetic_points']
    assert payload['research_status'] == 'DATA_CHECK' and payload['valuation_status'] == 'NOT_ASSESSED'
    runtime.mkdir(parents=True)
    export, target = runtime/'financial.json', runtime/'result.json'
    export.write_text(json.dumps({'points': []}), encoding='utf-8')
    saved = dict(result, research_registration=registered)

    def verify():
        target.write_text(json.dumps(saved, default=str), encoding='utf-8')
        return app.verify_enrichment_adoption(root=root,
            result_binding=dict(path=target.relative_to(root).as_posix(),
                sha256=hashlib.sha256(target.read_bytes()).hexdigest()),
            financial_export_path=export, financial_export_sha256=hashlib.sha256(export.read_bytes()).hexdigest(),
            evaluation_at=NOW)

    checked = verify()
    assert checked['research_inputs_updated'] and checked['new_fact_approvals'] == 0
    assert checked['source_financial_funding_scope'] == result['source_financial_funding_scope']
    assert not checked['complete_debt_verified'] and checked['action'] == 'no_order'
    observation = next(p for p in saved['sourced_arithmetic_points']
        if p['field_name'] == 'financing_liability_composition')
    if rejected_rows is None:
        observation['metadata']['financing_composition_review']['complete_debt_verified'] = True
    else:
        # Rehashing the outer result must not resurrect conflicting table rows.
        observation['metadata']['financing_composition_review']['rows'].extend(rejected_rows)
    with pytest.raises(ValueError, match='revalidated source facts'):
        verify()
    return checked


def test_typed_researchcase_and_cold_consumer_reject_rehashed_observation(tmp_path, retained):
    result = enrich(tmp_path, retained[0])
    register_and_reverify(tmp_path, result, tmp_path/'runtime/TEST_ONLY-financing')


def test_real_000498_original_replay(tmp_path):
    raw = os.environ.get('FINANCING_COMPOSITION_REAL_ROOT')
    if not raw:
        pytest.skip('Explicit retained official source root required; no network')
    root = Path(raw)
    source = parser.RetainedAnnualSource('000498', '2025-12-31',
        'runtime/daily-marketwide/20261025T0033265033467Z/research-priority-v2-enrichment/000498-official-original/original.pdf',
        'ecbc66587299817b4c51f8f029ccc77baf4b61b004477c712c4973b8226ffa17',
        'https://static.cninfo.com.cn/finalpage/2026-04-18/1225123102.PDF',
        '2026-10-25T00:34:46.716026+00:00')
    original_hash = hashlib.sha256((root/source.path).read_bytes()).hexdigest()
    result = enrich(root, source)
    review = composition(result)
    assert review['six_balance_buckets_cny'] == '35678798290.23'
    assert review['six_buckets_plus_other_noncurrent_cny'] == '36852337415.18'
    assert review['reported_interest_contracts_total_cny'] == '36829941000.00'
    assert review['balance_subset_minus_reported_interest_contracts_cny'] == '22396415.18'
    assert review['other_current_non_vat_cny'] == '1876210400.64'
    assert review['other_current_financial_table_residual_cny'] == '0.00'
    assert review['current_lease_dedup_residuals'] == dict(value='0.00', prior_value='0.00')
    assert len(review['balance_comparisons']) == 7
    assert all(Decimal(v) == 0 for row in review['balance_comparisons'] for v in row['residuals'].values())
    assert {r['page'] for r in review['rows']} == {240, 241, 242, 243, 246, 247, 249, 251}
    assert len(review['rows']) == 51
    assert all(r['owner_evidence']['legal_name'] == '山东高速路桥集团股份有限公司' for r in review['rows'])
    assert all(r['status'] != 'EXACT_PARSED_COMPONENT_SUM' for r in review['note_reconciliations']
        if r['note'] in {'其他流动负债', '其他非流动负债'})
    assert len(result['adopted_points']) == 1 and result['adopted_points'][0]['field_name'] == 'debt_ratio'
    assert result['after']['coverage_ratio'] == Decimal('0.1111')
    assert not result['debt_scope']['complete_debt_verified']
    # A real original is consumed through typed ResearchCase in a disposable
    # in-memory repository; no current registry or production pointer is changed.
    isolated = tmp_path/'source-replay'
    copy = isolated/source.path
    copy.parent.mkdir(parents=True)
    copy.write_bytes((root/source.path).read_bytes())
    register_and_reverify(isolated, deepcopy(result), isolated/'runtime/TEST_ONLY-financing')
    assert hashlib.sha256((root/source.path).read_bytes()).hexdigest() == original_hash == source.sha256


@pytest.mark.parametrize('symbol', ['600519', '600887'])
def test_real_sibling_source_remains_unapproved(symbol):
    raw = os.environ.get('FINANCING_COMPOSITION_REAL_ROOT')
    if not raw:
        pytest.skip('Explicit retained official source root required; no network')
    root = Path(raw)
    previous = root/('runtime/retained-income-research-adoption/a26132256225470c97eec792b250fb71/'
        +symbol+'/'+symbol+'.json')
    declaration = json.loads(previous.read_bytes())['source_extraction']['identity']['source']
    source = parser.RetainedAnnualSource(**declaration)
    result = enrich(root, source)
    assert not result['debt_scope']['complete_debt_verified']
    assert all(p['field_name'] != 'interest_bearing_debt' for p in result['adopted_points'])
    assert not result['formal_eligibility'] and result['action'] == 'no_order'
