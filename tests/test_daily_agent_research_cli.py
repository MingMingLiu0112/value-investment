"""Thin CLI integration over real snapshot/source verifiers and the Mock pilot."""
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from test_daily_agent_research import setup, financial_setup
from test_llm_agent_research import _replies
from value_investment_agent.application.product.common import sha256_file


@pytest.fixture
def cli(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/current/run_agent_research_pilot.py"
    spec = importlib.util.spec_from_file_location("daily_agent_cli_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("Mock/legacy offline CLI attempted a live provider")

    monkeypatch.setattr(module, "OpenAICompatibleChatProvider", forbidden)
    monkeypatch.setattr("value_investment_agent.infrastructure.agent_runtime.provider.build_opener", forbidden)
    return module


def inputs(args, workflow):
    argv = ["pilot", "--symbol", args["symbol"], "--workbench", str(args["workbench"]),
            "--workbench-sha256", args["workbench_sha256"], "--output", str(args["output"]),
            "--mode", "mock"]
    if workflow != "legacy":
        argv += ["--workflow", workflow]
        path = args["root"] / "runtime/excerpt-requests.json"
        path.write_text(json.dumps(dict(schema_version="agent-excerpt-requests-v1",
            action="no_order", symbol=args["symbol"],
            requests=[asdict(item) for item in args["source_requests"]])), encoding="utf-8")
        argv += ["--source-requests", str(path), "--source-requests-sha256", sha256_file(path)]
    if workflow in {"event", "legacy"}:
        path = args["root"] / "runtime/mock-responses.json"
        path.write_text(json.dumps({key: json.loads(value) for key, value in args["responses"].items()}),
                        encoding="utf-8")
        argv += ["--mock-responses", str(path), "--mock-responses-sha256", sha256_file(path)]
    else:
        for key in ("transcription", "metric_workbench"):
            if args.get(key) is not None:
                flag = key.replace("_", "-")
                argv += ["--" + flag, str(args[key]), "--" + flag + "-sha256", args[key + "_sha256"]]
    return argv


def invoke(cli, argv, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", argv)
    code = cli.main()
    return code, json.loads(capsys.readouterr().out)


def batch_inputs(args):
    argv = inputs(args, "event")
    flags = dict(zip(argv[1::2], argv[2::2]))
    event = {"symbol": args["symbol"], "workflow": "event",
             "output": str(args["output"].relative_to(args["root"]))}
    for key in ("workbench", "source_requests", "mock_responses"):
        flag = "--" + key.replace("_", "-")
        event[key] = {"path": flags[flag], "sha256": flags[flag + "-sha256"]}
    financial = {key: value for key, value in event.items() if key != "mock_responses"}
    financial.update(workflow="financial", output="runtime/daily-agent/financial.json")
    return event, financial


def test_batch_real_verifiers_isolate_missing_financial_and_reuse_event(cli, tmp_path, monkeypatch, capsys):
    args = setup(tmp_path)
    event, financial = batch_inputs(args)
    plan = tmp_path / "runtime/batch.json"
    plan.write_text(json.dumps(dict(schema_version="daily-agent-mock-batch-v1",
        action="no_order", mode="MOCK", jobs=[financial, event])), encoding="utf-8")
    argv = ["pilot", "--mode", "mock", "--batch-plan", str(plan),
            "--batch-plan-sha256", sha256_file(plan)]
    code, result = invoke(cli, argv, monkeypatch, capsys)
    assert code == 3 and result["status"] == "PARTIAL"
    assert [item["status"] for item in result["items"]] == ["BLOCKED_INPUT", "DRAFT_READY"]
    assert result["registered_or_published"] is False and result["approval_count"] == 0
    before = args["output"].read_bytes(), args["output"].stat().st_mtime_ns
    assert invoke(cli, argv, monkeypatch, capsys) == (code, result)
    assert before == (args["output"].read_bytes(), args["output"].stat().st_mtime_ns)


@pytest.mark.parametrize("bad_output", ["config/current-agent-research.json", "../outside.json"])
def test_batch_prevalidates_all_outputs_before_any_write(cli, tmp_path, monkeypatch, capsys, bad_output):
    args = setup(tmp_path)
    event, financial = batch_inputs(args)
    financial["output"] = bad_output
    plan = tmp_path / "runtime/batch.json"
    plan.write_text(json.dumps(dict(schema_version="daily-agent-mock-batch-v1",
        action="no_order", mode="MOCK", jobs=[event, financial])), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["pilot", "--mode", "mock", "--batch-plan", str(plan),
                                    "--batch-plan-sha256", sha256_file(plan)])
    with pytest.raises(ValueError):
        cli.main()
    assert not args["output"].exists()


def test_batch_bad_job_pin_does_not_block_other_workflow(cli, tmp_path, monkeypatch, capsys):
    args = setup(tmp_path)
    event, financial = batch_inputs(args)
    financial["workbench"] = dict(event["workbench"], sha256="0" * 64)
    plan = tmp_path / "runtime/batch.json"
    plan.write_text(json.dumps(dict(schema_version="daily-agent-mock-batch-v1",
        action="no_order", mode="MOCK", jobs=[financial, event])), encoding="utf-8")
    code, result = invoke(cli, ["pilot", "--mode", "mock", "--batch-plan", str(plan),
        "--batch-plan-sha256", sha256_file(plan)], monkeypatch, capsys)
    assert code == 3
    assert [row["status"] for row in result["items"]] == ["FAILED", "DRAFT_READY"]
    assert result["items"][0]["error_type"] == "ValueError"


def test_cli_explicit_batch_display_registration_uses_web_verifier(cli, tmp_path, monkeypatch, capsys):
    from datetime import datetime, timezone
    from value_investment_agent.application.research.agent_review.web_research import read_web_agent_research

    args = setup(tmp_path)
    event, _ = batch_inputs(args)
    plan = tmp_path / "runtime/batch.json"
    plan.write_text(json.dumps(dict(schema_version="daily-agent-mock-batch-v1",
        action="no_order", mode="MOCK", jobs=[event])), encoding="utf-8")
    code, result = invoke(cli, ["pilot", "--mode", "mock", "--batch-plan", str(plan),
        "--batch-plan-sha256", sha256_file(plan), "--register-drafts"], monkeypatch, capsys)
    assert code == 0 and result["display_registration"]["status"] == "UPDATED"
    assert result["registration_scope"] == "DISPLAY_ONLY_NOT_RESEARCH_APPROVAL"
    view = read_web_agent_research(tmp_path, symbol=args["symbol"], workflow="event",
                                   now=datetime.now(timezone.utc))
    assert view["status"] == "VERIFIED"
    assert view["approval_count"] == 0 and view["admitted"] is False


@pytest.mark.parametrize("workflow", ["event", "financial"])
def test_daily_cli_verified_drafts_reuse_without_public_or_private_writes(
        cli, tmp_path, monkeypatch, capsys, workflow):
    args = (financial_setup if workflow == "financial" else setup)(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    registry = config / "current-agent-research.json"
    registry.write_bytes(b"registry sentinel")
    journal = tmp_path / "runtime/private.jsonl"
    journal.write_bytes(b"private sentinel")
    argv = inputs(args, workflow)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    code, result = invoke(cli, argv, monkeypatch, capsys)
    assert code == 0 and result["packet"] and result["mode"] == "MOCK"
    assert result["formal_fact_count"] == result["approval_count"] == 0
    assert result["decision_changed"] is False and result["action"] == "no_order"
    assert len(result["findings"]) == 3
    assert all(item["status"] == "PENDING_HUMAN_REVIEW" for item in result["findings"])
    if workflow == "financial":
        assert result["economic_comparability_approved"] is False
        assert result["period_checks"][0]["prior_period"] == "2024"
    stamp = args["output"].stat().st_mtime_ns
    assert invoke(cli, argv, monkeypatch, capsys) == (0, result)
    assert args["output"].stat().st_mtime_ns == stamp
    assert all(path.read_bytes() == value for path, value in before.items())
    assert {path for path in tmp_path.rglob("*") if path.is_file()} - before.keys() == {args["output"]}


@pytest.mark.parametrize("workflow", ["event", "financial"])
def test_daily_cli_missing_prerequisites_returns_gap_without_packet(cli, tmp_path, monkeypatch, capsys, workflow):
    args = setup(tmp_path)
    if workflow == "financial":
        args.pop("responses")
    args["source_requests"] = ()
    code, result = invoke(cli, inputs(args, workflow), monkeypatch, capsys)
    assert code == 2 and not result.get("packet") and not args["output"].exists()
    key = "financial_report" if workflow == "financial" else "announcement_event"
    assert result["workflows"][key].startswith("BLOCKED_")


@pytest.mark.parametrize("extra", [
    ["--mode", "live"], ["--mode", "offline"], ["--authorize-paid-api"],
    ["--provider-config", "secret.json"], ["--provider-config-sha256", "a" * 64],
    ["--transcription", "row.json"],
])
def test_daily_cli_rejects_invalid_mode_provider_or_unpaired_inputs(cli, tmp_path, monkeypatch, extra):
    argv = inputs(setup(tmp_path), "event") + extra
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert not (tmp_path / "runtime/daily-agent/packet.json").exists()


def test_cli_changed_response_rejects_occupied_output_without_overwrite(cli, tmp_path, monkeypatch, capsys):
    args = setup(tmp_path)
    invoke(cli, inputs(args, "event"), monkeypatch, capsys)
    original = args["output"].read_bytes()
    args["responses"] = _replies("Changed research question")
    monkeypatch.setattr(sys, "argv", inputs(args, "event"))
    with pytest.raises(FileExistsError, match="different provider input"):
        cli.main()
    assert args["output"].read_bytes() == original


def test_cli_cross_workflow_cannot_reuse_same_output(cli, tmp_path, monkeypatch, capsys):
    args = financial_setup(tmp_path)
    replies = {key: json.loads(value) for key, value in _replies().items()}
    for value in replies.values():
        value["findings"][0]["supporting_evidence_refs"] = [args["source_requests"][0].source_id]
    args["responses"] = {key: json.dumps(value) for key, value in replies.items()}
    invoke(cli, inputs(args, "event"), monkeypatch, capsys)
    original = args["output"].read_bytes()
    monkeypatch.setattr(sys, "argv", inputs(args, "financial"))
    with pytest.raises(FileExistsError, match="different provider input"):
        cli.main()
    assert args["output"].read_bytes() == original


def test_cli_financial_separate_metric_workbench_binding(cli, tmp_path, monkeypatch, capsys):
    args = financial_setup(tmp_path)
    path = tmp_path / "runtime/metric-workbench.json"
    path.write_bytes(args["workbench"].read_bytes())
    args.update(metric_workbench=path, metric_workbench_sha256=sha256_file(path))
    code, result = invoke(cli, inputs(args, "financial"), monkeypatch, capsys)
    assert code == 0
    assert result["workflow_binding"]["metric_workbench"] == {
        "path": "runtime/metric-workbench.json", "sha256": sha256_file(path)}


@pytest.mark.parametrize("fault", ["hash", "identity", "outside_root"])
def test_cli_rejects_bad_excerpt_binding(cli, tmp_path, monkeypatch, fault):
    args = setup(tmp_path)
    argv = inputs(args, "event")
    path = Path(argv[argv.index("--source-requests") + 1])
    if fault == "hash":
        path.write_text("{}", encoding="utf-8")
    elif fault == "identity":
        value = json.loads(path.read_text(encoding="utf-8"))
        value["symbol"] = "000333"
        path.write_text(json.dumps(value), encoding="utf-8")
        argv[argv.index("--source-requests-sha256") + 1] = sha256_file(path)
    else:
        argv[argv.index("--source-requests") + 1] = str(tmp_path.parent / "outside.json")
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(ValueError):
        cli.main()
    assert not args["output"].exists()


@pytest.mark.parametrize("mode", ["offline", "mock"])
def test_cli_default_legacy_output_contract_is_preserved(cli, tmp_path, monkeypatch, capsys, mode):
    args = setup(tmp_path)
    argv = inputs(args, "legacy") + ["--mode", mode]
    code, result = invoke(cli, argv, monkeypatch, capsys)
    assert code == 0
    assert set(result) == {"scope", "symbol", "finding_count", "output", "output_sha256", "action"}
    assert result["finding_count"] == 3 and result["output_sha256"] == sha256_file(args["output"])
