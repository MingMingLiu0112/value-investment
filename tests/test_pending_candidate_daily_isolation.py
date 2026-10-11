"""Isolated daily integration; synthetic evidence never grants issuer approval."""
from copy import deepcopy
import json

import pytest

from test_pending_research_candidate import candidate_inputs
from value_investment_agent.application.product import daily_trade_assistant as daily
from value_investment_agent.application.product import pending_research_candidate as candidate
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.presentation import daily_trade_assistant as view


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _daily_inputs(root):
    package, policy, request = candidate_inputs(root)
    request_path = root / "config/request.json"
    _write_json(request_path, request)
    case = {
        "package": package.relative_to(root).as_posix(),
        "package_sha256": sha256_file(package),
        "schedule_request": request_path.relative_to(root).as_posix(),
        "schedule_request_sha256": sha256_file(request_path),
        "valuation_proposal_policy": policy.relative_to(root).as_posix(),
        "valuation_proposal_policy_sha256": sha256_file(policy),
        "pending_candidate_choice": "continuity",
    }
    return package, policy, request_path, request, case


def _run_daily(root, case):
    package = json.loads((root / case["package"]).read_text(encoding="utf-8"))
    return daily.run_daily_trade_assistant(
        root=root,
        symbol=package["symbol"],
        case=case,
        output_dir=root / "runtime/daily-isolation",
        agent_mode="none",
        report_renderer=view._render_report,
        supplement_renderer=view._render_supplements,
        candidate_review_renderer=view._render_pending_candidate_review,
    )


def _assert_receipt_files(root, result):
    run_dir = root / "runtime/daily-isolation"
    assert json.loads((run_dir / "receipt.json").read_text(encoding="utf-8")) == result
    for binding in result["outputs"].values():
        assert sha256_file(root / binding["path"]) == binding["sha256"]
    assert result["action"] == "no_order"
    assert result["position_guidance"] is None
    assert result["canonical_workbook_written"] is False
    assert result["preview_generated"] is False
    return run_dir


@pytest.mark.parametrize("error_type", [ValueError, OSError])
def test_candidate_failure_preserves_ordinary_daily_report_and_receipt(
    tmp_path, monkeypatch, error_type
):
    package, policy, _, _, case = _daily_inputs(tmp_path)
    before = (package.read_bytes(), policy.read_bytes(), deepcopy(case))
    observed = {}
    message = f"synthetic candidate {error_type.__name__}"

    def fail_candidate(**kwargs):
        ordinary = kwargs["output_dir"].parent / "workbench.json"
        observed["workbench_bytes"] = ordinary.read_bytes()
        observed["workbench"] = json.loads(observed["workbench_bytes"])
        assert kwargs["schedule_request_sha256"] == case["schedule_request_sha256"]
        raise error_type(message)

    monkeypatch.setattr(candidate, "prepare_pending_research_candidate", fail_candidate)
    result = _run_daily(tmp_path, case)
    run_dir = _assert_receipt_files(tmp_path, result)
    assert (run_dir / "workbench.json").read_bytes() == observed["workbench_bytes"]
    assert result["recommendation_type"] == observed["workbench"]["suggested_state"]
    assert result["research_as_of"] == "2026-09-22"
    assert result["status"] == "RESEARCH_RUN_COMPLETED_WITH_ADMISSION_STATUS"
    assert (package.read_bytes(), policy.read_bytes(), case) == before

    failure = json.loads((run_dir / "pending-candidate-error.json").read_text(encoding="utf-8"))
    assert failure["status"] == "RESEARCH_SUPPLEMENT_UNAVAILABLE"
    assert failure["error"] == message
    assert failure["action"] == "no_order"
    assert failure["decision_changed"] is False
    assert "pending_candidate_error" in result["outputs"]
    assert "pending_research_candidate" not in result["outputs"]
    assert "valuation_proposal" not in result["outputs"]
    assert not (run_dir / "pending-candidate/candidate.json").exists()
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert message in report
    assert "NO_ACTION" in report
    assert "本次失败没有改变批准或建议" in report


def test_unknown_choice_is_isolated_without_mocking_the_candidate_compiler(tmp_path):
    package, policy, _, _, case = _daily_inputs(tmp_path)
    before = (package.read_bytes(), policy.read_bytes())
    case["pending_candidate_choice"] = "not-a-registered-choice"
    result = _run_daily(tmp_path, case)
    run_dir = _assert_receipt_files(tmp_path, result)
    assert result["recommendation_type"] == "NO_ACTION"
    assert (package.read_bytes(), policy.read_bytes()) == before
    assert not (run_dir / "pending-candidate/candidate.json").exists()
    failure = json.loads((run_dir / "pending-candidate-error.json").read_text(encoding="utf-8"))
    assert "select an existing finite choice" in failure["error"]
    assert failure["decision_changed"] is False
    assert failure["error"] in (run_dir / "report.md").read_text(encoding="utf-8")


