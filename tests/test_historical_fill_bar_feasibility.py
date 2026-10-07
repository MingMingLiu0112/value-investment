"""Frozen day bars constrain a fill, but do not prove actual execution."""
import json

import pytest

from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.historical_validation.ohlc_fill_feasibility import audit_frozen_fill_bars
from value_investment_agent.presentation.read_models.historical_execution_replay import render_historical_fill_feasibility


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding='utf-8')
    return sha256_file(path)


def _fixture(tmp_path, second_high='12', fill_price='10'):
    paths = [tmp_path / 'a.json', tmp_path / 'b.json']
    rows = [['2025-01-02', '10', '11', high, '9', '100'] for high in ('12', second_high)]
    hashes = [_write(path, {'code': 0, 'data': {'sh600519': {'day': [row]}}})
              for path, row in zip(paths, rows)]
    sources = [dict(path=path.name, sha256=digest, row_index=0)
               for path, digest in zip(paths, hashes)]
    journal = tmp_path / 'journal.json'
    fill = dict(filled_on='2025-01-02', price=fill_price, side='buy', quantity=100)
    _write(journal, [dict(date='2025-01-02', open='10', close='11', fill=fill)])
    result = tmp_path / 'result.json'
    _write(result, dict(schema_version='historical-execution-replay-v1', action='no_order',
        symbol='600519', scenario='test-only', historical_execution_validated=False,
        performance_claim_allowed=False, mechanical_reproduction_verified=True,
        comparison={'frozen_journal': {'status': 'MATCH', 'rows_compared': 1, 'fills_compared': 1},
                    'range_result': {'status': 'MATCH'}},
        summary={'fills': 1}, execution_events=[{'date': '2025-01-02', 'fill': fill}],
        price_source_correspondence=dict(schema_version='historical-price-correspondence-v1',
            status='MATCH', action='no_order', validated_fields=['open', 'close'],
            rows=[dict(date='2025-01-02', open='10', close='11', sources=sources)]),
        source_bindings=[dict(role=f'execution_original_{index:03d}', path=path.name,
                              sha256=digest) for index, (path, digest) in enumerate(zip(paths, hashes))]))
    return result, journal, paths


def _audit(root, result, journal):
    return audit_frozen_fill_bars(root=root, result_path=result,
        result_sha256=sha256_file(result), journal_path=journal,
        journal_sha256=sha256_file(journal))


def test_frozen_fill_bar_audit_is_readable_but_not_execution_admission(tmp_path):
    result, journal, _ = _fixture(tmp_path)
    audit = _audit(tmp_path, result, journal)
    assert audit['checked_fills'] == 1
    assert len(audit['checks'][0]['originals']) == 2
    assert audit['execution_admitted'] is False
    assert audit['strict_pit_admitted'] is False
    assert audit['performance_claim_allowed'] is False
    report = render_historical_fill_feasibility(audit)
    assert '2 份封存原件一致' in report
    assert '真实可成交' in report and 'action=no_order' in report


def test_conflict_tamper_and_outside_range_fail_closed(tmp_path):
    result, journal, paths = _fixture(tmp_path, second_high='13')
    with pytest.raises(ValueError, match='conflicting overlapping'):
        _audit(tmp_path, result, journal)
    paths[1].write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='hash mismatch'):
        _audit(tmp_path, result, journal)
    result, journal, _ = _fixture(tmp_path, fill_price='15')
    with pytest.raises(ValueError, match='inconsistent'):
        _audit(tmp_path, result, journal)
    payload = json.loads(result.read_text(encoding='utf-8'))
    payload['historical_execution_validated'] = True
    _write(result, payload)
    with pytest.raises(ValueError, match='scope mismatch'):
        _audit(tmp_path, result, journal)


def test_other_journal_with_plausible_price_is_rejected(tmp_path):
    result, journal, _ = _fixture(tmp_path)
    altered = json.loads(journal.read_text(encoding='utf-8'))
    altered[0]['fill']['price'] = '10.50'
    _write(journal, altered)
    with pytest.raises(ValueError, match='does not match frozen replay result'):
        _audit(tmp_path, result, journal)
    result, journal, _ = _fixture(tmp_path)
    payload = json.loads(result.read_text(encoding='utf-8'))
    payload['comparison']['frozen_journal']['status'] = 'NOT_MATCHED'
    _write(result, payload)
    with pytest.raises(ValueError, match='comparison not established'):
        _audit(tmp_path, result, journal)
