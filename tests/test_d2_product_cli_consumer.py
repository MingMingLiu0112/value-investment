"""Exercise the existing candidate CLI's typed-snapshot/current-decision boundary."""
from dataclasses import asdict
import hashlib
import json
import sys

import pytest

from scripts.current import build_product_workbench_candidate as cli
from test_current_decision_surface import decision_workbench
from test_decision_recommendation import SYMBOL
from test_product_workbench_excel import _payload
from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload


def test_cli_refreshes_presentation_clock_and_registers_replayed_decision(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    base_payload = _payload()
    base_payload["as_of"] = "2026-09-21"
    base_payload["generated_at"] = "2026-09-21T13:00:00+00:00"
    baseline = asdict(product_workbench_from_payload(base_payload))
    base = runtime / "base-snapshot.json"
    base.write_text(json.dumps(baseline, default=lambda value: value.isoformat()), encoding="utf-8")
    workbench = runtime / "workbench.json"
    workbench.write_text(json.dumps(decision_workbench(missing_approval=True)), encoding="utf-8")
    output = runtime / "projection.json"
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "candidate", "--historical-preview", "--read-model-only",
        "--base-payload", str(base), "--base-read-model-snapshot",
        "--base-payload-sha256", hashlib.sha256(base.read_bytes()).hexdigest(),
        "--presentation-as-of", "2026-09-22", "--generated-at", "2026-09-22T13:00:00+00:00",
        "--decision-workbench", str(workbench), hashlib.sha256(workbench.read_bytes()).hexdigest(),
        "--register-decision-company", "--output", str(output),
    ])
    assert cli.main() == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    snapshot = result["snapshot"]
    assert snapshot["as_of"] == "2026-09-22"
    assert snapshot["generated_at"] == "2026-09-22T13:00:00+00:00"
    assert snapshot["companies"][0] == json.loads(json.dumps(baseline["companies"][0], default=str))
    assert snapshot["companies"][-1]["symbol"] == SYMBOL
    assert snapshot["companies"][-1]["decision_process"][-1]["status"] == "BLOCKED"
    assert result["decision_workbench_binding"]["sha256"] == hashlib.sha256(workbench.read_bytes()).hexdigest()
    assert result["canonical_written"] is False
    assert result["action"] == "no_order"


def test_registration_flag_requires_source_before_writing_output(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["candidate", "--output", "runtime/out.json", "--register-decision-company"])
    with pytest.raises(ValueError, match="pinned decision workbench"):
        cli.main()
    assert not (tmp_path / "runtime/out.json").exists()


@pytest.mark.parametrize("presentation_date, admitted", [("2026-09-22", True), ("2026-09-23", False)])
def test_display_date_uses_exchange_timezone_at_shanghai_midnight(tmp_path, monkeypatch, presentation_date, admitted):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    payload = _payload()
    payload["as_of"] = "2026-09-21"
    base = runtime / "base.json"
    base.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", [
        "candidate", "--historical-preview", "--read-model-only", "--base-payload", str(base),
        "--base-payload-sha256", hashlib.sha256(base.read_bytes()).hexdigest(),
        "--presentation-as-of", presentation_date, "--generated-at", "2026-09-21T16:30:00+00:00",
        "--output", "runtime/out.json",
    ])
    if admitted:
        assert cli.main() == 0
        assert json.loads((runtime / "out.json").read_text(encoding="utf-8"))["snapshot"]["as_of"] == presentation_date
    else:
        with pytest.raises(ValueError, match="generation date"):
            cli.main()
        assert not (runtime / "out.json").exists()