def test_daily_one_shot_reopen_is_not_reused_and_candidate_reason_is_visible(tmp_path):
    package, policy, request_path, request, case = _daily_inputs(tmp_path)
    source_path = tmp_path / "runtime/new-synthetic-evidence.md"
    source_path.write_text("Synthetic stop-reopen evidence, not an issuer filing.", encoding="utf-8")
    data = json.loads(package.read_text(encoding="utf-8"))
    new_id = "synthetic-new-reopen-evidence"
    data["sources"].append({
        "id": new_id,
        "kind": "official_issuer_filing",
        "location": source_path.relative_to(tmp_path).as_posix(),
        "local_path": source_path.relative_to(tmp_path).as_posix(),
        "sha256": sha256_file(source_path),
        "source_available_at": "2026-09-22T00:00:00+08:00",
        "availability_basis": "SYNTHETIC_TEST_ONLY",
        "issuer_identity": deepcopy(data["sources"][0]["issuer_identity"]),
    })
    _write_json(package, data)
    policy_data = json.loads(policy.read_text(encoding="utf-8"))
    policy_data["source_package_sha256"] = sha256_file(package)
    _write_json(policy, policy_data)
    request.update(
        blocker_id="synthetic-one-shot-stop",
        reopen_condition_met=True,
        new_evidence_ids=[new_id],
    )
    _write_json(request_path, request)
    stop = {
        "stop_id": "synthetic-one-shot-stop",
        "symbol": request["symbol"],
        "source_id": request["source_id"],
        "period": request["period"],
        "research_question_id": request["research_question_id"],
        "blocker_id": request["blocker_id"],
        "reviewed_evidence_ids": ["facts"],
        "reopen_condition": "A new hash-bound synthetic fact is available.",
    }
    _write_json(tmp_path / "config/research-evidence-stop-ledger-v1.json", {
        "schema_version": "research-evidence-stop-ledger-v1", "stops": [stop],
    })
    case.update(
        package_sha256=sha256_file(package),
        valuation_proposal_policy_sha256=sha256_file(policy),
        schedule_request_sha256=sha256_file(request_path),
    )
    before = (package.read_bytes(), policy.read_bytes(), request_path.read_bytes())

    result = _run_daily(tmp_path, case)
    run_dir = _assert_receipt_files(tmp_path, result)
    ordinary = json.loads((run_dir / "workbench.json").read_text(encoding="utf-8"))
    assert ordinary["schedule_gate"]["status"] == "REOPENED_WITH_NEW_EVIDENCE"
    assert ordinary["schedule_gate"]["allowed"] is True
    assert ordinary["decision_recommendation"] is not None
    assert result["recommendation_type"] == ordinary["suggested_state"] == "NO_ACTION"
    assert result["research_as_of"] == "2026-09-22"

    pending_dir = run_dir / "pending-candidate"
    pending = json.loads((pending_dir / "candidate.json").read_text(encoding="utf-8"))
    workbench = json.loads((pending_dir / "workbench.json").read_text(encoding="utf-8"))
    reason = "BLOCKED_EVIDENCE_ALREADY_CONSUMED"
    assert workbench["research_status"] == "BLOCKED_BY_RESEARCH_SCHEDULER"
    assert workbench["decision_recommendation"] is None
    assert pending["schedule_gate"] == workbench["schedule_gate"]
    assert pending["schedule_gate"]["status"] == reason
    assert pending["schedule_gate"]["allowed"] is False
    assert pending["research_blockers"] == workbench["research_blockers"] == [reason]
    assert reason in pending["decision_blockers"]
    assert pending["execution_status"] == pending["recommendation_type"] == "NOT_READY"
    assert pending["model_context_scope"] == "PREPARED_NOT_CONSUMED"
    assert pending["candidate_valuation"] is None
    assert not (pending_dir / "consumed-review.json").exists()
    assert pending["approval_changed"] is pending["research_admitted"] is pending["price_admitted"] is False
    assert pending["position_guidance"] is None
    assert reason in (run_dir / "report.md").read_text(encoding="utf-8")
    assert reason in (pending_dir / "candidate-review.md").read_text(encoding="utf-8")

    consumption_paths = list((tmp_path / "runtime/research-evidence-stop-consumptions").glob("*.json"))
    assert len(consumption_paths) == 1
    consumption = json.loads(consumption_paths[0].read_text(encoding="utf-8"))
    assert consumption["status"] == "ADMITTED_ONCE"
    assert consumption["new_evidence_ids"] == [new_id]
    assert consumption["request_sha256"] == case["schedule_request_sha256"]
    assert consumption["schedule_id"] == pending["schedule_gate"]["consumption_schedule_id"]
    assert (package.read_bytes(), policy.read_bytes(), request_path.read_bytes()) == before
