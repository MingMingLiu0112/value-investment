"""TEST_ONLY owned journal binding plus held action/risk join; not real admission."""
from copy import deepcopy

import pytest

from test_personal_entry_thesis import case, AS_OF, narrative_request, thesis_service
from value_investment_agent.application.portfolio.personal_entry_thesis import owned_entry_context
from value_investment_agent.application.portfolio.held_continuity import owned_held_action, SELL_REVIEW_SCHEMA


def confirmed_context(case, tmp_path):
    args, service, _ = case
    payload = narrative_request(args)
    del payload['reconstruction']
    payload.update(binding_mode='CONTEMPORANEOUS', entry_artifact_id=args['entry_artifact'].artifact_id,
                   consistency_artifact_id=args['consistency_artifact'].artifact_id)
    thesis_service(args, service).confirm(payload, repository_root=tmp_path,
        authenticated_subject='LOCAL_OPERATOR', now=AS_OF)
    return owned_entry_context(records=service.records(), symbol='300364', sleeve='CORE_VALUE',
        authenticated_subject='LOCAL_OPERATOR', as_of=AS_OF)


def inputs(context, selected):
    risk = {'blockers': [], 'engine': {'namespace': 'ACTUAL', 'status': 'RISK_REVIEW_CALCULATED',
        'blockers': [], 'core_quantity_review': {'review_quantity': 100, 'blockers': []}},
        'policy': {'confirmation_status': 'HUMAN_CONFIRMED'}, 'facts': {'reconciliation_status': 'RECONCILED',
        'reconciliation': {'scope': 'EXTERNAL_ACCOUNT_STATEMENT'},
        'revision': context['journal_revision'], 'account_scope': context['account_scope'],
        'positions': [{'symbol': '300364', 'exchange': 'SZSE'}]}}
    plan = {'action': 'no_order', 'symbol': '300364', 'strategy': 'CORE_VALUE', 'blockers': [],
        'schema_version': 'value-action-plan-v1',
        'action_intent': 'ADD', 'add_condition': {'triggered': True},
        'reduce_condition': {'review_quantity': 100}, 'exit_condition': {'review_quantity': 100}}
    result = dict(context=context, plan=plan, risk=risk,
        sleeve_position={'sleeve': 'CORE_VALUE', 'quantity': '100', 'sellable_quantity': '100'},
        advisory_provider=lambda: (selected, [], {'namespace': 'TEST_ONLY_KERNEL_JOIN_NOT_REAL_ADMISSION'}))
    risk['engine']['sleeves'] = {'CORE_VALUE': {'holdings': [dict(symbol='300364',
        quantity='100', sellable_quantity='100')]}}
    if selected in {'TRIM_CANDIDATE', 'SELL_CANDIDATE'}:
        result['sell_review_request'] = dict(schema_version=SELL_REVIEW_SCHEMA, action='no_order',
            expected_revision=context['journal_revision'], account_scope=context['account_scope'],
            symbol='300364', exchange='SZSE', sleeve='CORE_VALUE',
            requested_action='REDUCE' if selected == 'TRIM_CANDIDATE' else 'EXIT',
            requested_quantity=50 if selected == 'TRIM_CANDIDATE' else 100,
            entry_thesis_record_sha256=context['entry_thesis_record_sha256'], read_and_confirmed=True)
    return result


@pytest.mark.parametrize('selected,action,quantity', [('HOLD', 'HOLD', None),
    ('ADD_CANDIDATE', 'ADD', 100), ('TRIM_CANDIDATE', 'REDUCE', 50), ('SELL_CANDIDATE', 'EXIT', 100)])
def test_journal_owned_binding_joins_four_held_actions_without_journal_writes(case, tmp_path, selected, action, quantity):
    context = confirmed_context(case, tmp_path)
    before = case[1].journal.path.read_bytes()
    result = owned_held_action(**inputs(context, selected))
    assert result['decision_action'] == action, result['blockers']
    assert result['review_quantity'] == quantity
    assert result['ownership_verified'] is True
    assert result['original_thesis'] == context['entry_thesis'].thesis
    assert result['broker_execution_permission'] is False
    assert result['action'] == 'no_order'
    assert case[1].journal.path.read_bytes() == before


