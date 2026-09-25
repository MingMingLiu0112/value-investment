from datetime import datetime, timezone
import json

import pytest

from scripts import m6_operational_control as cli
from test_m6_shadow_receipts import _fixture
from value_investment_agent.m6_operational_control import initial_state, write_control_state


def test_signed_approved_authorization_can_advance_local_state(monkeypatch, tmp_path):
    candidate, root, _, _, _, _ = _fixture()
    bundle = {
        "authorization": candidate["authorization"],
        "authorization_artifacts": candidate["authorization_artifacts"],
    }
    trust = {
        "authorization_public_key": root["authorization_public_key"],
        "approved_authorization_sha256": root["approved_authorization_sha256"],
    }
    bundle_path = tmp_path / "bundle.json"
    root_path = tmp_path / "root.json"
    state_path = tmp_path / "state.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    root_path.write_text(json.dumps(trust), encoding="utf-8")
    write_control_state(state_path, initial_state(
        operator_id="operator",
        now=datetime(2026, 9, 23, 7, tzinfo=timezone.utc),
    ))
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls.fromisoformat("2026-09-24T07:00:00+00:00")
            return value.astimezone(tz) if tz else value
    monkeypatch.setattr(cli, "datetime", FixedDatetime)
    assert cli.main([
        "--state", str(state_path), "advance", "--target", "STAGING",
        "--authorization-bundle", str(bundle_path),
        "--authorization-trust-root", str(root_path),
        "--reason", "approved staging preparation", "--operator", "operator",
    ]) == 0
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "STAGING"
    assert payload["authorization_id"] == "synthetic-only"
    assert payload["permissions"]["publish_allowed"] is False


def test_rehashed_but_unapproved_authorization_cannot_advance(monkeypatch, tmp_path):
    candidate, root, _, _, _, _ = _fixture()
    bundle = {
        "authorization": candidate["authorization"],
        "authorization_artifacts": candidate["authorization_artifacts"],
    }
    bundle["authorization"]["payload"]["authorization_id"] = "self-declared"
    trust = {
        "authorization_public_key": root["authorization_public_key"],
        "approved_authorization_sha256": root["approved_authorization_sha256"],
    }
    bundle_path = tmp_path / "bundle.json"
    root_path = tmp_path / "root.json"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    root_path.write_text(json.dumps(trust), encoding="utf-8")
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(2026, 9, 24, 7, tzinfo=timezone.utc)
            return value.astimezone(tz) if tz else value
    monkeypatch.setattr(cli, "datetime", FixedDatetime)
    with pytest.raises(ValueError):
        cli.main([
            "--state", str(tmp_path / "state.json"), "advance", "--target", "STAGING",
            "--authorization-bundle", str(bundle_path),
            "--authorization-trust-root", str(root_path),
            "--reason", "unapproved", "--operator", "operator",
        ])
