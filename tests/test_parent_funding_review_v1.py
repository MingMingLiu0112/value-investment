from decimal import Decimal
import pytest
from value_investment_agent.domain.research.parent_distribution_capacity_v1 import assess_capacity


def run(**changes):
    args = dict(opening_cash='23517778984.18', dividend_payable='6501567650.57',
                retained_profit='23214184665.64', obligations=[])
    args.update(changes)
    return assess_capacity(**args)


def test_historical_and_conditional_budget():
    assert run()['static_after_declared_dividend'] == '17016211333.61'
    result = run(cash_floor='6000000000', additional_distribution='8500000000',
                 obligations_complete=True)
    assert Decimal(result['conditional_shortfall']) == 0
    assert result['current_capacity_proven'] is False
    assert run()['status'] == 'INCOMPLETE_OBLIGATIONS'
    assert run()['conditional_distribution_ceiling'] is None
    assert run()['conditional_shortfall'] is None


def test_paid_dividend_not_deducted_again():
    assert run(opening_cash='17016211333.61', dividend_already_deducted=True)['static_after_declared_dividend'] == '17016211333.61'


@pytest.mark.parametrize('value', [-1, 'NaN', 'Infinity', True])
def test_invalid_cash(value):
    with pytest.raises(ValueError):
        run(opening_cash=value)


def test_scope_and_duplicate():
    for obligations in ([dict(id='x', amount=1, scope='consolidated')],
                        [dict(id='declared_dividend', amount=1, scope='parent')],
                        [dict(id='x', amount=1, scope='parent')]*2):
        with pytest.raises(ValueError):
            run(obligations=obligations)


def test_source_tampering_and_future(tmp_path, monkeypatch):
    import hashlib
    import json
    from datetime import datetime, timezone
    from value_investment_agent.infrastructure.filings.parent_funding_facts_v1 import load_parent_facts
    pdf = tmp_path / 'original.pdf'
    pdf.write_bytes(b'original')
    packet = dict(sources=[dict(id='s', path='original.pdf',
                  sha256=hashlib.sha256(b'original').hexdigest(),
                  available_at='2026-11-01T00:00:00+00:00')], facts=[])
    path = tmp_path / 'facts.json'
    path.write_text(json.dumps(packet), encoding='utf-8')
    monkeypatch.setattr('value_investment_agent.infrastructure.filings.parent_funding_facts_v1.REVIEWED_NATIVE_SHA256', hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match='future source'):
        load_parent_facts(tmp_path, 'facts.json', cutoff=datetime(2026, 10, 31, tzinfo=timezone.utc))
    pdf.write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        load_parent_facts(tmp_path, 'facts.json', cutoff=datetime(2026, 11, 2, tzinfo=timezone.utc))


def test_floor_overlap_not_reserved_twice():
    result = run(cash_floor=100, obligations=[dict(id='reserve', scope='parent',
                  amount=100, included_in_cash_floor=True)])
    assert Decimal(result['conditional_cash_remaining']) == Decimal('17016211233.61')


@pytest.mark.parametrize('key', ['generated_at', 'identity_available_at', 'published_at'])
def test_later_packet_identity_publication(tmp_path, key, monkeypatch):
    import json
    import hashlib
    from datetime import datetime, timezone
    from value_investment_agent.infrastructure.filings.parent_funding_facts_v1 import load_parent_facts
    (tmp_path / 'original.pdf').write_bytes(b'original')
    source = dict(id='s', path='original.pdf', available_at='2026-10-01T00:00:00+00:00',
                  sha256=hashlib.sha256(b'original').hexdigest())
    packet = dict(sources=[source], facts=[])
    (packet if key == 'generated_at' else source)[key] = '2026-11-03T00:00:00+00:00'
    (tmp_path / 'facts.json').write_text(json.dumps(packet), encoding='utf-8')
    monkeypatch.setattr('value_investment_agent.infrastructure.filings.parent_funding_facts_v1.REVIEWED_NATIVE_SHA256', hashlib.sha256((tmp_path / 'facts.json').read_bytes()).hexdigest())
    with pytest.raises(ValueError, match='future'):
        load_parent_facts(tmp_path, 'facts.json', cutoff=datetime(2026, 11, 2, tzinfo=timezone.utc))


@pytest.mark.parametrize('changes', [dict(obligations_complete='false'),
    dict(dividend_already_deducted='false'), dict(opening_cash=1.5),
    dict(opening_cash=None), dict(obligations=[dict(id='x', scope='parent',
    amount=1, included_in_cash_floor='false')])])
def test_strict_input_types(changes):
    with pytest.raises(ValueError):
        run(**changes)


def test_negative_retained_profit():
    result = run(retained_profit='-1', obligations_complete=True)
    assert result['status'] == 'NOT_ASSESSABLE'
    assert result['conditional_distribution_ceiling'] is None


def test_overlap_and_renamed_dividend():
    for item in [dict(id='x', scope='parent', amount=1, included_in_cash_floor=True),
                 dict(id='renamed', scope='parent', amount=1, kind='declared_dividend'),
                 dict(id='renamed', scope='parent', amount=1, economic_id='declared_dividend')]:
        with pytest.raises(ValueError):
            run(obligations=[item])


