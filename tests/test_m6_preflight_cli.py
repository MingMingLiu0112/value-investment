from __future__ import annotations

import json

import pytest

from scripts import audit_m6_preflight as cli


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_cli_forwards_operational_admission_inputs(tmp_path, monkeypatch):
    bundle_path = _write_json(tmp_path / "bundle.json", {"candidate_bundle": {}, "admission": {}})
    trust_path = _write_json(tmp_path / "trust.json", {"admission_public_key": "0" * 64})
    event_path = _write_json(tmp_path / "events.json", [{
        "candidate_evidence": {},
        "event_admission": {},
        "approved_event_admission_sha256": "1" * 64,
    }])
    calendar_path = _write_json(tmp_path / "calendar.json", {"venue": "SSE"})
    captured = {}

    def fake_build(root, config, **kwargs):
        captured.update(kwargs)
        return {"action": "no_order"}

    monkeypatch.setattr(cli, "build_preflight_receipt", fake_build)
    monkeypatch.setattr(cli, "write_receipt", lambda receipt, *, root: {
        "receipt_path": "receipt.json", "pointer_path": "pointer.json",
        "receipt_sha256": "2" * 64,
    })

    result = cli.main([
        "--root", str(tmp_path),
        "--config", str(tmp_path / "config.json"),
        "--calendar-evidence", str(calendar_path),
        "--verify-live-calendar",
        "--operational-shadow-bundle", str(bundle_path),
        "--operational-shadow-trust-root", str(trust_path),
        "--operational-event-evidence", str(event_path),
        "--json-only",
    ])

    assert result == 0
    assert captured["operational_shadow_bundle"]["admission"] == {}
    assert captured["operational_shadow_trust_root"]["admission_public_key"] == "0" * 64
    assert captured["operational_event_evidence"][0]["approved_event_admission_sha256"] == "1" * 64


def test_cli_rejects_operational_bundle_without_pinned_trust_root(tmp_path, monkeypatch):
    bundle_path = _write_json(tmp_path / "bundle.json", {"candidate_bundle": {}, "admission": {}})
    calendar_path = _write_json(tmp_path / "calendar.json", {"venue": "SSE"})
    monkeypatch.setattr(cli, "build_preflight_receipt", lambda *_, **__: pytest.fail(
        "preflight must not run with a bundle-only operational input"))

    with pytest.raises(SystemExit) as error:
        cli.main([
            "--root", str(tmp_path),
            "--config", str(tmp_path / "config.json"),
            "--calendar-evidence", str(calendar_path),
            "--verify-live-calendar",
            "--operational-shadow-bundle", str(bundle_path),
        ])

    assert error.value.code == 2


@pytest.mark.parametrize('arguments', [
    ['--daily-input', 'input.json'],
    ['--daily-operational-inputs', 'ops.json'],
    ['--daily-operational-inputs', 'ops.json', '--daily-operational-inputs-sha256', 'a' * 64],
])
def test_cli_rejects_unpaired_daily_inputs_before_preflight(monkeypatch, arguments):
    monkeypatch.setattr(cli, 'build_preflight_receipt', lambda *a, **k: pytest.fail('must reject input first'))
    with pytest.raises(SystemExit) as error:
        cli.main(arguments)
    assert error.value.code == 2


def test_formal_preflight_cli_consumes_real_daily_manifest_without_promoting_it(tmp_path, monkeypatch, capsys):
    import hashlib
    from datetime import datetime, timezone, timedelta
    from value_investment_agent.operations import daily_preflight
    now = datetime.now(timezone(timedelta(hours=8)))
    decision = _write_json(tmp_path / 'decision.json', dict(action='no_order', orders=[],
        broker_called=False, run_id='synthetic-only', session_date=now.date().isoformat(),
        generated_at=now.isoformat(), suggested_state='NOT_READY'))
    manifest = _write_json(tmp_path / 'daily.json', dict(schema_version='shadow-daily-input-v1',
        action='no_order', symbols=['600887'], session_date=now.date().isoformat(),
        generated_at=now.isoformat(), bindings=dict(decision=dict(path=decision.name,
            sha256=hashlib.sha256(decision.read_bytes()).hexdigest(), observed_at=now.isoformat()))))
    def existing(*args, **kwargs):
        return dict(action='no_order', engineering_status='DONE', operational_acceptance_status='NOT_STARTED',
            summary=dict(done=[], partial=[], requires_authorization=[], blockers=['UNCHANGED_M6_GATE']))
    monkeypatch.setattr(daily_preflight, 'build_existing_preflight', existing)
    recorded = []
    monkeypatch.setattr(cli, 'write_receipt', lambda receipt, **kwargs:
        recorded.append(receipt) or dict(receipt_path='test-only', receipt_sha256='test-only'))
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert cli.main(['--root', str(tmp_path), '--daily-input', str(manifest),
        '--daily-input-sha256', digest, '--json-only']) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt == recorded[0]
    consumed = receipt['daily_input_consumption']
    assert consumed['daily_consumer_status'] == 'NOT_ADMITTED'
    assert consumed['verified_real_session_count'] == 0
    assert consumed['audit']['binding_hashes']['decision'] == hashlib.sha256(decision.read_bytes()).hexdigest()
    assert 'EXISTING_OPERATIONAL_ADMISSION_REQUIRED' in receipt['summary']['blockers']
    assert 'UNCHANGED_M6_GATE' in receipt['summary']['blockers']
    assert receipt['operational_acceptance_status'] == 'NOT_STARTED'
    assert receipt['daily_input_manifest_sha256'] == digest
    assert receipt['action'] == 'no_order'
    before = len(recorded)
    decision.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='artifact hash mismatch'):
        cli.main(['--root', str(tmp_path), '--daily-input', str(manifest),
            '--daily-input-sha256', digest, '--json-only'])
    assert len(recorded) == before
