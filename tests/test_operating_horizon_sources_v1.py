"""Synthetic bound originals; no network or financial admission."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_operating_horizon_draft_v1 import context
from value_investment_agent.application.research.agent_review import operating_horizon_sources_v1 as mod

NOW = datetime(2026, 11, 5, 10, tzinfo=timezone.utc)


@pytest.fixture
def source_env(tmp_path_factory, monkeypatch, context):
    root = tmp_path_factory.mktemp('hs')
    def no_network(*args, **kwargs):
        pytest.fail('Network forbidden')
    monkeypatch.setattr(socket.socket, 'connect', no_network)
    runtime = root / 'runtime'
    runtime.mkdir()
    original = runtime / 'interim.pdf'
    original.write_bytes(b'TEST_ONLY synthetic original, not PDF admission')
    source = dict(symbol='123456',period='2026-06-30',path='runtime/interim.pdf',
        sha256=mod._hash(original.read_bytes()), source_url='https://test-only.invalid/report.pdf',
        available_at='2026-11-04T00:00:00+00:00')
    receipt = dict(source=source,source_id='TEST_ONLY:interim',fetched_at=source['available_at'],
        completed_at='2026-11-04T00:01:00+00:00',published_date='2026-08-01')
    receipt_path = runtime / 'receipt.json'
    receipt_path.write_bytes(mod._bytes(receipt))
    receipt_pin = dict(path='runtime/receipt.json',sha256=mod._hash(receipt_path.read_bytes()))
    base = deepcopy(context)
    base.update(as_of=NOW.isoformat(),financial_basis='2025-12-31')
    for row in base['evidence']:
        row['physical_page'] = 1
    base_file = runtime / 'base.json'
    base_file.write_bytes(mod._bytes(base))
    base_pin = dict(path='runtime/base.json',sha256=mod._hash(base_file.read_bytes()))
    base['source_binding'] = base_pin
    def base_loader(*,root,symbol,now,binding=None):
        if binding is not None and binding != base_pin:
            raise ValueError('BASE_BINDING_CHANGED')
        if mod._hash(base_file.read_bytes()) != base_pin['sha256']:
            raise ValueError('BASE_CHANGED')
        result = deepcopy(base)
        result['as_of'] = now.isoformat()
        return result
    monkeypatch.setattr(mod.base_sources, 'build_operating_source_context', base_loader)
    events = []
    def cash_replay(**kwargs):
        events.append('cash_verifier')
        for binding in kwargs['receipt_bindings']:
            mod._bound(root,binding['receipt_binding'])
        return {}
    def load_receipt(**kwargs):
        events.append('official_verifier')
        packet = mod._bound(root,kwargs['receipt_binding'])
        if packet['source']['sha256'] != mod._hash(original.read_bytes()):
            raise ValueError('ORIGINAL_CHANGED')
        return packet
    monkeypatch.setattr(mod.cash,'replay_bound_parent_cash_observations',cash_replay)
    monkeypatch.setattr(mod.cash,'_receipt_issuer_query',lambda **kwargs:'TEST_ONLY')
    monkeypatch.setattr(mod.receipts,'load_retained_official_report',load_receipt)
    page = 'TEST_ONLY heading\n完整首句说明并表范围。\n完整第二句说明存量业务。\nNEXT\nother'
    monkeypatch.setattr(mod.pdf_text,'extract_pages',lambda *args,**kwargs:[page])
    def statement(*,root,source,evaluation_at):
        events.append('statement_parser')
        row = deepcopy(base['evidence'][0])
        row.update(id='TEST_ONLY:h1-revenue',period='2026-06-30',period_basis='H1',
            pdf_sha256=source['sha256'],available_at=source['available_at'],source_binding=source)
        return dict(symbol='123456',source_binding=source,action='no_order',financial_quality_granted=False,
                    evidence=[row],gaps=[])
    monkeypatch.setattr(mod.statements,'load_operating_statement_basis',statement)
    config = root / mod.CONFIG
    config.parent.mkdir()
    selection = dict(issuer_name='TEST_ONLY',parent_cash_observation_receipts=[dict(period='2026-06-30',receipt_binding=receipt_pin)],
        excerpts=[dict(period='2026-06-30',physical_page=1,start_marker='TEST_ONLY heading',end_marker='NEXT')])
    config.write_bytes(mod._bytes(dict(schema_version=mod.VERSION,action='no_order',cases={'123456':selection})))
    def load(binding=None, now=NOW):
        return mod.build_operating_horizon_source_context(root=root,symbol='123456',now=now,binding=binding)
    return SimpleNamespace(root=root,original=original,receipt_path=receipt_path,receipt=receipt,
        base_file=base_file,config=config,selection=selection,load=load,page=page,events=events)


def test_manifest_cold_replay_ignores_current_selection(source_env):
    env=source_env
    first=env.load()
    assert env.events[:2] == ['cash_verifier','official_verifier']
    env.config.write_bytes(b'{}')
    assert env.load(first['source_binding']) == first
    assert all(len(row['text'])<=2000 for row in first['evidence'])
    excerpt=next(row for row in first['evidence'] if row['unit']=='TEXT')
    assert env.page[excerpt['start_offset']:excerpt['end_offset']] == excerpt['text']
    assert excerpt['text_sha256']==mod._hash(excerpt['text'].encode('utf-8'))
    assert excerpt['physical_page']==1 and excerpt['pdf_sha256']==env.receipt['source']['sha256']
    assert excerpt['available_at']=='2026-11-04T00:01:00+00:00'
    assert len(mod._bytes(first).decode('utf-8'))<=48000
    h1=next(r for r in first['evidence'] if r.get('id')=='TEST_ONLY:h1-revenue')
    assert h1['period_basis']=='H1' and h1['period']=='2026-06-30'
    assert first['parent_cash_observation_receipts'] == env.selection['parent_cash_observation_receipts']


def test_v1_annual_task_defaults_to_the_versioned_horizon_source_contract(source_env):
    """D2 v1 and E2 must bind the same horizon source-manifest shape."""
    from value_investment_agent.application.research.agent_review import operating_horizon_task_v1 as task

    service = task.OperatingHorizonTaskService(source_env.root, test_provider=object())
    context = service.source_loader(root=source_env.root, symbol='123456', now=NOW)
    assert context['source_binding']['path'].startswith('runtime/operating-horizon-sources-v1/')
    assert service.source_loader is task.sources.build_operating_horizon_source_context


def test_source_bound_scope_declaration_is_hashed_into_context(source_env):
    env=source_env
    env.selection["scope_decomposition"]={
        "scope_change_expected":False,
        "contributions":[{"scope_kind":"LEGACY_ORGANIC","revenue_change_cny":"1",
            "profit_change_cny":"1","evidence_ids":["TEST_ONLY:interim:horizon-p1"]}],
    }
    env.config.write_bytes(mod._bytes(dict(schema_version=mod.VERSION,action='no_order',cases={'123456':env.selection})))
    first=env.load()
    assert first["scope_decomposition"]["scope_change_expected"] is False
    assert env.load(first["source_binding"])["scope_decomposition"]==first["scope_decomposition"]


@pytest.mark.parametrize('damage',['original','receipt','base','manifest','implementation'])
def test_cold_replay_provenance_failures(source_env,monkeypatch,damage):
    env=source_env; first=env.load()
    if damage=='implementation':
        monkeypatch.setattr(mod,'implementation',lambda:{'changed':'x'})
    else:
        target={'original':env.original,'receipt':env.receipt_path,'base':env.base_file,
                'manifest':env.root/first['source_binding']['path']}[damage]
        target.write_bytes(target.read_bytes()+b' ')
    with pytest.raises(ValueError):env.load(first['source_binding'])


def test_future_acquisition_not_historical_publication(source_env):
    with pytest.raises(ValueError,match='NOT_YET_ACQUIRED'):
        source_env.load(now=NOW-timedelta(days=2))


def test_no_silent_truncation_or_mid_sentence_selection():
    selection=dict(period='2026-06-30',physical_page=1,start_marker='START',end_marker='END')
    for text in ('prefix START\n完整句。\nEND','START\n半句\nEND','START\n'+'字'*2000+'。\nEND'):
        with pytest.raises(ValueError):mod._excerpt(text,selection)
    with pytest.raises(ValueError):mod._excerpt('START\n完整句。\nSTART\nEND',selection)
    assert mod._excerpt('START\n完整句。\nEND',selection)[0]=='START\n完整句。\n'


def test_existing_parser_gap_remains_visible_no_fabricated_h1_scalar(source_env,monkeypatch):
    def gaps(*,root,source,evaluation_at):
        return dict(symbol='123456',source_binding=source,action='no_order',financial_quality_granted=False,
            evidence=[],gaps=[dict(reason='STATEMENT_PREPARER_NOT_EXACT_LEGAL_OWNER',physical_page=53)])
    monkeypatch.setattr(mod.statements,'load_operating_statement_basis',gaps)
    c=source_env.load()
    assert c['statement_basis_gaps'][0]['reason']=='STATEMENT_PREPARER_NOT_EXACT_LEGAL_OWNER'
    assert any(r['period_basis']=='H1' and r['unit']=='TEXT' for r in c['evidence'])
    assert not any(r['period_basis']=='H1' and 'value' in r for r in c['evidence'])


def test_context_limit_rejects_instead_of_cutting(source_env,monkeypatch):
    monkeypatch.setattr(mod,'MAX_CONTEXT_CHARS',100)
    with pytest.raises(ValueError,match='OVER_BUDGET'):source_env.load()
    assert not (source_env.root/'runtime'/mod.VERSION).exists()


def test_page_config_has_exact_requested_periods_and_pages():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    entry=json.loads((root/mod.CONFIG).read_bytes())['cases']['600323']
    actual={p:{e['physical_page'] for e in entry['excerpts'] if e['period']==p}
            for p in ('2025-12-31','2026-06-30')}
    assert actual=={'2025-12-31':{2,17,18,24,56,147,183},
                    '2026-06-30':{13,14,19,135,191,203}}
    assert '600323' not in Path(mod.__file__).read_text(encoding='utf-8')


def test_supplement_fact_selection_requires_explicit_unique_fields():
    base = dict(issuer_name='TEST_ONLY', parent_cash_layout='LEGACY_BLANK_SAFE_V3',
        parent_income_layout='UNNUMBERED_CONTINUATION_V2',
        parent_cash_observation_receipts=[dict(period='2026-06-30',
            receipt_binding=dict(path='runtime/receipt.json', sha256='a' * 64))], excerpts=[])
    for fields in ([], ['parent_cfo', 'parent_cfo'], ['ParentCfo'], ['parent_cfo'] * 31):
        with pytest.raises(ValueError, match='HORIZON_SUPPLEMENT_FACT_SELECTION_INVALID'):
            mod._selection(dict(base, supplement_fact_fields=fields))
    assert mod._selection(dict(base, supplement_fact_fields=['parent_cfo']))['supplement_fact_fields'] == ['parent_cfo']


def test_600887_real_official_pair_replays_as_unapproved_source_context():
    import os
    root_var = os.environ.get('VALUE_INVESTMENT_REAL_SOURCE_ROOT')
    if not root_var:
        pytest.skip('Explicit retained official originals required')
    root = Path(root_var).resolve()
    now = datetime.now(timezone.utc)
    context = mod.build_operating_horizon_source_context(root=root, symbol='600887', now=now)
    replay = mod.build_operating_horizon_source_context(
        root=root, symbol='600887', now=now, binding=context['source_binding'])
    assert replay == context
    assert context['financial_basis'] == '2026-06-30'
    assert {'2025-12-31', '2026-06-30'} <= {row['period'] for row in context['evidence']}
    assert {'revenue', 'parent_profit', 'parent_cfo'} <= {row['field'] for row in context['evidence'] if 'field' in row}
    assert context['formal_eligibility'] is False and context['action'] == 'no_order'
