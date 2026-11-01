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
