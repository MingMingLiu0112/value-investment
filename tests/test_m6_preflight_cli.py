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
