"""Unsigned local interaction never substitutes for authentic reviewer decisions."""
import json
import importlib.util
from pathlib import Path
import sys

import pytest

pytestmark = pytest.mark.usefixtures('synthetic_pending_candidate_clock')

from test_pending_review_intake import _candidate
from test_pending_review_response import signed, consume
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.research_review_wizard import draft_pending_review_response


@pytest.mark.parametrize('policy_state', ['absent', 'matching', 'mismatch', 'rejected-policy'])
def test_external_handoff_delivers_exact_candidate_and_no_identity_or_approval(tmp_path, monkeypatch, policy_state):
    from datetime import datetime, timezone
    from value_investment_agent.application.product import publication_chain, user_research_workflow
    from value_investment_agent.application.product.research_review_wizard import build_external_review_handoff
    from value_investment_agent.application.decision import value_price_policy
    from value_investment_agent.application.product.research_review_wizard import preview_pending_review_response
    path, candidate = _candidate(tmp_path)
    binding = dict(path=path.relative_to(tmp_path).as_posix(), sha256=sha256_file(path))
    config = tmp_path / 'config/user-research-workflow-v1.json'
    config.parent.mkdir(exist_ok=True)
    config.write_text(json.dumps(dict(schema_version='user-research-workflow-v1', action='no_order',
        review_candidates={candidate['symbol']: binding})), encoding='utf-8')
    manifest = tmp_path / value_price_policy.REVIEW_MANIFEST_PATH
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(dict(items={} if policy_state == 'absent' else {candidate['symbol']: {}})), encoding='utf-8')
    expected = preview_pending_review_response(root=tmp_path, candidate_path=path,
        candidate_sha256=binding['sha256'])['draft']['valuation_artifact_sha256']
    calls = []
    def current_policy(root_arg, symbol_arg, now):
        calls.append((root_arg, symbol_arg))
        if policy_state == 'rejected-policy':
            raise ValueError('Current research changed since review')
        return dict(draft=dict(basis=dict(valuation_input_version=(
            expected if policy_state == 'matching' else '0' * 64))),
            source_bindings=[dict(path=manifest.relative_to(tmp_path).as_posix(), sha256=sha256_file(manifest))],
            model_review=dict(scope='CURRENT_PUBLIC_POLICY_REVIEW'))
    monkeypatch.setattr(value_price_policy, 'load_value_policy_review', current_policy)
    monkeypatch.setattr(publication_chain, 'load_current_chain',
        lambda root: dict(sources=dict(source_bindings=[binding])))
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    if policy_state in ('mismatch', 'rejected-policy'):
        with pytest.raises(ValueError, match='current valuation|Current research changed'):
            build_external_review_handoff(root=tmp_path, symbol=candidate['symbol'], now=datetime.now(timezone.utc))
        assert calls == [(tmp_path, candidate['symbol'])]
        assert all(p.read_bytes() == raw for p, raw in before.items())
        return
    result = build_external_review_handoff(root=tmp_path, symbol=candidate['symbol'], now=datetime.now(timezone.utc))
    assert result['candidate_binding'] == binding
    assert result['status'] == 'EXTERNAL_SIGNATURE_REQUIRED'
    assert result['review_questions'][0]['countercase'] == 'Normalization unknown.'
    assert result['unsigned_response']['reviewer_id'] is None
    assert result['verification']['approval_changed'] is False
    assert result['verification']['research_admitted'] is False
    assert result['valuation_artifact_sha256']
    assert calls == ([] if policy_state == 'absent' else [(tmp_path, candidate['symbol'])])
    assert all(p.read_bytes() == raw for p, raw in before.items())
    monkeypatch.setattr(publication_chain, 'load_current_chain',
        lambda root: dict(sources=dict(source_bindings=[])))
    with pytest.raises(ValueError, match='not bound'):
        build_external_review_handoff(root=tmp_path, symbol=candidate['symbol'], now=datetime.now(timezone.utc))


def run(root, path, answers, show=None):
    values = iter(answers)
    return draft_pending_review_response(root=root, candidate_path=path,
        candidate_sha256=sha256_file(path), output_path=root/'runtime/wizard/draft.json',
        read=lambda prompt: next(values), show=show or (lambda value: None))


