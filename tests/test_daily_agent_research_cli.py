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
