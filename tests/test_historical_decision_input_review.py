import pytest
from value_investment_agent.application.historical_validation.decision_input_review import review_historical_decision_inputs, render_decision_input_review


def inputs():
    common = dict(symbol='600887', action='no_order', strict_pit_admitted=False)
    cutoff = '2026-09-22T15:00:00+08:00'
    return (dict(**common, schema_version='reconstructed-equity-input-v1', workbench_sha256='a'*64, cutoffs=[dict(
        cutoff=cutoff, eligible_facts=[{'fact_name': 'parent_equity'}], missing_facts=[])]),
        dict(**common, schema_version='historical-price-bridge-replay-v1', valuation_reference_sha256='a'*64, rows=[dict(
            cutoff=cutoff, quote_observed=False, valuation_observed=False, bridge=None, blockers=[])]))


def test_public_facts_do_not_admit_unobserved_decisions_or_execution():
    reconstruction, history = inputs()
    output = review_historical_decision_inputs(reconstruction, history)
    row = output['rows'][0]
    assert row['publicly_available_basis_facts'] == ['parent_equity']
    assert row['orders'] == row['fills'] == []
    assert '截止后才抓取' in render_decision_input_review(output)
    history['rows'][0].update(quote_observed=True, valuation_observed=True, bridge={'bridge_status': 'READY'})
    output = review_historical_decision_inputs(reconstruction, history)
    assert output['rows'][0]['decision_input_status'] == 'NOT_READY'
    assert not output['historical_execution_validated']


@pytest.mark.parametrize('change', ['symbol', 'cutoff', 'admission', 'workbench'])
def test_incompatible_input_contracts_fail_closed(change):
    reconstruction, history = inputs()
    if change == 'symbol': history['symbol'] = '000333'
    if change == 'cutoff': history['rows'][0]['cutoff'] = '2026-09-23T15:00:00+08:00'
    if change == 'admission': reconstruction['strict_pit_admitted'] = True
    if change == 'workbench': reconstruction['workbench_sha256'] = 'b'*64
    with pytest.raises(ValueError): review_historical_decision_inputs(reconstruction, history)


def test_evidence_timeline_distinguishes_publication_from_later_review():
    reconstruction, history = inputs()
    fact = dict(fact_name='parent_equity', value='100', unit='CNY', period='2026-06-30',
        source_id='official:1', source_file_hash='c'*64, physical_page=6,
        original_review_available_at='2026-10-01T00:00:00+08:00',
        reconstructed_availability=dict(available_from='2026-08-28T00:00:00+08:00',
            basis='next_day_conservative', timestamp_precision='DATE_ONLY'),
        source_excerpt_semantics_verified=False)
    reconstruction['facts'] = [fact]
    reconstruction['cutoffs'][0]['eligible_facts'] = [fact.copy()]
    output = review_historical_decision_inputs(reconstruction, history)
    row = output['rows'][0]['fact_evidence_timeline'][0]
    assert row['publicly_available_at_cutoff'] is True
    assert row['review_observed_at_cutoff'] is False
    assert row['semantic_status'] == 'NOT_VERIFIED'
    assert '原件物理页 6' in render_decision_input_review(output)
    row['value'] = '999'
    assert fact['value'] == '100'
    reconstruction['facts'][0]['reconstructed_availability']['available_from'] = '2026-09-23T00:00:00+08:00'
    with pytest.raises(ValueError, match='cutoff availability'):
        review_historical_decision_inputs(reconstruction, history)
