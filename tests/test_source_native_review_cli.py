"""Opt-in CLI uses actual native verification; only TEST_ONLY fixtures are signed."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

import pytest

from test_source_native_signed_review_v2 import native_signed, synthetic_native, consume_args
from value_investment_agent.application.product import source_native_signed_review_v2 as native
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.decision_surface import verify_current_decision_workbench
from value_investment_agent.operations.authorization.trust_root_registry import _use_test_trust_registry

CODE = Path(__file__).resolve().parents[1]
SCRIPT = CODE/'scripts/current/review_research.py'


def cli_for(root, monkeypatch):
    spec = importlib.util.spec_from_file_location('native_review_cli_test', SCRIPT)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    # Only the filesystem root / process argv harness changes. No validator,
    # signature, service, provenance, gate or result is substituted.
    monkeypatch.setattr(cli, 'ROOT', root)
    return cli


def argv_for(f, extra=(), *, opt_in=True):
    return [str(SCRIPT), '--symbol', f['candidate']['symbol'],
        '--candidate', str(f['path']), '--candidate-sha256', f['ref']['sha256'],
        *(['--native-research-only'] if opt_in else []), *map(str, extra)]


def signature_flags(args):
    return [flag for pair in (
        ('--signed-review-response', args['response_path']),
        ('--signed-review-response-sha256', args['response_sha256']),
        ('--review-trust-root', args['trust_root_path']),
        ('--review-trust-root-sha256', args['trust_root_sha256']),
        ('--output', args['output_dir'])) for flag in map(str, pair)]


def snapshot(root):
    return {p.relative_to(root).as_posix(): sha256_file(p) for p in root.rglob('*') if p.is_file()}


def test_native_preview_and_immutable_unsigned_draft(native_signed, monkeypatch, capsys):
    f = native_signed
    cli = cli_for(f['root'], monkeypatch)
    before = snapshot(f['root'])
    monkeypatch.setattr(sys, 'argv', argv_for(f, ['--preview']))
    assert cli.main() == 0
    template = json.loads(capsys.readouterr().out)
    assert template['schema_version'] == native.SCHEMA
    assert template['action'] == 'no_order'
    assert len(template['groups']) == 5
    assert all(template[key] is None for key in ('reviewer_id', 'reviewed_at',
        'whole_model_approval', 'sequence', 'previous_response_binding', 'trust_root_binding'))
    assert snapshot(f['root']) == before
    output = f['root']/'runtime/source-native-review-drafts-v2/TEST_ONLY-draft.json'
    monkeypatch.setattr(sys, 'argv', argv_for(f, ['--output', output]))
    assert cli.main() == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt['scope'] == 'UNSIGNED_NOT_APPROVED'
    assert json.loads(output.read_bytes()) == template
    assert sha256_file(output) == receipt['draft_binding']['sha256']
    preserved = output.read_bytes()
    with pytest.raises(SystemExit) as failure: cli.main()
    assert failure.value.code == 2
    assert output.read_bytes() == preserved
    assert not (f['root']/native.NAMESPACE).exists()


def test_native_cli_user_signature_to_saved_workbench_and_cold_readback(native_signed, monkeypatch, capsys):
    f = native_signed
    args = consume_args(f)
    cli = cli_for(f['root'], monkeypatch)
    before = snapshot(f['root'])
    monkeypatch.setattr(sys, 'argv', argv_for(f, signature_flags(args)))
    with _use_test_trust_registry(f['registry']):
        assert cli.main() == 0
        output = json.loads(capsys.readouterr().out)
        assert output['schema_version'] == 'source-native-reviewed-readback-v2'
        assert output['scope'] == 'RESEARCH_ONLY'
        assert output['verification_scope'] == 'PUBLICATION_TIME_REPLAY_ONLY_REVERIFY_BEFORE_USE'
        for key in ('price_admitted', 'formal_eligibility', 'strategy_approved',
                    'registered_current_case_changed', 'canonical_written'):
            assert output[key] is False
        readback = f['root']/output['readback_binding']['path']
        assert sha256_file(readback) == output['readback_binding']['sha256']
        saved = json.loads(readback.read_bytes())
        wb_path = f['root']/saved['workbench_binding']['path']
        assert sha256_file(wb_path) == saved['workbench_binding']['sha256']
        wb = json.loads(wb_path.read_bytes())
        restored = verify_current_decision_workbench(wb,
            human_approval_provenance_verifier=lambda a: native.verify_native_human_approval_provenance(f['root'], a))
        assert restored.dependency_objects['human_approval'].verified_transport is not None
        assert restored.dependency_objects['human_approval'].price_assessment_eligible is False
        assert restored.recommendation.action == 'no_order'
        assert wb['valuation'] == f['candidate']['candidate_valuation']
        assert wb['price_bridge']['current_price'] is None
        after = snapshot(f['root'])
        assert all(after[path] == digest for path, digest in before.items())
        assert all(path.startswith((native.NAMESPACE+'/', native.CONSUMPTIONS+'/'))
            for path in after.keys()-before.keys())
        assert not (f['root']/'runtime/research-review-responses').exists()
        with pytest.raises(SystemExit) as failure: cli.main()
        assert failure.value.code == 2
        assert snapshot(f['root']) == after


@pytest.mark.parametrize('extra', [
    ['--resume-incomplete'], ['--incomplete-consumption-sha256', '0'*64],
    ['--previous-review-response', 'old.json'], ['--previous-review-response-sha256', '0'*64],
    ['--verify-economics'], ['--prepare-bound-draft'],
    ['--preview', '--output', 'runtime/not-written.json'],
    ['--preview', '--signed-review-response', 'supplied.json'],
    ['--preview', '--review-trust-root', 'trust.json'],
    ['--preview', '--signed-review-response-sha256', '0'*64],
    ['--signed-review-response', 'supplied.json', '--output', 'runtime/not-written'], [],
    ['--output', 'runtime/outside-native-drafts.json'],
])
def test_native_cli_rejects_incompatible_or_incomplete_flags(native_signed, monkeypatch, extra):
    f = native_signed
    cli = cli_for(f['root'], monkeypatch)
    before = snapshot(f['root'])
    monkeypatch.setattr(sys, 'argv', argv_for(f, extra))
    with pytest.raises(SystemExit) as failure: cli.main()
    assert failure.value.code == 2
    assert snapshot(f['root']) == before


@pytest.mark.parametrize('damage', ['untrusted', 'purpose', 'hash', 'issuer', 'group', 'v1_candidate'])
def test_native_cli_signature_or_candidate_failure_never_falls_back(native_signed, monkeypatch, damage):
    f = native_signed
    if damage == 'group': f['response']['groups'][0]['response'] = 'INSUFFICIENT'
    args = consume_args(f, purpose=b'v1-wrong-purpose' if damage == 'purpose' else native.PURPOSE)
    cli = cli_for(f['root'], monkeypatch)
    flags = argv_for(f, signature_flags(args))
    if damage == 'hash': flags[flags.index('--candidate-sha256')+1] = '0'*64
    if damage == 'issuer': flags[flags.index('--symbol')+1] = '000001'
    if damage == 'v1_candidate':
        path = f['root']/'runtime/pending/candidate.json'
        flags[flags.index('--candidate')+1] = str(path)
        flags[flags.index('--candidate-sha256')+1] = sha256_file(path)
    monkeypatch.setattr(sys, 'argv', flags)
    with _use_test_trust_registry(f['root']/'absent.json' if damage == 'untrusted' else f['registry']):
        with pytest.raises(SystemExit) as failure: cli.main()
    assert failure.value.code == 2
    assert not list((f['root']/native.NAMESPACE).glob('*/*.json'))
    assert not (f['root']/'runtime/research-review-responses').exists()
    assert not args['output_dir'].exists()


@pytest.mark.parametrize('failure', ['source_after_workbench', 'readback_write'])
def test_native_cli_publication_failure_does_not_claim_success(native_signed, monkeypatch, failure, capsys):
    f = native_signed
    args = consume_args(f)
    cli = cli_for(f['root'], monkeypatch)
    write = native.write_new_json
    def interrupted(path, payload):
        if path.name == 'readback.json' and failure == 'readback_write':
            raise OSError('TEST_ONLY readback interruption')
        result = write(path, payload)
        if path.name == 'workbench.json' and failure == 'source_after_workbench':
            source = f['root']/f['package_ref']['path']
            source.write_bytes(source.read_bytes()+b'\nTEST_ONLY_DRIFT')
        return result
    # Only persistence is instrumented. Signature, model, typed service and DI run.
    monkeypatch.setattr(native, 'write_new_json', interrupted)
    monkeypatch.setattr(sys, 'argv', argv_for(f, signature_flags(args)))
    with _use_test_trust_registry(f['registry']):
        with pytest.raises(SystemExit) as error: cli.main()
    assert error.value.code == 2
    assert (args['output_dir']/'receipt.json').exists()
    assert not (args['output_dir']/'readback.json').exists()
    assert capsys.readouterr().out == ''


def test_default_v1_preview_remains_v1_and_native_requires_opt_in(native_signed, monkeypatch, capsys):
    f = native_signed
    cli = cli_for(f['root'], monkeypatch)
    before = snapshot(f['root'])
    monkeypatch.setattr(sys, 'argv', argv_for(f, ['--preview'], opt_in=False))
    with pytest.raises(ValueError): cli.main()
    assert snapshot(f['root']) == before
    path = f['root']/'runtime/pending/candidate.json'
    candidate = json.loads(path.read_bytes())
    monkeypatch.setattr(sys, 'argv', [str(SCRIPT), '--symbol', candidate['symbol'],
        '--candidate', str(path), '--candidate-sha256', sha256_file(path), '--preview'])
    assert cli.main() == 0
    text = capsys.readouterr().out
    assert candidate['symbol'] in text
    assert native.SCHEMA not in text
    assert snapshot(f['root']) == before


def test_native_draft_write_tampering_cannot_be_rehashed_as_success(native_signed, monkeypatch, capsys):
    from value_investment_agent.application.product import common
    f = native_signed
    cli = cli_for(f['root'], monkeypatch)
    output = f['root']/'runtime/source-native-review-drafts-v2/TEST_ONLY-tampered.json'
    write = common.write_new_json
    def altered(path, payload):
        write(path, payload)
        path.write_bytes(path.read_bytes()+b'\n')
    monkeypatch.setattr(common, 'write_new_json', altered)
    monkeypatch.setattr(sys, 'argv', argv_for(f, ['--output', output]))
    with pytest.raises(SystemExit) as error: cli.main()
    assert error.value.code == 2
    assert capsys.readouterr().out == ''
    assert not (f['root']/native.NAMESPACE).exists()


def test_real_js2_cli_preview_is_unsigned_and_read_only(tmp_path, monkeypatch, capsys):
    source_root = os.environ.get('SOURCE_NATIVE_REAL_ROOT')
    if not source_root:
        pytest.skip('Explicit public retained source root required; no private/network discovery')
    source = Path(source_root)
    candidate_path = 'runtime/source-native-pending/3bb7bfe05c3f4c7d9a52d34b07588087/candidate.json'
    candidate = json.loads((source/candidate_path).read_bytes())
    refs = [dict(path=candidate_path, sha256=sha256_file(source/candidate_path)), *candidate['source_bindings']]
    for ref in refs:
        target = tmp_path/ref['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/ref['path'], target)
        assert sha256_file(target) == ref['sha256']
    for name in native.IMPLEMENTATIONS:
        target = tmp_path/'src/value_investment_agent'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CODE/'src/value_investment_agent'/name, target)
    cli = cli_for(tmp_path, monkeypatch)
    f = dict(root=tmp_path, candidate=candidate, path=tmp_path/candidate_path,
        ref=dict(path=candidate_path, sha256=sha256_file(tmp_path/candidate_path)))
    before = snapshot(tmp_path)
    monkeypatch.setattr(sys, 'argv', argv_for(f, ['--preview']))
    assert cli.main() == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview['schema_version'] == native.SCHEMA
    assert preview['symbol'] == '600519'
    assert preview['reviewer_id'] is preview['whole_model_approval'] is preview['trust_root_binding'] is None
    assert preview['action'] == 'no_order'
    assert snapshot(tmp_path) == before