def test_unreviewed_native_rejected(tmp_path):
    from datetime import datetime, timezone
    from value_investment_agent.infrastructure.filings.parent_funding_facts_v1 import load_parent_facts
    (tmp_path / 'facts.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='unreviewed native'):
        load_parent_facts(tmp_path, 'facts.json', cutoff=datetime.now(timezone.utc))


@pytest.fixture
def registered_parent(tmp_path, monkeypatch):
    import hashlib
    import json
    from datetime import datetime, timezone
    from value_investment_agent.application.research import parent_funding_review_v1 as app
    def bind(name, value):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')
        return dict(path=name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    native = bind('native.json', dict(symbol='000568'))
    receipt = bind('receipt.json', dict(records=[]))
    spec = dict(schema_version='parent-funding-followup-v1', symbol='000568',
        scope='HISTORICAL_PARENT_CASH_REVIEW_NOT_CURRENT_CAPACITY', action='no_order',
        native_facts=native, source_receipt=receipt, generated_at='2026-11-01T00:00:00+00:00')
    registry_name = 'config/current-operating-research-sources-v1.json'
    def register():
        pin = bind('spec.json', spec)
        bind(registry_name, dict(schema_version='current-operating-research-sources-v1', action='no_order',
            cases={'000568': dict(native_facts=native, parent_funding_followup=pin)}))
    register()
    calls = []
    def review(root, native_path, receipt_path, *, cutoff):
        calls.append((root, native_path, receipt_path, cutoff))
        return dict(TEST_ONLY=True, unknown='UNKNOWN', current_capacity_proven=False, action='no_order')
    monkeypatch.setattr(app, 'review_post_h1', review)
    return dict(root=tmp_path, app=app, spec=spec, register=register, bind=bind, calls=calls,
                now=datetime(2026, 11, 2, tzinfo=timezone.utc), registry=tmp_path/registry_name)


def test_registered_public_read_without_account_data(registered_parent, monkeypatch):
    from pathlib import Path
    import socket
    e = registered_parent
    before = {str(p): p.read_bytes() for p in e['root'].rglob('*') if p.is_file()}
    def forbidden(*args, **kwargs): pytest.fail('Public read must not write or use network')
    monkeypatch.setattr(Path, 'write_bytes', forbidden)
    monkeypatch.setattr(Path, 'write_text', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    result = e['app'].read_registered_parent_funding_review(root=e['root'], symbol='000568', now=e['now'])
    assert result['status'] == 'HISTORICAL_PARENT_REVIEW'
    assert result['review']['TEST_ONLY'] and result['review']['unknown'] == 'UNKNOWN'
    assert not result['formal_eligibility'] and not result['current_capacity_proven']
    assert result['source_receipt'] == e['spec']['source_receipt']
    assert len(result['implementation_sha256']) == 3 and len(e['calls']) == 1
    assert {str(p): p.read_bytes() for p in e['root'].rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('damage', ['spec_hash', 'native_hash', 'receipt_hash', 'future', 'naive',
    'symbol', 'native_symbol', 'native_binding', 'scope', 'extra', 'traversal', 'registry'])
def test_registered_parent_fail_closed_no_fallback(registered_parent, damage):
    e = registered_parent
    spec = e['spec']
    if damage in {'spec_hash', 'native_hash', 'receipt_hash'}:
        name = {'spec_hash': 'spec.json', 'native_hash': 'native.json', 'receipt_hash': 'receipt.json'}[damage]
        path = e['root']/name
        path.write_bytes(path.read_bytes()+b' ')
    elif damage == 'registry': e['registry'].write_text('{', encoding='utf-8')
    else:
        if damage == 'future': spec['generated_at'] = '2027-01-01T00:00:00+00:00'
        elif damage == 'naive': spec['generated_at'] = '2026-11-01T00:00:00'
        elif damage == 'symbol': spec['symbol'] = '600519'
        elif damage == 'native_symbol':
            pin = e['bind']('native.json', dict(symbol='600519'))
            spec['native_facts'].update(pin)
        elif damage == 'native_binding': spec['native_facts'] = e['bind']('other.json', dict(symbol='000568'))
        elif damage == 'scope': spec['scope'] = 'CURRENT_CAPACITY'
        elif damage == 'extra': spec['approved'] = True
        else: spec['source_receipt'] = dict(path='../receipt.json', sha256='a'*64)
        e['register']()
    result = e['app'].read_registered_parent_funding_review(root=e['root'], symbol='000568', now=e['now'])
    assert result['status'] == 'UNASSESSABLE' and result['review'] is None
    assert result['reason'] and not e['calls']


@pytest.mark.parametrize('target', ['spec.json', 'native.json', 'receipt.json', 'registry'])
def test_registered_parent_rechecks_bindings_after_review(registered_parent, monkeypatch, target):
    e = registered_parent
    def changed(*args, **kwargs):
        path = e['registry'] if target == 'registry' else e['root']/target
        path.write_bytes(path.read_bytes()+b' ')
        return dict(TEST_ONLY=True)
    monkeypatch.setattr(e['app'], 'review_post_h1', changed)
    result = e['app'].read_registered_parent_funding_review(root=e['root'], symbol='000568', now=e['now'])
    assert result['status'] == 'UNASSESSABLE' and result['review'] is None


def test_parent_missing_registration_not_started(registered_parent):
    e = registered_parent
    assert e['app'].read_registered_parent_funding_review(root=e['root'], symbol='600519', now=e['now'])['status'] == 'NOT_STARTED'
    e['registry'].unlink()
    assert e['app'].read_registered_parent_funding_review(root=e['root'], symbol='000568', now=e['now'])['status'] == 'NOT_STARTED'
    assert e['calls'] == []


def test_real_registered_parent_funding_public_read(monkeypatch):
    import os
    import json
    import hashlib
    import socket
    from pathlib import Path
    from datetime import datetime, timezone
    from value_investment_agent.application.research import parent_funding_review_v1 as app
    location = os.environ.get('PARENT_FUNDING_REAL_ROOT')
    if not location:
        if os.environ.get('PARENT_FUNDING_REAL_REQUIRED') == '1': pytest.fail('PARENT_FUNDING_REAL_ROOT required')
        pytest.skip('Retained public originals require explicit opt-in root')
    root = Path(location).resolve()
    registry = root/'config/current-operating-research-sources-v1.json'
    entry = json.loads(registry.read_bytes())['cases']['000568']
    spec_path = root/entry['parent_funding_followup']['path']
    spec = json.loads(spec_path.read_bytes())
    native = json.loads((root/spec['native_facts']['path']).read_bytes())
    receipt = json.loads((root/spec['source_receipt']['path']).read_bytes())
    paths = [registry, spec_path, root/spec['native_facts']['path'], root/spec['source_receipt']['path']]
    paths += [root/source['path'] for source in native['sources']]
    paths += [root/r['path'] for r in receipt['records'] if r.get('source_id') == 'cninfo:1225481717']
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    def forbidden(*args, **kwargs): pytest.fail('Real parent review is read-only/offline')
    monkeypatch.setattr(Path, 'write_bytes', forbidden)
    monkeypatch.setattr(Path, 'write_text', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    result = app.read_registered_parent_funding_review(root=root, symbol='000568', now=datetime.now(timezone.utc))
    assert result['status'] == 'HISTORICAL_PARENT_REVIEW', result
    assert result['review']['result']['static_after_declared_dividend'] == '17016211333.61'
    assert result['review']['future_necessary_investment'] == 'UNKNOWN'
    assert result['review']['post_h1_bridge']
    assert result['action'] == 'no_order' and result['current_capacity_proven'] is False
    assert {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths} == before


def test_historical_parent_amount_can_check_consumed_cash_input_without_approval():
    from value_investment_agent.application.research.parent_funding_review_v1 import compare_parent_cash_opening
    parent=dict(status="HISTORICAL_PARENT_REVIEW",symbol="000568",native_facts=dict(path="TEST_ONLY",sha256="a"*64),source_spec=dict(path="TEST_ONLY",sha256="b"*64),review=dict(period="2026-06-30",
        result=dict(static_after_declared_dividend="17016211333.61")))
    from value_investment_agent.domain.valuation.joint_capital_cash_path_v4 import SCOPE
    cash=dict(symbol="000568",source_binding=parent["native_facts"],annual_followup=dict(status="CONDITIONAL_STRESS_CONSUMED",
        opening_state=dict(as_of="2026-06-30",currency="CNY",cash_cny="17016211333.61",scope=SCOPE),
        input_descriptor_sha256="c"*64))
    result=compare_parent_cash_opening(parent,cash)
    assert result["status"]=="AMOUNT_EQUAL_NOT_MAPPING_VERIFIED"
    assert result["current_capacity_proven"] is False and result["action"]=="no_order"
    assert result["source_mapping_verified"] is False
    cash["annual_followup"]["opening_state"]["scope"]="consolidated"
    assert compare_parent_cash_opening(parent,cash)["status"]=="NOT_ASSESSABLE"
    cash["annual_followup"]["opening_state"]["scope"]=SCOPE
    cash["annual_followup"]["opening_state"]["cash_cny"]="17016211334.61"
    assert compare_parent_cash_opening(parent,cash)["status"]=="AMOUNT_DIFFERENT"
    cash["annual_followup"]["opening_state"]["as_of"]="2026-09-30"
    assert compare_parent_cash_opening(parent,cash)["status"]=="NOT_ASSESSABLE"


@pytest.mark.parametrize("cash", [None,{},{"annual_followup":None},{"annual_followup":{"opening_state":None}}])
def test_cash_comparison_null_structures_do_not_break_public_api(cash):
    from value_investment_agent.application.research.parent_funding_review_v1 import compare_parent_cash_opening
    parent=dict(status="HISTORICAL_PARENT_REVIEW",review=dict(period="2026-06-30"))
    assert compare_parent_cash_opening(parent,cash)["status"]=="NOT_ASSESSABLE"
