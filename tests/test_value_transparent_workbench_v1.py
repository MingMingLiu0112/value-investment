"""Public composition contracts; no paid execution, publication or private inputs."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket

import pytest

from value_investment_agent.application.product import value_transparent_workbench_v1 as app

NOW = datetime(2026, 11, 1, 16, tzinfo=timezone.utc)
SYMBOL = '123456'  # TEST_ONLY, intentionally not any retained real company.


def denied(*args, **kwargs):
    raise AssertionError('No network, provider, private context, locks or writes')


@pytest.fixture
def consumers(monkeypatch):
    values = {
        'select_current_value_candidates': dict(data_status='PROVIDER_OBSERVATIONS_NOT_FORMAL_FACTS',
            items=[dict(symbol=SYMBOL, channels=['quality'], reasons=['TEST_ONLY source observation'])],
            coverage={'universe_count': 4}, blockers=['LIMITED_SCOPE']),
        'load_company_profile': dict(symbol=SYMBOL, status='SOURCE_BOUND_PROFILE'),
        'load_source_company_profile': dict(symbol=SYMBOL, status='SOURCE_BOUND_ROUTE_ONLY'),
        'load_current_value_research_analysis': None,
        'read_first_research_input': dict(symbol=SYMBOL, status='SOURCE_BOUND_FIRST_INPUT_COMPILED',
            annual_ledgers={'base': {'rows': [{'profit': '17.50'}]}},
            valuation={'base_value': '8.123456'}, main_range_adopted=False),
        'read_main_valuation_revalidation': dict(symbol=SYMBOL,
            status='CONDITIONAL_RESEARCH_CANDIDATE_PENDING_ECONOMIC_REVIEW',
            annual_ledgers={'base': {'rows': [{'profit': '19.125'}]}},
            valuation={'base_value': '9.87654321'},
            price_policy={'status': 'NOT_PREPARED', 'rules': [], 'draft_prices': None},
            current_comparable=False, main_range_adopted=False),
        'load_operating_assumption_draft': dict(symbol=SYMBOL, status='MISSING_SOURCE',
            missing_sources=[{'path': 'config/TEST_ONLY-missing.json'}]),
        'load_registered_value_action_plans': dict(status='BLOCKED', action='no_order',
            items=[], blockers=['TEST_ONLY_PUBLICATION_UNAVAILABLE']),
        '_live': dict(symbol=SYMBOL, status='NOT_STARTED', reason='NO_VERIFIED_LIVE_RESEARCH_RESULT'),
    }
    calls = []
    for name in values:
        def loader(*args, _name=name, **kwargs):
            calls.append(_name)
            return deepcopy(values[_name])
        monkeypatch.setattr(app, name, loader)
    monkeypatch.setattr(app, 'read_operating_cash_consumption', denied)
    monkeypatch.setattr(socket.socket, 'connect', denied)
    return values, calls


def sections(result):
    assert result['schema_version'] == 'value-transparent-workbench-v1'
    assert result['action'] == 'no_order' and result['formal_eligibility'] is False
    assert result['quantity'] is None
    assert [s['id'] for s in result['sections']] == list(app.SECTION_IDS)
    assert all(set(s) == {'id', 'title', 'status', 'summary', 'data', 'blockers'} for s in result['sections'])
    return {s['id']: s for s in result['sections']}


def test_independent_native_results_no_valuation_math_or_side_effects(tmp_path, consumers, monkeypatch):
    values, calls = consumers
    monkeypatch.setattr(Path, 'mkdir', denied)
    monkeypatch.setattr(Path, 'write_bytes', denied)
    monkeypatch.setattr(Path, 'write_text', denied)
    result = app.read_value_transparent_workbench(root=tmp_path, symbol=SYMBOL, now=NOW)
    s = sections(result)
    native = s['valuation']['data']['native_results']
    assert native['first_input']['valuation'] == values['read_first_research_input']['valuation']
    assert native['main_revalidation']['annual_ledgers'] == values['read_main_valuation_revalidation']['annual_ledgers']
    assert s['valuation']['status'] == 'PARTIAL'  # missing old package is visible.
    assert s['continuity']['status'] == 'PRIVATE_CONTEXT_REQUIRED' and s['continuity']['data'] is None
    assert s['research']['data']['native_results']['new_live_research']['status'] == 'NOT_STARTED'
    assert s['price']['data']['native_results']['main_revalidation']['price_policy']['rules'] == []
    assert 'load_source_company_profile' not in calls
    assert json.dumps(result, ensure_ascii=False, allow_nan=False)


@pytest.mark.parametrize('damage', ['hash', 'escape', 'wrong_symbol', 'action'])
def test_bad_main_isolated_without_fallback_to_old_success(tmp_path, consumers, damage):
    values, _ = consumers
    p = tmp_path / 'source.json'
    p.write_text('{"TEST_ONLY":1}', encoding='utf-8')
    ref = dict(path='source.json', sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    value = values['read_main_valuation_revalidation']
    value['source_spec'] = ref
    if damage == 'hash':
        ref['sha256'] = '0' * 64
    elif damage == 'escape':
        ref['path'] = '../outside.json'
    elif damage == 'wrong_symbol':
        value['symbol'] = '654321'
    else:
        value['action'] = 'order'
    s = sections(app.read_value_transparent_workbench(root=tmp_path, symbol=SYMBOL, now=NOW))
    native = s['valuation']['data']['native_results']
    assert native['main_revalidation']['status'] == 'UNASSESSABLE'
    assert 'valuation' not in native['main_revalidation']
    assert native['first_input']['valuation']['base_value'] == '8.123456'
    assert s['valuation']['status'] == 'PARTIAL'
    assert s['valuation']['blockers']


def test_bound_sources_and_mid_read_mutation_fail_closed(tmp_path, consumers, monkeypatch):
    values, _ = consumers
    p = tmp_path / 'original.pdf'
    p.write_bytes(b'TEST_ONLY bytes, not a real company')
    ref = dict(path=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    values['read_main_valuation_revalidation']['source_spec'] = ref
    good = sections(app.read_value_transparent_workbench(root=tmp_path, symbol=SYMBOL, now=NOW))
    assert ref in good['evidence']['data']['source_bindings']
    def changed(*args, **kwargs):
        p.write_bytes(b'TEST_ONLY changed during read')
        return dict(symbol=SYMBOL, status='NOT_STARTED')
    monkeypatch.setattr(app, '_live', changed)
    bad = sections(app.read_value_transparent_workbench(root=tmp_path, symbol=SYMBOL, now=NOW))
    assert bad['valuation']['status'] == 'UNASSESSABLE'
    assert bad['valuation']['data'] is None


def test_windows_binding_and_native_manifest_relative_locator_are_distinct(tmp_path, consumers):
    values, _ = consumers
    (tmp_path / 'runtime').mkdir()
    p = tmp_path / 'runtime/source.json'
    p.write_bytes(b'TEST_ONLY retained manifest')
    ref = dict(path='runtime\\source.json', sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    main = values['read_main_valuation_revalidation']
    main['source_spec'] = ref
    # Not a project binding: the native parser resolves this inside its bundle.
    main['official_constraints'] = {'sources': [{'path': 'report.pdf', 'sha256': 'a' * 64}]}
    main['research_draft'] = {'source_bindings': [{'source_id': 'TEST_ONLY', 'pdf_sha256': 'a' * 64}]}
    s = sections(app.read_value_transparent_workbench(root=tmp_path, symbol=SYMBOL, now=NOW))
    assert s['valuation']['data']['native_results']['main_revalidation']['valuation']['base_value'] == '9.87654321'
    assert {'path': 'runtime/source.json', 'sha256': ref['sha256']} in s['evidence']['data']['source_bindings']


def test_absolute_native_binding_must_stay_inside_project(tmp_path, consumers):
    values, _ = consumers
    p = tmp_path / 'source.json'
    p.write_bytes(b'TEST_ONLY source')
    main = values['read_main_valuation_revalidation']
    main['source_spec'] = dict(path=str(p), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    s = sections(app.read_value_transparent_workbench(root=tmp_path, symbol=SYMBOL, now=NOW))
    assert s['valuation']['data']['native_results']['main_revalidation']['status'] != 'UNASSESSABLE'
    main['source_spec']['path'] = str(tmp_path.parent / 'outside.json')
    s = sections(app.read_value_transparent_workbench(root=tmp_path, symbol=SYMBOL, now=NOW))
    assert s['valuation']['data']['native_results']['main_revalidation']['status'] == 'UNASSESSABLE'


def test_existing_research_and_cash_are_not_hidden_by_no_new_live(tmp_path, consumers):
    values, _ = consumers
    ledger = {'rows': [{'year': 1, 'opening_cash': '500.25', 'distribution': '17.125'}]}
    economic_path = {'period_basis': 'MODEL_YEAR_NOT_DISCLOSED_FISCAL_YEAR',
                     'scenarios': [{'scenario': 'base', 'years': [{'model_year': 1}]}]}
    existing = dict(symbol=SYMBOL, status='CONDITIONAL_ANALYSIS_VERIFIED',
        input_descriptor_sha256='a' * 64, research_as_of='2026-10-28',
        valuation_date='2026-06-30', thesis='TEST_ONLY existing source-bound thesis',
        counter_evidence=[{'kind': 'COUNTER', 'text': 'TEST_ONLY volume pressure'}],
        thesis_breakers=[{'text': 'TEST_ONLY invalidation'}],
        joint_capital_review={'scenarios': [{'scenario': 'base', 'ledger': ledger}],
            'economic_path': economic_path, 'distribution_diagnostics': {'status': 'CONDITIONAL_DIAGNOSTICS'}},
        source_native_cash_review={'status': 'TEST_ONLY_MATERIAL'})
    values['load_current_value_research_analysis'] = existing
    s = sections(app.read_value_transparent_workbench(root=tmp_path, symbol=SYMBOL, now=NOW))
    research = s['research']['data']['native_results']
    assert research['new_live_research']['status'] == 'NOT_STARTED'
    assert research['existing_research']['thesis'] == existing['thesis']
    assert research['existing_research']['counter_evidence'] == existing['counter_evidence']
    cash = s['cash']['data']['native_results']['existing_analysis']
    assert s['cash']['status'] != 'NOT_STARTED'
    assert cash['joint_capital_review']['scenarios'][0]['ledger'] == ledger
    assert cash['joint_capital_review']['economic_path'] == economic_path
    assert cash['source_native_cash_review'] == existing['source_native_cash_review']
    cash['joint_capital_review']['scenarios'][0]['ledger']['rows'][0]['distribution'] = '0'
    assert ledger['rows'][0]['distribution'] == '17.125'


@pytest.mark.parametrize('native_decision', ['WAIT', 'NO_TRADE', 'UNASSESSABLE'])
def test_native_decisions_are_not_replaced_by_workbench_authority(tmp_path, consumers, native_decision):
    values, _ = consumers
    values['load_registered_value_action_plans'] = dict(status='VALUE_RESEARCH_OBSERVATION',
        action='no_order', items=[dict(symbol=SYMBOL, candidate_action=native_decision,
            blockers=['TEST_ONLY_EXACT_NATIVE_REASON'])])
    values['load_current_value_research_analysis'] = dict(symbol=SYMBOL,
        status='CONDITIONAL_ANALYSIS_VERIFIED', economic_review_status='PENDING_EXACT_VERSION_REVIEW',
        current_alignment={'status': 'BLOCKED', 'reason_codes': ['TEST_ONLY_QUOTE_NOT_CURRENT']},
        strategy_admitted=True, formal_eligibility=True, blockers=['TEST_ONLY_REVIEW'])
    result = app.read_value_transparent_workbench(root=tmp_path, symbol=SYMBOL, now=NOW)
    s = sections(result)
    native = s['decision']['data']['native_results']
    assert native['public_core']['items'][0]['candidate_action'] == native_decision
    assert native['public_core']['items'][0]['blockers'] == ['TEST_ONLY_EXACT_NATIVE_REASON']
    states = native['existing_analysis']['native_statuses']
    assert states['research']['economic_review_status'] == 'PENDING_EXACT_VERSION_REVIEW'
    assert states['price']['current_alignment']['status'] == 'BLOCKED'
    assert states['approval']['formal_eligibility'] is True  # preserve native fact, no new grant.
    assert result['formal_eligibility'] is False and result['quantity'] is None
    assert s['decision']['data']['workbench_authority']['scope'].endswith('NOT_A_NATIVE_DECISION')


def test_profile_fallback_exact_absence_only(tmp_path, consumers):
    values, calls = consumers
    values['load_company_profile'] = dict(symbol=SYMBOL, status='UNASSESSABLE', blockers=['BROKEN_CURRENT'])
    app.read_value_transparent_workbench(root=tmp_path, symbol=SYMBOL, now=NOW)
    assert 'load_source_company_profile' not in calls
    values['load_company_profile']['blockers'] = ['NO_CURRENT_SOURCE_BOUND_RESEARCH']
    result = sections(app.read_value_transparent_workbench(root=tmp_path, symbol=SYMBOL, now=NOW))
    assert result['profile']['data']['native_results']['profile']['status'] == 'SOURCE_BOUND_ROUTE_ONLY'
    assert 'load_source_company_profile' in calls


def test_live_read_uses_no_locks_and_projects_no_private_fields(tmp_path, monkeypatch):
    base = tmp_path / 'tasks'
    task_id = 'rt-' + 'a' * 32
    (base / task_id).mkdir(parents=True)
    pin = {'path': 'TEST_ONLY.json', 'sha256': 'a' * 64}
    class Native:
        def __init__(self, root):
            self.base = base
        def _load(self, ident, *, recover):
            assert recover is False and ident == task_id
            return {'symbol': SYMBOL}, {'updated_at': NOW.isoformat()}, pin
        def _view(self, spec, state, binding, now):
            return dict(symbol=SYMBOL, status='SUCCEEDED', task_id=task_id,
                scope='LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED', research_draft={'FUNDAMENTAL': {}},
                record_binding=pin, private_config={'secret': 'TEST_ONLY_MUST_NOT_ESCAPE'}, raw_response='PRIVATE')
        read = list_for_symbol = create = run = resume = _lock = denied
    monkeypatch.setattr(app, 'LiveOperatingTaskService', Native)
    public, native = app._live(tmp_path, SYMBOL, NOW)
    assert 'private_config' not in public and 'raw_response' not in public
    assert native['private_config']  # retained internally only for the native cash consumer.


@pytest.mark.parametrize('symbol,now', [('bad', NOW), (SYMBOL, NOW.replace(tzinfo=None))])
def test_invalid_identity_clock_rejected_before_consumers(tmp_path, consumers, symbol, now):
    _, calls = consumers
    with pytest.raises(ValueError):
        app.read_value_transparent_workbench(root=tmp_path, symbol=symbol, now=now)
    assert calls == []
