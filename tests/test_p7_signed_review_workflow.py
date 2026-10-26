"""TEST_ONLY signed review integration; no real identity or publication writes."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from test_pending_review_response import signed, consume, whole_approval
from test_d2_conditional_shared_service import synthetic_chain
from test_p62_positive_workflow import _simulated_review
from test_private_ips_policy import full_policy
from value_investment_agent.application.product.common import sha256_file, write_new_json
from value_investment_agent.application.product.company_research import run_company_research_for_symbol
from value_investment_agent.application.product.research_publication_input import (
    prepare_research_publication_input, load_research_publication_input,
)
from value_investment_agent.operations.authorization.trust_root_registry import _use_test_trust_registry
from value_investment_agent.application.product.research_reviews import (
    prepare_pending_review_response, build_research_review_model_context,
    verify_human_approval_transport_provenance,
)
from value_investment_agent.application.product.workbench import build_current_workbench_for_symbol
from value_investment_agent.application.product.decision_surface import verify_current_decision_workbench
from value_investment_agent.research_input import build_research_run_spec
from value_investment_agent.application.decision.value_action_plan import project_value_action_plan
from value_investment_agent.application.product.value_decision_explanation import project_value_decision_explanation
from value_investment_agent.application.product.public_snapshot import publish_snapshot, load_current_packet
from value_investment_agent.application.product.daily_public_packet import packet_content_sha256
from value_investment_agent.application.portfolio.private_portfolio_service import PrivateJournal, PrivatePortfolioService
from value_investment_agent.application.product.dual_sleeve_risk import append_dual_sleeve_manual_record
from value_investment_agent.domain.portfolio.dual_sleeve_records import validate_manual_history
from value_investment_agent.operations.authorization.trust_root_registry import trust_root_fingerprint
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from test_portfolio_risk_assessment import _attributes
from value_investment_agent.application.portfolio.private_risk_projection import build_risk_input
from value_investment_agent.domain.portfolio.dual_sleeve_risk import review_dual_sleeve_risk
from value_investment_agent.domain.hotspot.price_action_plan import calculate_price_levels
from value_investment_agent.application.decision.value_policy_interaction import (
    ValuePolicyInteractionService, PolicyPrincipal, PERMISSION,
)
from value_investment_agent.application.decision import value_price_policy as policy_contract
from value_investment_agent.application.decision.value_action_plan import (
    load_registered_value_action_plans, load_value_action_policy,
)
from value_investment_agent.domain.decision.value_price_policy import draft_value_price_policy
from value_investment_agent.application.product.quote_bridge import pin_quote_bridge_for_symbol
from value_investment_agent.application.product.daily_public_packet import build_daily_public_packet


def _registered_policy_fixture(root, restored):
    registry = root / 'TEST_ONLY-combined-trust-registry.json'
    with _use_test_trust_registry(registry):
        return _registered_policy_fixture_trusted(root, restored)


def _registered_policy_fixture_trusted(root, restored):
    """Real publication readers and isolated policy registration over signed output."""
    now = datetime.fromisoformat('2026-09-21T19:00:00+08:00')
    symbol = restored.recommendation.symbol
    binding = lambda p: dict(path=p.relative_to(root).as_posix(), sha256=sha256_file(p))
    explanation = project_value_decision_explanation(restored, evidence_scope='RETAINED_RESEARCH')
    explanation['model_id'] = restored.recommendation.input_model_id
    explanation_path = root / f'runtime/{symbol}-value-decision-explanation.json'
    write_new_json(explanation_path, explanation)
    package_path = root / 'runtime/TEST_ONLY-signing/package.json'
    package = json.loads(package_path.read_text(encoding='utf-8'))
    # The quote reader requires runtime-local originals, even in isolated tests.
    quote_path = root / 'runtime/TEST_ONLY-quote.json'
    write_new_json(quote_path, json.loads((root / package['quote']['bundle_path']).read_text(encoding='utf-8')))
    pin_quote_bridge_for_symbol(root, symbol, quote_path, package_path,
        registered_at=now.isoformat())

    def publication(version, registry=None):
        folder = root / f'runtime/TEST_ONLY-canonical-{version}'
        snapshot = dict(action='no_order', as_of='2026-09-21',
            companies=[dict(symbol=symbol, company_name='TEST_ONLY')], opportunities=[])
        model = dict(schema_version='historical-company-read-model-preview-v1', action='no_order',
            scope='TEST_ONLY', snapshot=snapshot, additional_evidence_bindings=[binding(explanation_path)])
        if registry is not None:
            model['product_extensions'] = dict(value_action_policy_registry=registry)
        model_path = folder / 'model.json'
        write_new_json(model_path, model)
        handoff_path = folder / 'handoff.json'
        write_new_json(handoff_path, dict(schema_version='research-publication-input-v1',
            action='no_order', snapshot=snapshot, read_model_binding=binding(model_path)))
        sources_path = folder / 'sources.json'
        write_new_json(sources_path, dict(schema_version='existing-workbench-preview-bindings-v1',
            decision_workbench_binding=binding(root / 'runtime/TEST_ONLY-recomputed/workbench.json'),
            publication_input_binding=binding(handoff_path)))
        receipt_path = folder / 'receipt.json'
        write_new_json(receipt_path, dict(schema_version='canonical-reviewed-research-publication-v1',
            scope='TEST_ONLY_CONTRACT_FIXTURE_NOT_NATIVE_WPS_VERIFICATION', canonical_written=True,
            source_bindings_path=binding(sources_path)['path'], source_bindings_sha256=sha256_file(sources_path)))
        state_path = folder / 'state.json'
        write_new_json(state_path, dict(action='no_order', content=dict(companies={}, extensions={})))
        pointer_path = root / 'config/current-trial-workbook.json'
        # Only the isolated fixture pointer is versioned; no actual workbook is written.
        from value_investment_agent.application.product.public_snapshot import _atomic_write_json
        _atomic_write_json(pointer_path, dict(schema_version='m7-current-trial-workbook-v5',
            action='no_order', as_of='2026-09-21', daily_product_state_binding=binding(state_path),
            current_publication=dict(status='PUBLISHED_WPS_READONLY_VERIFIED',
                receipt=binding(receipt_path)['path'], receipt_sha256=sha256_file(receipt_path))))

    publication('before')
    current = load_registered_value_action_plans(root, now=now, symbols=[symbol])
    assert current['blockers'] == [] and len(current['items']) == 1
    current_plan = current['items'][0]
    draft = draft_value_price_policy(current_plan, draft_id='TEST_ONLY-review', policy_id='TEST_ONLY',
        rule_version='TEST_ONLY-v1', profile_id=current_plan['profile_id'],
        effective_from=date(2026, 9, 21), effective_through=date(2026, 10, 21),
        rationale='TEST_ONLY explicit policy', dividend_coverage_risk='TEST_ONLY unknown', rules=[])
    prepared = policy_contract.prepare_value_price_policy(root, draft, now=now)
    review = dict(schema_version='tl11-p5-value-model-review-v1', symbol=symbol, action='no_order',
        reviewed_at=now.isoformat(), formal_eligibility=False, portfolio_eligibility=None,
        direct_hash_checks=current_plan['source_bindings'],
        scenarios={key: current_plan[key] for key in ('bear', 'base', 'bull')},
        model_identity_evidence=current_plan.get('model_identity_evidence'),
        **{key: current_plan[key] for key in ('model_id', 'model_type', 'model_version',
            'valuation_input_version', 'valuation_date')})
    manifest_path = root / policy_contract.REVIEW_MANIFEST_PATH
    roles = {}
    for role, payload in dict(model_review=review, draft=draft, preparation=prepared).items():
        path = manifest_path.parent / f'value-{role}.json'
        write_new_json(path, payload)
        roles[role] = binding(path)
    write_new_json(manifest_path, dict(schema_version='value-policy-review-manifest-v1',
        action='no_order', items={symbol: roles}))
    principal = PolicyPrincipal('TEST_ONLY-P7-owner', frozenset({PERMISSION}))
    service = ValuePolicyInteractionService(root,
        storage_relative='.tmp/value-policy-review/TEST_ONLY-P7', isolated=True)
    selection = dict(effective_from='2026-09-21', effective_through='2026-10-21',
        rationale='TEST_ONLY owner choice', dividend_coverage_risk='TEST_ONLY unknown',
        rules=[dict(action='entry', scenario='bear', value_fraction='0.93', comparison='LTE',
            rationale='TEST_ONLY explicit rule')])
    preview = service.preview(symbol, selection, principal=principal, now=now)
    registered = service.confirm(preview['preview_id'], dict(acknowledged=True, note='TEST_ONLY owner'),
        principal=principal, now=now)
    restarted = ValuePolicyInteractionService(root,
        storage_relative='.tmp/value-policy-review/TEST_ONLY-P7', isolated=True)
    loaded = restarted.status(symbol, principal=principal, now=now)
    assert loaded['status'] == registered['status'] == 'REGISTERED'
    assert loaded['registry_binding'] == registered['registry_binding']
    assert loaded['scope'] == 'ISOLATED_TEST' and loaded['production_published'] is False
    # Publish the service-produced registry as an isolated public fixture, then
    # load it through the real registered-policy reader, not a direct constructor.
    registry_path = root / 'runtime/TEST_ONLY-registered-policy.json'
    write_new_json(registry_path, json.loads((root / loaded['registry_binding']['path']).read_text(encoding='utf-8')))
    public_binding = binding(registry_path)
    publication('after', public_binding)
    policy = load_value_action_policy(root=root, binding=public_binding, symbol=symbol, now=now)
    assert policy.policy_id == loaded['registered_policy']['draft']['policy_id']
    assert loaded['conditional_plan']['formal_eligibility'] is project_value_action_plan(
        restored, evidence_scope='RETAINED_RESEARCH', policy=policy)['formal_eligibility']
    return policy, public_binding


def recalculate(fixture, version, packet=None):
    root = fixture['root']
    output = root / f'runtime/TEST_ONLY-{version}/research.json'
    kwargs = {} if packet is None else dict(
        reviews_path=root / packet['path'], reviews_sha256=packet['sha256'])
    with _use_test_trust_registry(fixture['registry']):
        result = run_company_research_for_symbol(
            root=root, symbol=fixture['candidate']['symbol'],
            package_path=fixture['path'].parent / 'package.json',
            schedule_request=dict(schema_version='research-schedule-request-v1',
                symbol=fixture['candidate']['symbol'], source_id='CNINFO',
                period=fixture['candidate']['prior_research_as_of'],
                research_question_id='TEST_ONLY-p7-review', blocker_id='no-active-evidence-stop',
                reopen_condition_met=False, new_evidence_ids=[]),
            output_path=output, **kwargs)
    return output, result


def handoff(fixture, output, receipt, version):
    root = fixture['root']
    preview = root / f'runtime/TEST_ONLY-{version}/preview.json'
    write_new_json(preview, dict(
        schema_version='historical-company-read-model-preview-v1',
        action='no_order', canonical_written=False, historical_preview=True,
        scope='TEST_ONLY_NOT_REAL_PUBLICATION', snapshot=receipt['result'],
        source_catalog=[dict(path=output.relative_to(root).as_posix(), sha256=sha256_file(output)),
            dict(path='runtime/response-consumed/receipt.json',
                sha256=sha256_file(root / 'runtime/response-consumed/receipt.json'))]))
    target = preview.parent / 'publication-input.json'
    result = prepare_research_publication_input(root=root, read_model_path=preview,
        expected_sha256=sha256_file(preview), output_path=target)
    assert load_research_publication_input(root=root, path=target,
        expected_sha256=sha256_file(target)) == result
    return target, result


def test_signed_import_recalculates_new_version_with_replayable_publication_evidence(signed):
    root = signed['root']
    candidate_files = {p: p.read_bytes() for p in signed['path'].parent.glob('*.json')}
    before_path, before = recalculate(signed, 'before')
    before_bytes = before_path.read_bytes()
    signed['response']['whole_model_approval'] = whole_approval(signed)
    imported = consume(signed)
    packet = imported['review_packet_binding']
    after_path, after = recalculate(signed, 'after', packet)
    result = after['result']
    assert before['result']['human_research_approval'] is None
    assert result['human_research_approval']['reviewer_id'] == 'SYNTHETIC_HUMAN'
    assert result['input_descriptor_sha256'] != before['result']['input_descriptor_sha256']
    assert after['receipt']['input_sha256']['research_reviews'] == packet['sha256']
    assert result['valuation'] == before['result']['valuation']
    assert result['event_materiality_review'] is None
    assert result['decision_recommendation']['position_guidance'] is None
    assert result['action'] == 'no_order'
    assert not imported['price_admitted'] and not imported['research_admitted']
    target, evidence = handoff(signed, after_path, after, 'after')
    bindings = {item['path']: item['sha256'] for item in evidence['source_bindings']}
    assert bindings[packet['path']] == packet['sha256']
    for path in ('response.json', 'trust.json', 'runtime/response-consumed/receipt.json'):
        assert bindings[path] == sha256_file(root / path)
    assert evidence['snapshot'] == result
    assert not evidence['canonical_written'] and not evidence['publication_approved']
    assert before_path.read_bytes() == before_bytes
    assert all(p.read_bytes() == raw for p, raw in candidate_files.items())
    assert not (root / 'config/current-trial-workbook.json').exists()
    assert target.is_relative_to(root / 'runtime')


@pytest.mark.parametrize('dependency', ['response.json', 'runtime/response-consumed/human-approval.json'])
def test_post_import_tampering_blocks_recalculation_and_handoff_reverification(signed, dependency):
    signed['response']['whole_model_approval'] = whole_approval(signed)
    imported = consume(signed)
    output, result = recalculate(signed, 'valid', imported['review_packet_binding'])
    target, _ = handoff(signed, output, result, 'valid')
    digest = sha256_file(target)
    path = signed['root'] / dependency
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError):
        recalculate(signed, 'tampered', imported['review_packet_binding'])
    assert not (signed['root'] / 'runtime/TEST_ONLY-tampered/research.json').exists()
    with pytest.raises(ValueError, match='hash'):
        load_research_publication_input(root=signed['root'], path=target, expected_sha256=digest)


def test_signed_revocation_blocks_old_packet_in_actual_recalculation(signed):
    signed['response']['whole_model_approval'] = whole_approval(signed)
    imported = consume(signed)
    output, _ = recalculate(signed, 'approved', imported['review_packet_binding'])
    preserved = output.read_bytes()
    signed['response'].update(reviewed_at=datetime.now(timezone.utc).isoformat(),
        supersedes_response_sha256=sha256_file(signed['root'] / 'response.json'),
        whole_model_approval=None)
    signed['response']['groups'][0]['response'] = 'REJECTED'
    revoked = consume(signed, suffix='-revoked', previous=signed['root'] / 'response.json')
    assert 'EARNINGS:REJECTED' in revoked['blockers']
    assert 'review_packet_binding' not in revoked
    with pytest.raises(ValueError, match='superseded'):
        recalculate(signed, 'revoked', imported['review_packet_binding'])
    assert output.read_bytes() == preserved
    assert not (signed['root'] / 'runtime/TEST_ONLY-revoked/research.json').exists()


@pytest.mark.parametrize('failure', ['unpinned', 'wrong-signing-key'])
def test_unauthorized_import_cannot_produce_downstream_review_evidence(signed, failure):
    signed['response']['whole_model_approval'] = whole_approval(signed)
    if failure == 'wrong-signing-key':
        signed['key'] = Ed25519PrivateKey.generate()
    with pytest.raises(ValueError, match='not pinned|signature'):
        consume(signed, pin=failure != 'unpinned')
    root = signed['root']
    assert not (root / 'runtime/response-consumed').exists()
    assert not (root / 'runtime/research-review-responses').exists()
    output, result = recalculate(signed, 'unauthorized')
    assert result['result']['human_research_approval'] is None
    assert result['result']['decision_recommendation']['position_guidance'] is None
    assert output.is_file()
    assert not list(root.rglob('publication-input.json'))


def _complete_signed_case(chain, monkeypatch, *, price_eligible=True):
    """Construct a pending receipt over real service output, then authenticate it.

    This deliberately bypasses the finite *economic proposal compiler*, which
    introduces unresolved assumptions by design, but never the candidate,
    signature, import, event, G3 or decision validators. All economics are fixtures.
    """
    from value_investment_agent.application.product import research_reviews, workbench
    from value_investment_agent.m1_valuation_package_builder import build_descriptor

    root, source, _, _, _, approval, event, event_hash = chain
    moment = datetime(2026, 9, 21, 10, tzinfo=timezone.utc)
    class TestClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment.astimezone(tz) if tz else moment.replace(tzinfo=None)
    # A deterministic historical test clock, not a substituted eligibility result.
    monkeypatch.setattr(research_reviews, 'datetime', TestClock)
    monkeypatch.setattr(workbench, 'datetime', TestClock)
    package = json.loads(source.read_text(encoding='utf-8'))
    package['recommendation_schema_version'] = 'advisory-decision-recommendation-v3'
    scan_path = root / 'synthetic-scan.json'
    scan_ref = dict(id='daily-event-'+event_hash, symbol=package['symbol'],
        path=scan_path.relative_to(root).as_posix(), sha256=event_hash)
    package['model_validity_input'].update(event_scan_ref=scan_ref, event_scan_evidence_refs=[scan_ref])
    folder = root / 'runtime/TEST_ONLY-signing'
    package_path = folder / 'package.json'
    write_new_json(package_path, package)
    descriptor = build_descriptor(package, root=root)
    context = build_research_review_model_context(descriptor=descriptor,
        spec=build_research_run_spec(descriptor))
    schedule = dict(schema_version='research-schedule-request-v1', symbol=descriptor.symbol,
        source_id='TEST_ONLY', period='2026-09-21', research_question_id='TEST_ONLY-P7',
        blocker_id='initial_research', reopen_condition_met=False, new_evidence_ids=[])
    work_path = folder / 'workbench.json'
    baseline = build_current_workbench_for_symbol(root=root, symbol=descriptor.symbol,
        package_path=package_path, output_path=work_path, schedule_request=schedule)['result']
    assert baseline['suggested_state'] == 'NO_ACTION'
    groups = [dict(id='TEST_ONLY-COMPLETE', question='Accept exact TEST_ONLY model?',
        support='Synthetic complete sample', countercase='Not real issuer evidence',
        impact='TEST_ONLY research and price review', field_paths=['facts.operating_inputs'])]
    economic_policy = folder / 'economic-policy.json'
    write_new_json(economic_policy, dict(scope='TEST_ONLY', human_review_groups=groups))
    binding = lambda p: dict(path=p.relative_to(root).as_posix(), sha256=sha256_file(p))
    candidate = dict(schema_version='pending-research-candidate-v1', status='PENDING_REVIEW',
        action='no_order', symbol=descriptor.symbol, approval_changed=False, research_admitted=False,
        price_admitted=False, canonical_written=False, registered_current_case_changed=False,
        position_guidance=None, strict_contemporaneous_pit='NOT_PROVEN',
        candidate_research_as_of='2026-09-21', model_context=context,
        candidate_valuation=baseline['valuation'], model_context_scope='ACTUALLY_CONSUMED',
        execution_status=baseline['suggested_state'], research_blockers=baseline['research_blockers'],
        schedule_gate=baseline['schedule_gate'], economic_policy_binding=binding(economic_policy),
        source_bindings=[binding(p) for p in (package_path, work_path, economic_policy)], review_groups=groups)
    path = folder / 'candidate.json'
    write_new_json(path, candidate)
    response = prepare_pending_review_response(root=root, candidate_path=path,
        candidate_sha256=sha256_file(path))
    response.update(reviewer_id='TEST_ONLY-P7-REVIEWER', reviewed_at=moment.isoformat())
    response['groups'][0].update(response='VERIFIED', response_reason='TEST_ONLY exact sample reviewed',
        confirmed_scope='TEST_ONLY model, not production or trading authorization')
    approval = replace(approval, reviewer_id=response['reviewer_id'], reviewed_at=moment,
        price_assessment_eligible=price_eligible)
    response['whole_model_approval'] = approval.as_policy()
    key = Ed25519PrivateKey.generate()
    trust = dict(schema_version='research-review-transport-trust-root-v1',
        reviewer_id=response['reviewer_id'], public_key=key.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw).hex(), scopes=['human_group_research', 'human_whole_model'],
        symbols=[descriptor.symbol], valid_from=(moment-timedelta(days=1)).isoformat(),
        valid_until=(moment+timedelta(days=1)).isoformat())
    registry = root / 'TEST_ONLY-trust-registry.json'
    write_new_json(registry, dict(schema_version='authorization-trust-root-registry-v1',
        pinned_trust_root_sha256=[trust_root_fingerprint(trust)]))
    fixture = dict(root=root, path=path, candidate=candidate, response=response, key=key,
        trust=trust, registry=registry)
    imported = consume(fixture)
    # Compose the existing v2 packet, retaining authenticated G3 provenance.
    packet = json.loads((root / imported['review_packet_binding']['path']).read_text(encoding='utf-8'))
    from value_investment_agent.application.product.research_materiality_reviews import (
        MATERIALITY_RESPONSE_PURPOSE, prepare_materiality_review_handoff, consume_materiality_review_response,
    )
    from value_investment_agent.research_run_contract import canonical_contract_payload
    handoff = prepare_materiality_review_handoff(root=root, package_path=package_path,
        package_sha256=sha256_file(package_path), scan_path=scan_path, scan_sha256=event_hash)
    assert handoff['model_context'] == context
    handoff_path = folder / 'materiality-handoff.json'
    write_new_json(handoff_path, handoff)
    reviewer = 'TEST_ONLY-P7-MATERIALITY'
    typed = replace(event, reviewer_id=reviewer, reviewed_at=moment,
        decisions=tuple(replace(d, reviewer_id=reviewer, reviewed_at=moment) for d in event.decisions)).as_policy()
    typed['model_context'] = context
    material_response = dict(handoff['unsigned_response'], reviewer_id=reviewer,
        reviewed_at=moment.isoformat(), event_materiality=typed)
    material_response_path = folder / 'materiality-response.json'
    write_new_json(material_response_path, dict(payload=material_response, signature=key.sign(
        MATERIALITY_RESPONSE_PURPOSE+canonical_contract_payload(material_response).encode('utf-8')).hex()))
    material_trust = dict(trust, reviewer_id=reviewer, scopes=['human_event_materiality'],
        valid_until=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
    material_trust_path = folder / 'materiality-trust.json'
    write_new_json(material_trust_path, material_trust)
    registry = root / 'TEST_ONLY-combined-trust-registry.json'
    write_new_json(registry, dict(schema_version='authorization-trust-root-registry-v1',
        pinned_trust_root_sha256=[trust_root_fingerprint(trust), trust_root_fingerprint(material_trust)]))
    with _use_test_trust_registry(registry):
        material_receipt = consume_materiality_review_response(root=root,
            handoff_path=handoff_path, handoff_sha256=sha256_file(handoff_path),
            response_path=material_response_path, response_sha256=sha256_file(material_response_path),
            trust_root_path=material_trust_path, trust_root_sha256=sha256_file(material_trust_path),
            output_dir=root / 'runtime/TEST_ONLY-materiality-consumed')
    material_packet = json.loads((root / material_receipt['review_packet_binding']['path']).read_text(encoding='utf-8'))
    packet.update(schema_version='shared-research-review-inputs-v2', model_context=context,
        authenticated_materiality_binding=material_packet['authenticated_materiality_binding'])
    packet['bindings']['event_materiality'] = material_packet['bindings']['event_materiality']
    reviews_path = folder / 'complete-reviews.json'
    write_new_json(reviews_path, packet)
    after_path = root / 'runtime/TEST_ONLY-recomputed/workbench.json'
    with _use_test_trust_registry(registry):
        after = build_current_workbench_for_symbol(root=root, symbol=descriptor.symbol,
            package_path=package_path, output_path=after_path, schedule_request=schedule,
            reviews_path=reviews_path, reviews_sha256=sha256_file(reviews_path))['result']
    with _use_test_trust_registry(registry):
        restored = verify_current_decision_workbench(
            after,
            human_approval_provenance_verifier=lambda approval: (
                verify_human_approval_transport_provenance(root, approval)
            ),
        )
    attached_approval = restored.dependency_objects['human_approval']
    assert attached_approval.authenticated_transport_binding is not None
    assert attached_approval.verified_transport is not None
    assert replace(attached_approval, authenticated_transport_binding=None) == approval
    assert restored.dependency_objects['event_materiality'].scan_sha256 == event_hash
    assert after['pre_decision_eligibility']['positive_price_review_eligible'] is price_eligible
    assert after['suggested_state'] == ('BUY_CANDIDATE' if price_eligible else 'NO_ACTION')
    assert baseline['valuation'] == after['valuation']
    return restored, after_path, binding(root / 'runtime/response-consumed/receipt.json')


def test_full_signed_research_public_publish_ips_risk_buy_sell_history(synthetic_chain, monkeypatch):
    root = synthetic_chain[0]
    restored, research_path, import_binding = _complete_signed_case(synthetic_chain, monkeypatch)
    policy, policy_binding = _registered_policy_fixture(root, restored)
    plan = project_value_action_plan(restored, evidence_scope='SYNTHETIC_TEST', policy=policy)
    assert plan['formal_eligibility'] is True, plan['formal_eligibility_blockers']
    assert plan['entry_condition']['triggered'] is True
    assert plan['candidate_action'] == 'BUY_CANDIDATE' and plan['position_guidance'] is None
    symbol = plan['symbol']
    # Explicit synthetic bars for the SAME signed research security. These are
    # a scenario, never issuer market evidence or production hotspot admission.
    bars = [dict(time=f'2026-09-{day:02}T15:00:00+08:00', open='4.85',
        high='4.90', low='4.80', close='4.85', volume='1000') for day in (14, 15, 16, 17, 18)]
    bars.append(dict(time='2026-09-21T15:00:00+08:00', open='4.90', high='5.10',
        low='4.85', close='5', volume='1500'))
    bars_path = root / 'runtime/TEST_ONLY-hotspot-bars.json'
    write_new_json(bars_path, dict(namespace='SIMULATED', scope='TEST_ONLY', bars=bars))
    bars_binding = dict(path=bars_path.relative_to(root).as_posix(), sha256=sha256_file(bars_path))
    hotspot_plan = dict(calculate_price_levels(bars, period='daily'), symbol=symbol,
        schema_version='price-action-plan-independent-v2', strategy='HOTSPOT_SATELLITE',
        namespace='SIMULATED', scope='TEST_ONLY_SYNTHETIC_PRICE_SCENARIO',
        research_version=plan['research_version'], signed_research_binding=import_binding,
        source_bindings=[bars_binding])
    assert hotspot_plan['breakout_observed'] is True
    with _use_test_trust_registry(root / 'TEST_ONLY-combined-trust-registry.json'):
        packet = build_daily_public_packet(root,
            generated_at=datetime.fromisoformat('2026-09-21T19:00:00+08:00'))
    assert packet['packet_status'] == 'CURRENT' and packet['chain_error'] is None
    assert packet['value_price_conditions'][symbol]['safety_margin_policy']['policy_id'] == policy.policy_id
    assert packet['value_price_conditions'][symbol]['formal_eligibility'] is True
    assert packet['value_price_conditions'][symbol]['entry_condition']['triggered'] is True
    write_new_json(root / 'runtime/TEST_ONLY-built-packet.json', packet)
    # Production hotspot acquisition is outside this synthetic fixture. Preserve
    # builder output and explicitly attach the separately simulated bar scenario.
    packet.update(scope='TEST_ONLY_NOT_PRODUCTION', research_version=plan['research_version'])
    packet['source_bindings'].extend([import_binding, policy_binding, bars_binding,
        dict(path=research_path.relative_to(root).as_posix(), sha256=sha256_file(research_path))])
    packet['price_conditions']['items'] = [dict(symbol=symbol, price_action_plan=hotspot_plan)]
    packet['content_sha256'] = packet_content_sha256(packet)
    packet_path = root / 'runtime/TEST_ONLY-public-packet.json'
    write_new_json(packet_path, packet)
    pointer = publish_snapshot(root, packet, packet_path,
        published_at=datetime.fromisoformat('2026-09-21T18:00:00+08:00'))
    assert load_current_packet(root) == (packet, None)
    assert (root / pointer['receipt_path']).is_file()
    original_packet_bytes = packet_path.read_bytes()
    current_packet = packet

    service = PrivatePortfolioService(PrivateJournal(root / 'TEST_ONLY-P7.jsonl'))
    service.initialize(dict(idempotency_key='init', expected_revision=0,
        account_scope='TEST_ONLY_P7_NOT_REAL_ACCOUNT', as_of='2026-09-20', cash_cny='10000',
        holdings=[], sleeve_allocations={}, policy={}, confirmed_at='2026-09-20T20:00:00+08:00',
        confirmation_note='TEST_ONLY'))
    ips = full_policy()
    ips.update(effective_date='2026-09-21', emergency_cash_cny='100', liquidity_needs_cny='100',
        max_cyclical_exposure_pct='70', tax_regime='TEST_ONLY')
    ips['sleeves']['CORE_VALUE']['cash_cny'] = '7000'
    ips['hotspot_single_trade_risk_pct'] = '10'  # Explicit TEST_ONLY IPS choice.
    _, digest = service.prepare_policy(dict(idempotency_key='ips', expected_revision=1, policy=ips))
    service.confirm_policy(dict(idempotency_key='ips-confirm', expected_revision=len(service.records()),
        prepared_record_sha256=digest, confirmed_at='2026-09-20T20:01:00+08:00',
        confirmation_note='TEST_ONLY explicit IPS'))
    assert service.policy_view()['status'] == 'CONFIRMED'
    initial = _simulated_review(service, day='2026-09-21', review_hour=19)
    assert initial['status'] == 'RISK_REVIEW_CALCULATED' and initial['blockers'] == []
    now = datetime.fromisoformat('2026-09-21T19:00:00+08:00')
    request = dict(sleeve='HOTSPOT_SATELLITE', symbol=symbol,
        entry_price_cny=hotspot_plan['reference_close'], stop_price_cny=hotspot_plan['invalidation_price'],
        gap_stress_cny='0.10', entry_slippage_cny='0.01', exit_slippage_cny='0.01',
        buy_fee_fraction='0.001', sell_fee_fraction='0.001', minimum_buy_fee_cny='5',
        minimum_sell_fee_cny='5', lot_size=100, max_trade_notional_cny='2000',
        quote_as_of='2026-09-21', available_at=now.isoformat(),
        valid_until=(now+timedelta(hours=1)).isoformat(), liquidity_verified=True,
        limit_up=False, limit_down=False,
        research_version_sha256=hashlib.sha256(plan['research_version'].encode()).hexdigest(),
        evidence_ref='TEST_ONLY published synthetic hotspot scenario')
    risk_input = build_risk_input(service._replay(service.records()), sellable_as_of=date(2026, 9, 21),
        namespace='SIMULATED', generated_at=now, hotspot_request=request, _prices={})
    risk_input['portfolio']['snapshot']['namespace'] = 'SIMULATED'
    risk_input['shared_budget']['policy_scope'] = 'SYNTHETIC_POLICY_ONLY'
    risk_input['security_attributes'] = [_attributes(symbol).as_policy()]
    journal_before_sizing = service.journal.path.read_bytes()
    sized = review_dual_sleeve_risk(risk_input, generated_at=now, allow_synthetic=True)
    sizing = sized['hotspot_quantity_review']
    assert sized['namespace'] == 'SIMULATED' and sized['trade_eligible'] is False
    assert sizing['status'] == 'QUANTITY_REVIEW_ONLY' and sizing['blockers'] == []
    quantity = Decimal(sizing['review_quantity'])
    assert quantity > 0 and quantity % request['lot_size'] == 0
    assert Decimal(sizing['stressed_loss_cny']) <= Decimal(sizing['planned_risk_limit_cny'])
    assert Decimal(sizing['cash_required_cny']) <= Decimal(initial['sleeves']['HOTSPOT_SATELLITE']['available_funds_cny'])
    assert service.journal.path.read_bytes() == journal_before_sizing
    # An execution uncertainty must remove the computed number, not reuse it.
    blocked_input = deepcopy(risk_input)
    blocked_input['hotspot_request']['liquidity_verified'] = False
    assert review_dual_sleeve_risk(blocked_input, generated_at=now, allow_synthetic=True)[
        'hotspot_quantity_review']['review_quantity'] is None
    sizing_path = root / 'runtime/TEST_ONLY-sizing.json'
    write_new_json(sizing_path, dict(research_binding=import_binding, plan=hotspot_plan,
        assumptions=risk_input, result=sized))
    buy_price = Decimal(request['entry_price_cny']) + Decimal(request['entry_slippage_cny'])
    captured = None
    for side, day, price in [('BUY', '2026-09-21', buy_price),
                             ('SELL', '2026-09-22', buy_price + 2)]:
        _, digest = service.prepare_fill(dict(idempotency_key=side, expected_revision=len(service.records()),
            fill=dict(transaction_id='TEST_ONLY-'+side, side=side, sleeve='HOTSPOT_SATELLITE', symbol=symbol,
                exchange='SSE', quantity=str(quantity), price_cny=str(price), fees_cny='5', trade_date=day,
                trading_unit='100' if side == 'BUY' else None,
                next_sell_session='2026-09-22' if side == 'BUY' else None,
                decision_id='hotspot-'+symbol, research_version=plan['research_version'])), repository_root=root)
        service = PrivatePortfolioService(PrivateJournal(service.journal.path))
        service.confirm_fill(dict(idempotency_key=side+'-confirm', expected_revision=len(service.records()),
            prepared_record_sha256=digest, confirmed_at=day+'T20:00:00+08:00',
            confirmation_note='TEST_ONLY human simulated fill; no broker order'))
        view = service.portfolio_view(today=date.fromisoformat(day))
        if side == 'BUY':
            captured = deepcopy(view['trades'][0]['judgment_snapshot'])
            assert captured['plan'] == hotspot_plan and captured['publication_id'] == pointer['publication_id']
            assert captured['public_packet_content_sha256'] == packet['content_sha256']
            assert view['positions'][0]['sleeves'][0]['sellable_quantity'] == '0'
            assert Decimal(view['positions'][0]['sleeves'][0]['quantity']) == quantity
            assert Decimal(service.portfolio_view(today=date(2026, 9, 22))['positions'][0]['sleeves'][0]['sellable_quantity']) == quantity
            held_risk = _simulated_review(service, day=day, mark=buy_price + Decimal('0.05'))
            assert held_risk['aggregate']['existing_risk_assessment']['status'] == 'PASS'
            # P8: an actual-shaped isolated fill must remain reviewed after it
            # leaves every discovery ranking; this does not certify a real hold.
            from value_investment_agent.application.portfolio.held_continuity import project_held_continuity
            held_plan = dict(hotspot_plan, action='no_order', symbol=symbol,
                data_available_at=now.isoformat(), signal_state='WATCH')
            continued = project_held_continuity(view['positions'],
                {'engine': held_risk, 'blockers': []}, selected_symbols=(),
                plan_provider=lambda code: held_plan if code == symbol else None,
                generated_at=datetime.fromisoformat(day+'T20:00:00+08:00'))
            assert len(continued['items']) == 1
            assert continued['items'][0]['selected_today'] is False
            assert continued['items'][0]['sellable_quantity'] == '0'
            assert continued['items'][0]['strategy_plan']['research_version'] == plan['research_version']
            # Use the real publication writer for the version switch too.
            current_packet = dict(deepcopy(packet), publication_id='TEST_ONLY-P7-F2-next',
                generated_at='2026-09-22T18:00:00+08:00')
            current_packet['content_sha256'] = packet_content_sha256(current_packet)
            next_path = root / 'runtime/TEST_ONLY-public-packet-next.json'
            write_new_json(next_path, current_packet)
            publish_snapshot(root, current_packet, next_path,
                published_at=datetime.fromisoformat('2026-09-22T18:00:00+08:00'))
            assert load_current_packet(root) == (current_packet, None)
    final = PrivatePortfolioService(PrivateJournal(service.journal.path)).portfolio_view(today=date(2026, 9, 22))
    expected_equity = Decimal('10000') + quantity * 2 - 10
    assert final['positions'] == [] and Decimal(final['total_equity_cny']) == expected_equity
    assert [row['side'] for row in final['trades']] == ['BUY', 'SELL']
    assert all(Decimal(row['quantity']) == quantity for row in final['trades'])
    assert final['trades'][0]['judgment_snapshot'] == captured
    assert final['trades'][1]['judgment_snapshot']['publication_id'] == current_packet['publication_id']
    assert packet_path.read_bytes() == original_packet_bytes
    closed = _simulated_review(service, day='2026-09-22')
    assert Decimal(closed['aggregate']['total_assets_cny']) == expected_equity
    assert held_risk['aggregate'] != closed['aggregate']
    assert project_held_continuity(final['positions'], {'engine': closed, 'blockers': []},
        selected_symbols=(), plan_provider=lambda code: None,
        generated_at=datetime.fromisoformat('2026-09-22T21:00:00+08:00'))['items'] == []
    journal_bytes = service.journal.path.read_bytes()
    now = datetime.fromisoformat('2026-09-22T21:00:00+08:00')
    body = dict(record_id='TEST_ONLY-P7-plan', kind='PLAN', namespace='SIMULATED', sleeve='HOTSPOT_SATELLITE',
        symbol=symbol, recorded_at='2026-09-21T19:00:00+08:00', trade_date='2026-09-21',
        research_version_sha256=hashlib.sha256(plan['research_version'].encode()).hexdigest(),
        candidate_action=plan['candidate_action'], observed_price_cny=str(buy_price),
        reason='TEST_ONLY signed research; engine-sized quantity='+str(quantity),
        risk_budget_cny=sizing['planned_risk_limit_cny'],
        invalidation_condition=hotspot_plan['invalidation_rule'], user_confirmation='PENDING',
        plan_record_sha256=None, fill=None, retrospective=None, evidence_ref=captured['snapshot_sha256'])
    directory = root / '.tmp/TEST_ONLY-P7-history'
    first = append_dual_sleeve_manual_record(root=root, directory=directory, body=body,
        expected_head_sha256=None, synthetic=True, generated_at=now)
    review = dict(body, record_id='TEST_ONLY-P7-review', kind='REVIEW', recorded_at=now.isoformat(),
        trade_date='2026-09-22', user_confirmation='USER_CONFIRMED', plan_record_sha256=first['record_sha256'],
        retrospective='TEST_ONLY signed publication; engine quantity='+str(quantity)
        +'; sizing evidence='+sha256_file(sizing_path)+'; T+1 BUY/SELL; realized PnL='+final['realized_pnl_cny'])
    last = append_dual_sleeve_manual_record(root=root, directory=directory, body=review,
        expected_head_sha256=first['record_sha256'], synthetic=True, generated_at=now)
    history = [json.loads(p.read_text(encoding='utf-8')) for p in sorted(directory.glob('*.json'))]
    assert validate_manual_history(history, namespace='SIMULATED', generated_at=now) == last['record_sha256']
    assert 'engine quantity='+str(quantity) in history[-1]['body']['retrospective']
    assert sha256_file(sizing_path) in history[-1]['body']['retrospective']
    assert last['changes_holdings'] is False and last['acceptance_authority'] == 'NONE'
    assert service.journal.path.read_bytes() == journal_bytes
    assert load_current_packet(root) == (current_packet, None)


def test_signed_research_without_explicit_price_permission_cannot_qualify_plan(synthetic_chain, monkeypatch):
    restored, _, _ = _complete_signed_case(synthetic_chain, monkeypatch, price_eligible=False)
    policy, _ = _registered_policy_fixture(synthetic_chain[0], restored)
    plan = project_value_action_plan(restored, evidence_scope='SYNTHETIC_TEST', policy=policy)
    assert plan['formal_eligibility'] is False
    assert plan['formal_eligibility_blockers']
    assert plan['candidate_action'] == 'NO_ACTION'
    registry = synthetic_chain[0] / 'TEST_ONLY-combined-trust-registry.json'
    with _use_test_trust_registry(registry):
        packet = build_daily_public_packet(synthetic_chain[0],
            generated_at=datetime.fromisoformat('2026-09-21T19:00:00+08:00'))
    assert packet['value_price_conditions'][plan['symbol']]['formal_eligibility'] is False
    assert not (synthetic_chain[0] / 'config/current-daily-public-snapshot.json').exists()
    assert not list(synthetic_chain[0].glob('*.jsonl'))


def test_v3_bundle_replay_requires_authenticated_transport_not_serialized_binding(
    synthetic_chain, monkeypatch,
):
    restored, after_path, _ = _complete_signed_case(synthetic_chain, monkeypatch)
    workbench = json.loads(after_path.read_text(encoding='utf-8'))
    approval_artifact = next(
        row for row in workbench['artifact_bundle']['artifacts']
        if row['identity'].get('artifact_type') == 'human_research_approval'
    )
    assert 'authenticated_transport_binding' in approval_artifact['canonical_payload']

    with pytest.raises(ValueError, match='PreDecision|repository replay|provenance'):
        verify_current_decision_workbench(workbench)

    root = synthetic_chain[0]
    with _use_test_trust_registry(root / 'TEST_ONLY-combined-trust-registry.json'):
        replayed = verify_current_decision_workbench(
            workbench,
            human_approval_provenance_verifier=lambda approval: (
                verify_human_approval_transport_provenance(root, approval)
            ),
        )
    assert replayed.recommendation.recommendation_type == 'BUY_CANDIDATE'
    assert replayed.dependency_objects['human_approval'].verified_transport is not None


@pytest.mark.parametrize('defect', ['missing', 'hash', 'dependency', 'future', 'explanation'])
def test_formal_packet_requires_exact_current_replay(synthetic_chain, monkeypatch, defect):
    from value_investment_agent.application.product.public_snapshot import _atomic_write_json
    from value_investment_agent.application.product.publication_chain import load_current_chain

    root = synthetic_chain[0]
    restored, _, _ = _complete_signed_case(synthetic_chain, monkeypatch)
    _registered_policy_fixture(root, restored)
    chain = load_current_chain(root)
    sources = chain['sources']
    work_binding = sources['decision_workbench_binding']
    work_path = root / work_binding['path']
    if defect == 'missing':
        del sources['decision_workbench_binding']
    else:
        work = json.loads(work_path.read_text(encoding='utf-8'))
        if defect == 'dependency':
            work['artifact_bundle']['artifacts'].pop()
        elif defect == 'future':
            work['generated_at'] = '2026-09-22T19:00:00+08:00'
        elif defect == 'explanation':
            # A valid replay cannot lend admission to different display facts.
            from value_investment_agent.application.decision.value_action_plan import replay_published_value_decision
            explanation = project_value_decision_explanation(restored, evidence_scope='RETAINED_RESEARCH')
            explanation['candidate_action'] = 'SELL_CANDIDATE'
            with _use_test_trust_registry(root / 'TEST_ONLY-combined-trust-registry.json'):
                with pytest.raises(ValueError, match='differs from replayed'):
                    replay_published_value_decision(root, explanation,
                        now=datetime.fromisoformat('2026-09-21T19:00:00+08:00'))
            return
        else:
            work['symbol'] = '000001'
        _atomic_write_json(work_path, work)
        if defect != 'hash':
            work_binding['sha256'] = sha256_file(work_path)
    # Rebind the isolated publication envelope so semantic replay, rather than
    # an unrelated outer hash failure, decides dependency admission.
    source_path = root / chain['receipt']['source_bindings_path']
    _atomic_write_json(source_path, sources)
    receipt = chain['receipt']
    receipt['source_bindings_sha256'] = sha256_file(source_path)
    receipt_path = root / chain['pointer']['current_publication']['receipt']
    _atomic_write_json(receipt_path, receipt)
    pointer = chain['pointer']
    pointer['current_publication']['receipt_sha256'] = sha256_file(receipt_path)
    _atomic_write_json(root / 'config/current-trial-workbook.json', pointer)
    with _use_test_trust_registry(root / 'TEST_ONLY-combined-trust-registry.json'):
        packet = build_daily_public_packet(root,
            generated_at=datetime.fromisoformat('2026-09-21T19:00:00+08:00'))
        plan = packet['value_price_conditions'].get(restored.recommendation.symbol)
        assert plan is None or plan.get('formal_eligibility') is not True
        if defect == 'missing':
            assert 'VALUE_VERIFIED_PREDECISION_REQUIRED' in plan['formal_eligibility_blockers']
        else:
            result = load_registered_value_action_plans(root,
                now=datetime.fromisoformat('2026-09-21T19:00:00+08:00'))
            assert result['items'] == []
            assert any('VALUE_PLAN_UNAVAILABLE:' in reason for reason in result['blockers'])


def test_other_security_in_same_chain_keeps_display_without_typed_policy_admission(synthetic_chain, monkeypatch):
    from value_investment_agent.application.product.public_snapshot import _atomic_write_json
    from value_investment_agent.application.product.publication_chain import load_current_chain
    from value_investment_agent.application.decision.value_action_plan import replay_published_value_decision

    root = synthetic_chain[0]
    now = datetime.fromisoformat('2026-09-21T19:00:00+08:00')
    restored, _, _ = _complete_signed_case(synthetic_chain, monkeypatch)
    _registered_policy_fixture(root, restored)
    chain = load_current_chain(root)
    symbol = '000333' if restored.recommendation.symbol != '000333' else '600887'
    # Display-only TEST_ONLY issuer fixture: never claim that the other issuer
    # owns the signed workbench or possesses a replayed approval.
    explanation = project_value_decision_explanation(restored, evidence_scope='RETAINED_RESEARCH')

    def display_issuer(value):
        if isinstance(value, dict):
            return {key: symbol if key == 'symbol' else display_issuer(item)
                    for key, item in value.items()}
        if isinstance(value, list):
            return [display_issuer(item) for item in value]
        return value

    explanation = display_issuer(explanation)
    explanation['company_name'] = 'TEST_ONLY other issuer display, not signed approval'
    explanation['model_id'] = restored.recommendation.input_model_id
    explanation['pre_decision'] = None
    explanation['human_approval'] = None
    explanation['price_context']['price_bridge'] = None
    explanation['price_context']['positive_price_review_eligible'] = False
    explanation['price_context']['formal_comparison'] = None
    explanation['blockers'] = ['TEST_ONLY_OTHER_ISSUER_REPLAY_REQUIRED']
    path = root / f'runtime/{symbol}-value-decision-explanation.json'
    write_new_json(path, explanation)
    binding = lambda p: dict(path=p.relative_to(root).as_posix(), sha256=sha256_file(p))
    chain['model']['additional_evidence_bindings'].append(binding(path))
    model_path = root / chain['handoff']['read_model_binding']['path']
    _atomic_write_json(model_path, chain['model'])
    chain['handoff']['read_model_binding'] = binding(model_path)
    handoff_path = root / chain['sources']['publication_input_binding']['path']
    _atomic_write_json(handoff_path, chain['handoff'])
    chain['sources']['publication_input_binding'] = binding(handoff_path)
    source_path = root / chain['receipt']['source_bindings_path']
    _atomic_write_json(source_path, chain['sources'])
    chain['receipt']['source_bindings_sha256'] = sha256_file(source_path)
    receipt_path = root / chain['pointer']['current_publication']['receipt']
    _atomic_write_json(receipt_path, chain['receipt'])
    chain['pointer']['current_publication']['receipt_sha256'] = sha256_file(receipt_path)
    _atomic_write_json(root / 'config/current-trial-workbook.json', chain['pointer'])
    registry = root / 'TEST_ONLY-combined-trust-registry.json'
    with _use_test_trust_registry(registry):
        assert replay_published_value_decision(root, explanation, now=now) == (None, None)
        plans = load_registered_value_action_plans(root, now=now)
    assert plans['blockers'] == []
    by_symbol = {item['symbol']: item for item in plans['items']}
    assert by_symbol[restored.recommendation.symbol]['formal_eligibility'] is True
    current = by_symbol[symbol]
    assert current['bear'] == by_symbol[restored.recommendation.symbol]['bear']
    assert current['formal_eligibility'] is False
    assert 'VALUE_VERIFIED_PREDECISION_REQUIRED' in current['formal_eligibility_blockers']
    assert chain['sources']['decision_workbench_binding'] not in current['source_bindings']

    draft = draft_value_price_policy(current, draft_id='TEST_ONLY-other-review',
        policy_id='TEST_ONLY-other', rule_version='TEST_ONLY-v1', profile_id=current['profile_id'],
        effective_from=date(2026, 9, 21), effective_through=date(2026, 10, 21),
        rationale='TEST_ONLY display policy', dividend_coverage_risk='TEST_ONLY unknown', rules=[])
    with _use_test_trust_registry(registry):
        prepared = policy_contract.prepare_value_price_policy(root, draft, now=now)
    review = dict(schema_version='tl11-p5-value-model-review-v1', symbol=symbol, action='no_order',
        reviewed_at=now.isoformat(), formal_eligibility=False, portfolio_eligibility=None,
        direct_hash_checks=current['source_bindings'],
        scenarios={key: current[key] for key in ('bear', 'base', 'bull')},
        model_identity_evidence=current.get('model_identity_evidence'),
        **{key: current[key] for key in ('model_id', 'model_type', 'model_version',
            'valuation_input_version', 'valuation_date')})
    manifest_path = root / policy_contract.REVIEW_MANIFEST_PATH
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    roles = {}
    for role, payload in dict(model_review=review, draft=draft, preparation=prepared).items():
        target = manifest_path.parent / f'value-TEST_ONLY-other-{role}.json'
        write_new_json(target, payload)
        roles[role] = binding(target)
    manifest['items'][symbol] = roles
    _atomic_write_json(manifest_path, manifest)
    principal = PolicyPrincipal('TEST_ONLY-P7-other-owner', frozenset({PERMISSION}))
    kwargs = dict(storage_relative='.tmp/value-policy-review/TEST_ONLY-other', isolated=True)
    service = ValuePolicyInteractionService(root, **kwargs)
    selection = dict(effective_from='2026-09-21', effective_through='2026-10-21',
        rationale='TEST_ONLY owner choice, not research approval', dividend_coverage_risk='Unknown',
        rules=[dict(action='entry', scenario='bear', value_fraction='0.93', comparison='LTE',
            rationale='TEST_ONLY explicit rule')])
    with _use_test_trust_registry(registry):
        preview = service.preview(symbol, selection, principal=principal, now=now)
        confirmed = service.confirm(preview['preview_id'], dict(acknowledged=True, note='TEST_ONLY'),
            principal=principal, now=now)
        status = ValuePolicyInteractionService(root, **kwargs).status(
            symbol, principal=principal, now=now)
    for result in (confirmed, status):
        assert result['status'] == 'REGISTERED'
        plan = result['conditional_plan']
        assert plan['symbol'] == symbol and plan['bear'] == current['bear']
        assert result['registered_policy']['draft']['basis']['symbol'] == symbol
        assert plan['formal_eligibility'] is False and plan['portfolio_eligibility'] is None
        assert 'VALUE_VERIFIED_PREDECISION_REQUIRED' in plan['formal_eligibility_blockers']
    # Same-issuer display corruption must still be rejected, not treated as an
    # unrelated issuer that can merely fall back to display-only mode.
    mismatched = project_value_decision_explanation(restored, evidence_scope='RETAINED_RESEARCH')
    mismatched['candidate_action'] = 'SELL_CANDIDATE'
    with _use_test_trust_registry(registry):
        with pytest.raises(ValueError, match='differs from replayed'):
            replay_published_value_decision(root, mismatched, now=now)


def test_registered_policy_restart_rejects_tampered_signed_sample_review(synthetic_chain, monkeypatch):
    """Registration cannot survive a changed public review original."""
    root = synthetic_chain[0]
    restored, _, _ = _complete_signed_case(synthetic_chain, monkeypatch)
    _registered_policy_fixture(root, restored)
    service = ValuePolicyInteractionService(root,
        storage_relative='.tmp/value-policy-review/TEST_ONLY-P7', isolated=True)
    principal = PolicyPrincipal('TEST_ONLY-P7-owner', frozenset({PERMISSION}))
    now = datetime.fromisoformat('2026-09-21T19:00:00+08:00')
    registry = root / 'TEST_ONLY-combined-trust-registry.json'
    with _use_test_trust_registry(registry):
        assert service.status(restored.recommendation.symbol, principal=principal, now=now)['status'] == 'REGISTERED'
    manifest = json.loads((root / policy_contract.REVIEW_MANIFEST_PATH).read_text(encoding='utf-8'))
    review_path = root / manifest['items'][restored.recommendation.symbol]['model_review']['path']
    review_path.write_bytes(review_path.read_bytes()+b' ')
    with _use_test_trust_registry(registry):
        status = service.status(restored.recommendation.symbol, principal=principal, now=now)
    assert status['status'] == 'REVIEW_REQUIRED' and status['conditional_plan'] is None
    assert len(list(service.store.glob('confirmed-*.json'))) == 1
