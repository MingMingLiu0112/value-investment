from dataclasses import replace
import hashlib
import json
from datetime import date
from types import SimpleNamespace
import pytest
from test_product_workbench_read_model import _payload
from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload, EvidenceRecord
from value_investment_agent.presentation.read_models.dividend_history import project_dividend_history


def test_lifecycle_and_unknown_classification_do_not_create_yield_or_orders():
    model = product_workbench_from_payload(_payload())
    card = model.companies[0]
    record = dict(fiscal_period='FY2025-final', status='paid', dividend_per_share='0.90', currency='CNY',
        ex_date='2026-06-05', payment_date='2026-06-05', dividend_type='unknown',
        evidence_refs=[{'id': 'implementation'}], blockers=['classification unknown'])
    history = dict(schema_version='source-bound-dividend-history-v1', symbol=card.symbol,
        records=[record], sources=[dict(id='implementation', location='runtime/paid.pdf', sha256='b'*64)],
        package_as_of='2026-09-28', blockers=['sustainable dividend not established'], dividend_sustainability_admitted=False,
        current_yield_admitted=False, strict_pit_admitted=False, action='no_order')
    evidence = EvidenceRecord('dividend-fixture', 'Dividend', 'research', 'runtime/package.json', 'a'*64, model.as_of)
    output = project_dividend_history(model, history, evidence)
    updated = output.companies[0]
    assert replace(updated, decision_review=card.decision_review, evidence_refs=card.evidence_refs) == card
    assert output.portfolio == model.portfolio
    assert 'unknown' in str(updated.decision_review)
    assert '非个人到账证明' in str(updated.decision_review)
    history['current_yield_admitted'] = True
    with pytest.raises(ValueError): project_dividend_history(model, history, evidence)


def test_loader_binds_sources_and_discards_cached_yield(tmp_path, monkeypatch):
    from value_investment_agent.application.product import dividend_history as service
    original = tmp_path / 'source.pdf'
    original.write_bytes(b'original')
    package = {'sources': [dict(id='source', location='source.pdf', sha256=hashlib.sha256(original.read_bytes()).hexdigest())]}
    path = tmp_path / 'package.json'
    path.write_text(json.dumps(package), encoding='utf-8')
    value = dict(as_of='2026-09-28', history=dict(status='PARTIAL', records=[dict(known_at='2026-09-28',
        evidence_refs=[{'id': 'source'}])]), blockers=['partial'], yield_snapshots=[{'dividend_yield': '999'}])
    monkeypatch.setattr(service, 'build_dividend_result', lambda *a, **k:
        SimpleNamespace(symbol='600887', as_of=date(2026, 9, 28), to_json=lambda: json.dumps(value)))
    args = dict(root=tmp_path, path=path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), symbol='600887')
    output = service.read_dividend_history(**args)
    assert 'yield_snapshots' not in output
    assert not output['current_yield_admitted']
    original.write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed'): service.read_dividend_history(**args)