@pytest.mark.parametrize('fault', ['t_plus_one', 'ips', 'reconciliation', 'thesis', 'sizing', 'no_add_condition'])
def test_known_ownership_cannot_waive_risk_or_execution(case, tmp_path, fault):
    context = confirmed_context(case, tmp_path)
    args = inputs(context, 'SELL_CANDIDATE' if fault == 't_plus_one' else 'ADD_CANDIDATE')
    if fault == 't_plus_one': args['sleeve_position']['sellable_quantity'] = '0'
    elif fault == 'ips': args['risk']['policy']['confirmation_status'] = 'DRAFT'
    elif fault == 'reconciliation': args['risk']['facts']['reconciliation']['scope'] = 'INTERNAL_JOURNAL_REPLAY'
    elif fault == 'thesis': args['context']['advisory_dependencies_valid'] = False
    elif fault == 'sizing': args['risk']['engine']['core_quantity_review']['review_quantity'] = 0
    else: args['plan']['add_condition']['triggered'] = False
    result = owned_held_action(**args)
    assert result['decision_action'] == 'UNASSESSABLE'
    assert result['review_quantity'] is None
    assert result['formal_eligibility'] is False


def test_narrative_reconstruction_stays_ineligible_after_durable_confirmation(case, tmp_path):
    args, service, _ = case
    thesis_service(args, service).confirm(narrative_request(args), repository_root=tmp_path,
        authenticated_subject='LOCAL_OPERATOR', now=AS_OF)
    context = owned_entry_context(records=service.records(), symbol='300364', sleeve='CORE_VALUE',
        authenticated_subject='LOCAL_OPERATOR', as_of=AS_OF)
    result = owned_held_action(**inputs(context, 'HOLD'))
    assert context['ownership_verified'] is True
    assert context['advisory_dependencies_valid'] is False
    assert result['decision_action'] == 'UNASSESSABLE'
    assert 'HISTORICAL_RECONSTRUCTION_NOT_ORIGINAL_PIT_ENTRY' in result['blockers']


def test_current_consistency_display_does_not_reuse_original_confirmation(case, tmp_path):
    context = confirmed_context(case, tmp_path)
    args = inputs(context, 'SELL_CANDIDATE')
    args['advisory_provider'] = lambda: ('SELL_CANDIDATE', [], {
        'namespace': 'TEST_ONLY_KERNEL_JOIN_NOT_REAL_ADMISSION',
        'current_consistency_status': 'BROKEN',
    })
    result = owned_held_action(**args)
    assert result['entry_consistency_status'] == context['investment_consistency_review'].status
    assert result['consistency_status'] == 'BROKEN'
    assert result['original_thesis'] == context['entry_thesis'].thesis


def test_missing_current_consistency_does_not_display_original_as_current(case, tmp_path):
    context = confirmed_context(case, tmp_path)
    result = owned_held_action(**inputs(context, 'HOLD'))
    assert result['entry_consistency_status'] == context['investment_consistency_review'].status
    assert result['consistency_status'] is None


@pytest.mark.parametrize('fault', ['missing_request', 'revision', 'account', 'hash', 'sleeve',
    'over_sellable', 'partial_exit', 'full_reduce', 'unknown_advisory', 'stale_plan', 'risk_revision'])
def test_explicit_sell_review_cannot_waive_identity_or_quantity(case, tmp_path, fault):
    context = confirmed_context(case, tmp_path)
    args = inputs(context, 'TRIM_CANDIDATE' if fault == 'full_reduce' else 'SELL_CANDIDATE')
    request = args['sell_review_request']
    if fault == 'missing_request': args['sell_review_request'] = None
    elif fault == 'revision': request['expected_revision'] += 1
    elif fault == 'account': request['account_scope'] = 'TEST_ONLY-other-account'
    elif fault == 'hash': request['entry_thesis_record_sha256'] = '0' * 64
    elif fault == 'sleeve': request['sleeve'] = 'HOTSPOT_SATELLITE'
    elif fault == 'over_sellable': request['requested_quantity'] = 101
    elif fault == 'partial_exit': request['requested_quantity'] = 50
    elif fault == 'full_reduce': request['requested_quantity'] = 100
    elif fault == 'unknown_advisory': args['advisory_provider'] = lambda: ('UNKNOWN', [], {})
    elif fault == 'stale_plan': args['plan']['signal_state'] = 'STALE'
    else: args['risk']['facts']['revision'] += 1
    before = case[1].journal.path.read_bytes()
    result = owned_held_action(**args)
    assert result['decision_action'] == 'UNASSESSABLE'
    assert result['review_quantity'] is None and result['formal_eligibility'] is False
    assert case[1].journal.path.read_bytes() == before
