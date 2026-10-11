import copy
import json

import pytest

from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.presentation.research_supplement_surface import project_research_supplements


def fixture(root):
    source = root / 'source.md'
    source.write_text('original financial evidence', encoding='utf-8')
    path = root / 'runtime/proposal.json'
    path.parent.mkdir()
    data = dict(schema_version='finite-neutral-valuation-proposal-v1', symbol='600519',
        action='no_order', status='NEUTRAL_VALUATION_PROPOSAL_PENDING_REVIEW',
        generated_at='2026-10-11T03:00:00+00:00', original_research_as_of='2026-10-08',
        original_valuation_date='2026-10-08', position_guidance=None,
        source_bindings=[dict(path='source.md', sha256=sha256_file(source))],
        choices=[dict(id='B', valuation=dict(symbol='600519', bear_value='400', base_value='500', bull_value='600'))])
    for key in ('assumptions_approved', 'g3_approved', 'model_validity_approved', 'price_admitted',
                'research_date_advanced', 'decision_changed', 'canonical_written'):
        data[key] = False
    path.write_text(json.dumps(data), encoding='utf-8')
    payload = dict(as_of='2026-10-08', companies=[dict(symbol='600519', evidence_refs=[],
        valuation=dict(status='NOT_READY'), decision_status='NO_ACTION', sections=[])], audit=dict(evidence=[]))
    binding = dict(role='valuation_proposal', path='runtime/proposal.json', sha256=sha256_file(path))
    return source, path, data, payload, binding


def test_supplement_is_visible_without_changing_admission(tmp_path):
    _, _, _, payload, binding = fixture(tmp_path)
    before = copy.deepcopy(payload['companies'][0])
    assert project_research_supplements(payload, root=tmp_path, symbol='600519', bindings=[binding]) == [binding]
    company = payload['companies'][0]
    assert company['valuation'] == before['valuation']
    assert company['decision_status'] == 'NO_ACTION'
    assert payload['as_of'] == '2026-10-08'
    assert '尚非批准合理价或买点' in company['decision_review'][0]['value']
    assert payload['audit']['evidence'][0]['sha256'] == binding['sha256']


@pytest.mark.parametrize('change', ['source', 'output', 'symbol', 'approval', 'nonfinite', 'escape'])
def test_supplement_rejects_drift_and_scope_escalation(tmp_path, change):
    source, path, data, payload, binding = fixture(tmp_path)
    if change == 'source':
        source.write_text('changed', encoding='utf-8')
    elif change == 'output':
        path.write_text('{}', encoding='utf-8')
    elif change == 'escape':
        binding['path'] = '../outside.json'
    else:
        if change == 'symbol':
            data['symbol'] = '600887'
        elif change == 'approval':
            data['g3_approved'] = True
        else:
            data['choices'][0]['valuation']['base_value'] = 'NaN'
        path.write_text(json.dumps(data), encoding='utf-8')
        binding['sha256'] = sha256_file(path)
    with pytest.raises(ValueError):
        project_research_supplements(payload, root=tmp_path, symbol='600519', bindings=[binding])
