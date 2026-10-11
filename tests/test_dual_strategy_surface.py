from copy import deepcopy

import pytest

from value_investment_agent.presentation.dual_strategy_surface import (
    hotspot_surfaces, selected_candidate, validate_extensions,
)


def test_extension_requires_publication_binding_and_no_order():
    payload = {'schema_version': 'dual-product-surface-v1', 'action': 'no_order',
               'input_sha256': 'a' * 64, 'source_bindings': [{'path': 'runtime/report.json', 'sha256': 'b' * 64}]}
    validate_extensions(payload, 'a' * 64)
    with pytest.raises(ValueError):
        validate_extensions(payload, 'c' * 64)
    payload['hotspot_report'] = {'action': 'order'}
    with pytest.raises(ValueError):
        validate_extensions(payload, 'a' * 64)


def test_hotspot_does_not_promote_observation_or_mutate_input():
    report = {'action': 'no_order', 'opportunities': [{'symbol': 'TEST', 'state': 'HOT_WATCH'}]}
    before = deepcopy(report)
    row = hotspot_surfaces(report)[0]
    assert row.candidate_action == 'HOT_WATCH'
    assert row.quote_date == 'UNKNOWN'
    assert row.action == 'no_order'
    assert report == before


@pytest.mark.parametrize('value', [False, 'true', None])
def test_entry_review_fails_closed_on_unqualified_gate(value):
    gates = dict.fromkeys(('core_value', 'risk', 'pit', 'oos', 'cost', 'shadow'), True)
    gates['shadow'] = value
    with pytest.raises(ValueError):
        hotspot_surfaces({'action': 'no_order', 'opportunities': [
            {'symbol': 'TEST', 'state': 'ENTRY_REVIEW_CANDIDATE', 'gates': gates}]})


def test_current_candidate_requires_unambiguous_upstream_selection():
    candidate = {'symbol': 'TEST', 'action': 'no_order', 'model_context_scope': 'ACTUALLY_CONSUMED',
                 'candidate_valuation': {'status': 'conditional_research_only', 'base_value': '123.45'}}
    with pytest.raises(ValueError):
        selected_candidate([candidate, deepcopy(candidate)], 'TEST')
    newer = dict(candidate, is_current=True, selected_choice='selected-v5')
    assert selected_candidate([candidate, newer], 'TEST') is newer