@pytest.mark.parametrize('answers', [['cancel'], ['VERIFIED', 'cancel'],
    ['VERIFIED', 'Reason', 'cancel'], ['VERIFIED', 'Reason', 'Scope', 'cancel']])
def test_cancel_at_every_stage_writes_nothing(tmp_path, answers):
    path, _ = _candidate(tmp_path)
    original = path.read_bytes()
    result = run(tmp_path, path, answers)
    assert result['status'] == 'CANCELLED'
    assert not (tmp_path/'runtime/wizard').exists()
    assert path.read_bytes() == original


@pytest.mark.parametrize('state', ['VERIFIED', 'REJECTED', 'INSUFFICIENT', 'skip'])
def test_partial_and_negative_drafts_remain_unsigned_without_identity(tmp_path, state):
    path, _ = _candidate(tmp_path)
    digest = sha256_file(path)
    previews = []
    answers = ['skip', 'save'] if state == 'skip' else [state, 'Reason', 'Scope', 'save']
    result = run(tmp_path, path, answers, previews.append)
    draft = json.loads((tmp_path/result['path']).read_text(encoding='utf-8'))
    assert draft['candidate_binding']['sha256'] == digest == sha256_file(path)
    assert draft['reviewer_id'] is draft['reviewed_at'] is draft['whole_model_approval'] is None
    assert draft['groups'][0]['response'] == (None if state == 'skip' else state)
    assert result['approval_changed'] is False
    assert result['status'] == 'UNSIGNED_DRAFT_SAVED_NOT_APPROVED'
    assert any('whole_model_approval' in text for text in previews)
    assert not (tmp_path/'runtime/research-review-responses').exists()


def test_candidate_changed_during_preview_is_rejected_without_draft(tmp_path):
    path, _ = _candidate(tmp_path)
    def show(text):
        if 'whole_model_approval' in text:
            path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='hash'):
        run(tmp_path, path, ['skip', 'save'], show)
    assert not (tmp_path/'runtime/wizard').exists()


def test_no_pinned_identity_cannot_consume_signed_input(signed):
    with pytest.raises(ValueError, match='not pinned'):
        consume(signed, pin=False)


def test_two_groups_can_save_only_one_response(tmp_path):
    from test_pending_research_candidate import candidate_inputs, run as prepare_candidate
    package, policy, request = candidate_inputs(tmp_path)
    payload = json.loads(policy.read_text(encoding='utf-8'))
    payload['human_review_groups'] = [dict(id=group, question='Synthetic question',
        support='Synthetic support', countercase='Unknown', impact='Conditional only',
        field_paths=['facts.operating_inputs']) for group in ('FIRST', 'SECOND')]
    policy.write_text(json.dumps(payload), encoding='utf-8')
    prepare_candidate(tmp_path, package, policy, request)
    path = tmp_path/'runtime/pending/candidate.json'
    result = run(tmp_path, path, ['VERIFIED', 'Reason', 'Scope', 'skip', 'save'])
    assert result['pending_groups'] == ['SECOND']
    assert result['approval_changed'] is False


@pytest.mark.parametrize('error', [EOFError, KeyboardInterrupt])
def test_interrupted_input_discards_draft(tmp_path, error):
    path, _ = _candidate(tmp_path)
    def read(prompt):
        raise error()
    result = draft_pending_review_response(root=tmp_path, candidate_path=path,
        candidate_sha256=sha256_file(path), output_path=tmp_path/'runtime/wizard/draft.json',
        read=read, show=lambda value: None)
    assert result['status'] == 'CANCELLED'
    assert not (tmp_path/'runtime/wizard').exists()


