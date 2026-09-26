from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from value_investment_agent.domain.portfolio.confirmation_receipt import (
    portfolio_confirmation_receipt_from_payload,
)
from value_investment_agent.presentation.read_models.product_workbench import (
    product_workbench_from_payload,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "current" / "rehearse_m4_onboarding.py"
EXPECTED_STAGES = {
    "init",
    "validate",
    "encrypt",
    "verify",
    "dual_snapshot_reconciliation",
    "confirmation_receipt",
    "portfolio_risk",
    "position_guidance",
    "dividend_projection",
    "product_read_model",
    "m7_candidate_material",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(runtime_root: Path, run_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--runtime-root",
            str(runtime_root),
            "--run-id",
            run_id,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_synthetic_onboarding_rehearsal_is_complete_and_cannot_claim_acceptance(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    completed = _run(runtime_root, "focused-test")

    assert completed.returncode == 0, completed.stderr
    command_receipt = json.loads(completed.stdout)
    output = Path(command_receipt["output_dir"])
    receipt_path = output / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    assert command_receipt["receipt_sha256"] == _sha256(receipt_path)
    assert command_receipt["action"] == "no_order"
    assert receipt["classification"] == "SYNTHETIC_REHEARSAL_ONLY"
    assert receipt["action"] == "no_order"
    assert receipt["M4_PERSONALIZED_ACCEPTANCE"] == "WAITING_R2"
    assert receipt["synthetic_success_is_not_real_acceptance"] is True
    assert receipt["real_private_inputs_used"] is False
    assert receipt["production_evidence_created"] is False
    assert receipt["M7_USER_ACCEPTANCE"] == "NOT_PASSED"
    assert receipt["INITIAL_ASSISTED_USE"] == "NOT_REACHED"
    assert receipt["M6_OPERATIONAL"] == "NOT_STARTED"
    assert receipt["all_requested_stages_exercised"] is True
    assert set(receipt["requested_chain"]) == EXPECTED_STAGES
    assert set(receipt["chain_stages"]) == EXPECTED_STAGES
    assert all(
        stage["status"] == "EXERCISED"
        and stage["classification"] == "SYNTHETIC_REHEARSAL_ONLY"
        for stage in receipt["chain_stages"].values()
    )

    for artifact in receipt["artifacts"].values():
        path = output / artifact["path"]
        assert path.is_file()
        assert _sha256(path) == artifact["sha256"]

    sidecar = json.loads(
        (output / "receipt.sha256.json").read_text(encoding="utf-8")
    )
    assert sidecar == {
        "schema_version": "file-sha256-v1",
        "path": "receipt.json",
        "sha256": command_receipt["receipt_sha256"],
    }
    assert list(output.glob("*.viportfolio")) == []


def test_confirmation_and_product_model_replay_with_simulated_boundary(
    tmp_path: Path,
) -> None:
    completed = _run(tmp_path / "runtime", "replay-test")
    assert completed.returncode == 0, completed.stderr
    output = Path(json.loads(completed.stdout)["output_dir"])

    reconciliation_path = output / "06_dual_snapshot_reconciliation.json"
    confirmation_record = json.loads(
        (output / "07_confirmation_receipt.json").read_text(encoding="utf-8")
    )
    confirmation = portfolio_confirmation_receipt_from_payload(
        confirmation_record["private_receipt"]
    )
    assert confirmation.action == "no_order"
    assert confirmation.reconciliation_sha256 == _sha256(reconciliation_path)
    assert confirmation.account_scope == "SYNTHETIC_M4_REHEARSAL_ONLY"
    assert confirmation_record["synthetic_human_confirmation_rehearsal_only"] is True

    for name in (
        "09_portfolio_risk.json",
        "10_position_guidance.json",
        "11_dividend_projection.json",
    ):
        envelope = json.loads((output / name).read_text(encoding="utf-8"))
        assert envelope["classification"] == "SYNTHETIC_REHEARSAL_ONLY"
        assert envelope["assessment"]["assessment_namespace"] == "SIMULATED"
        assert envelope["assessment"]["action"] == "no_order"

    product_payload = json.loads(
        (output / "12_product_workbench_payload.json").read_text(encoding="utf-8")
    )
    model = product_workbench_from_payload(product_payload)
    stage_by_key = {stage.stage_key: stage for stage in model.stage_summaries}
    assert stage_by_key["m4"].status.code == "ENGINEERING_DONE_SIMULATED"
    assert "M4_PERSONALIZED_ACCEPTANCE=WAITING_R2" in stage_by_key["m4"].detail
    assert model.portfolio.real_data_available is False
    assert model.portfolio.status.code == "SIMULATED_ONLY"
    assert model.portfolio.summary == ()
    assert model.portfolio.positions == ()
    assert model.action == "no_order"

    m7_material = json.loads(
        (output / "13_m7_candidate_material.json").read_text(encoding="utf-8")
    )
    assert m7_material["M4_PERSONALIZED_ACCEPTANCE"] == "WAITING_R2"
    assert m7_material["synthetic_success_is_not_real_acceptance"] is True
    assert m7_material["product_payload_sha256"] == _sha256(
        output / "12_product_workbench_payload.json"
    )