@pytest.mark.parametrize('replay', [False, True])
def test_cli_delegates_provided_signed_file_to_existing_consumer(signed, monkeypatch, capsys, replay):
    from test_pending_review_response import whole_approval
    from value_investment_agent.application.product.common import write_new_json
    from value_investment_agent.application.product.research_reviews import REVIEW_RESPONSE_PURPOSE
    from value_investment_agent.research_run_contract import canonical_contract_payload
    from value_investment_agent.operations.authorization.trust_root_registry import _use_test_trust_registry
    signed['response']['whole_model_approval'] = whole_approval(signed)
    root = signed['root']
    if replay:
        consume(signed)
    else:
        signature = signed['key'].sign(REVIEW_RESPONSE_PURPOSE +
            canonical_contract_payload(signed['response']).encode('utf-8')).hex()
        write_new_json(root/'response.json', dict(payload=signed['response'], signature=signature))
        write_new_json(root/'trust.json', signed['trust'])
    script = Path(__file__).resolve().parents[1]/'scripts/current/review_research.py'
    module_spec = importlib.util.spec_from_file_location('review_wizard_cli_test', script)
    cli = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, 'ROOT', root)
    monkeypatch.setattr(sys, 'argv', [str(script), '--symbol', signed['candidate']['symbol'],
        '--candidate', str(signed['path']), '--candidate-sha256', sha256_file(signed['path']),
        '--signed-review-response', str(root/'response.json'),
        '--review-trust-root', str(root/'trust.json')])
    with _use_test_trust_registry(signed['registry']):
        if replay:
            with pytest.raises(ValueError, match='predecessor|replay'):
                cli.main()
            assert not (root/'runtime/replayed-cli').exists()
            assert not (root/'runtime/research-review-consumptions').exists()
        else:
            assert cli.main() == 0
            result = json.loads(capsys.readouterr().out)
            assert result['authenticated_reviewer'] == 'SYNTHETIC_HUMAN'
            assert not result['price_admitted']
            assert len(list((root/'runtime/research-review-consumptions').glob('*/receipt.json'))) == 1


def test_cli_root_candidate_aliases_prepare_cancelled_draft(tmp_path, monkeypatch, capsys):
    path, candidate = _candidate(tmp_path)
    script = Path(__file__).resolve().parents[1]/'scripts/current/review_research.py'
    module_spec = importlib.util.spec_from_file_location('review_wizard_root_alias_test', script)
    cli = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    observed = {}
    def draft(**kwargs):
        observed.update(kwargs)
        return dict(status='CANCELLED', action='no_order', approval_changed=False)
    monkeypatch.setattr(cli, 'draft_pending_review_response', draft)
    monkeypatch.setattr(sys, 'argv', [str(script), '--symbol', candidate['symbol'],
        '--candidate', str(path.relative_to(tmp_path)), '--candidate-sha256', sha256_file(path)])
    assert cli.main() == 0
    assert observed['candidate_path'] == path
    assert observed['candidate_sha256'] == sha256_file(path)
    assert observed['output_path'].parent == tmp_path/'runtime/research-review-drafts'
    assert observed['output_path'].name.endswith('-' + candidate['symbol'] + '.json')
    assert json.loads(capsys.readouterr().out)['status'] == 'CANCELLED'
    assert not (tmp_path/'runtime/root-review').exists()


def test_cli_noninteractive_preview_needs_no_output_and_writes_nothing(tmp_path, monkeypatch, capsys):
    path, candidate = _candidate(tmp_path)
    before = set(tmp_path.rglob('*'))
    script = Path(__file__).resolve().parents[1]/'scripts/current/review_research.py'
    module_spec = importlib.util.spec_from_file_location('review_wizard_preview_test', script)
    cli = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    monkeypatch.setattr(cli, 'draft_pending_review_response',
        lambda **kwargs: pytest.fail('Preview must not start interactive drafting'))
    monkeypatch.setattr(sys, 'argv', [str(script), '--symbol', candidate['symbol'],
        '--candidate', str(path), '--candidate-sha256', sha256_file(path), '--preview'])
    assert cli.main() == 0
    text = capsys.readouterr().out
    assert candidate['symbol'] in text
    assert '未批准' in text and '支持' in text and '反证' in text
    assert sha256_file(path) not in text
    assert set(tmp_path.rglob('*')) == before


@pytest.mark.parametrize('extra', [['--cand', 'different.json', '--preview'],
    ['--resume-incomplete'], ['--resume-incomplete', '--output', 'runtime/incomplete']])
def test_cli_rejects_abbreviated_override_or_invalid_resume(tmp_path, monkeypatch, extra):
    path, candidate = _candidate(tmp_path)
    script = Path(__file__).resolve().parents[1]/'scripts/current/review_research.py'
    module_spec = importlib.util.spec_from_file_location('review_wizard_abbrev_test', script)
    cli = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    monkeypatch.setattr(sys, 'argv', [str(script), '--symbol', candidate['symbol'],
        '--candidate', str(path), '--candidate-sha256', sha256_file(path)] + extra)
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
