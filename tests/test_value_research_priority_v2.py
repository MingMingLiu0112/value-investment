"""Evidence scheduling keeps missing quality out of deep research priority."""
from dataclasses import replace
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from test_m2_opportunity_discovery import _receipt, _financial_points, _official_payload
from value_investment_agent.application.product.value_discovery_surface import publish_value_discovery_report
from value_investment_agent.application.research.value_research_priority_v2 import build_value_research_priority_v2
from value_investment_agent.application.research.value_research_queue import build_value_research_queue


def _inputs(root, *, future=False, pending=False):
    runtime = root / "runtime"
    runtime.mkdir()
    points = [dict(p, data_point_id=str(i)) for i, p in enumerate(_financial_points())]
    if future:
        points = [dict(p, available_at="2026-10-21T00:00:00+00:00") for p in points]
    if pending:
        points = [dict(p, validation_status="pending") for p in points]
    export = runtime / "financial.json"
    export.write_text(json.dumps({"points": [], "annual_points": points}), encoding="utf-8")
    digest = lambda p: sha256(p.read_bytes()).hexdigest()
    receipt = _receipt()
    refs = []
    for ref in receipt.evidence_refs:
        if ref.id == "financial":
            refs.append(replace(ref, path="runtime/financial.json", sha256=digest(export)))
        else:
            raw = (json.dumps(_official_payload()) if ref.id == 'official' else ref.id).encode('utf-8')
            (root / ref.path).write_bytes(raw)
            refs.append(replace(ref, sha256=digest(root / ref.path)))
    receipt = replace(receipt, evidence_refs=tuple(refs))
    receipt_path = runtime / "receipt.json"
    receipt_path.write_text(json.dumps(receipt.as_policy(), ensure_ascii=False), encoding="utf-8")
    report = runtime / "report.json"
    publish_value_discovery_report(root=root, receipt_path=receipt_path,
        receipt_sha256=digest(receipt_path), output_path=report)
    return dict(root=root, report_path=report, report_sha256=digest(report),
        receipt_path=receipt_path, receipt_sha256=digest(receipt_path), budget=1,
        financial_export_path=export, financial_export_sha256=digest(export))


def test_split_replay_and_legacy_unchanged(tmp_path):
    args = _inputs(tmp_path)
    legacy_args = {k: v for k, v in args.items() if not k.startswith("financial_export")}
    before = build_value_research_queue(**legacy_args)
    result = build_value_research_priority_v2(**args)
    assert result == build_value_research_priority_v2(**args)
    assert result["deep_research_priority"][0]["symbol"] == "600001"
    assert result["deep_research_priority"][0]["quality_score"] == "100"
    assert result["evidence_enrichment_work_queue"]
    assert all(row["quality_score"] is None for row in result["evidence_enrichment_work_queue"])
    assert result["action"] == "no_order"
    assert result["new_verification_or_approval_count"] == 0
    assert before == build_value_research_queue(**legacy_args)


@pytest.mark.parametrize("option", ["future", "pending"])
def test_missing_or_unavailable_never_receives_score(tmp_path, option):
    result = build_value_research_priority_v2(**_inputs(tmp_path, **{option: True}))
    assert result["deep_research_priority"] == []
    assert all(row["quality_score"] is None for row in result["evidence_enrichment_work_queue"])


def test_hash_and_budgets(tmp_path):
    args = _inputs(tmp_path)
    with pytest.raises(ValueError, match="hash mismatch"):
        build_value_research_priority_v2(**dict(args, financial_export_sha256="0" * 64))
    with pytest.raises(ValueError, match="enrichment budget"):
        build_value_research_priority_v2(**args, enrichment_budget=True)
    result = build_value_research_priority_v2(**dict(args, budget=0), enrichment_budget=0)
    assert result["selected_deep_research_count"] == result["selected_enrichment_count"] == 0


@pytest.mark.parametrize("change", ["stale", "mixed", "debt_proxy"])
def test_invalid_annual_basis_cannot_create_deep_priority(tmp_path, change):
    args = _inputs(tmp_path)
    path = args["financial_export_path"]
    payload = json.loads(path.read_bytes())
    for p in payload["annual_points"]:
        if change == "stale" or (change == "mixed" and p["field_name"] == "cash"):
            p["period_label"] = "2024-12-31"
        if change == "debt_proxy" and p["field_name"] == "interest_bearing_debt":
            p["metadata"] = dict(p["metadata"], complete_debt_verified=False)
    path.write_text(json.dumps(payload), encoding="utf-8")
    # Supplement is separately bound; the original retained reference stays intact.
    supplement = path.with_name("supplement.json")
    supplement.write_bytes(path.read_bytes())
    path.write_text(json.dumps({"points": [], "annual_points": [dict(p, data_point_id=str(i))
        for i, p in enumerate(_financial_points())]}), encoding="utf-8")
    result = build_value_research_priority_v2(**dict(args, financial_export_path=supplement,
        financial_export_sha256=sha256(supplement.read_bytes()).hexdigest()))
    assert not result["deep_research_priority"]


def test_export_cannot_replace_retained_base_or_escape_runtime(tmp_path):
    args = _inputs(tmp_path)
    supplement = args["financial_export_path"].with_name("supplement.json")
    supplement.write_text(json.dumps({"points": [{}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="base points differ"):
        build_value_research_priority_v2(**dict(args, financial_export_path=supplement,
            financial_export_sha256=sha256(supplement.read_bytes()).hexdigest()))
    with pytest.raises(ValueError, match="inside runtime"):
        build_value_research_priority_v2(**dict(args, financial_export_path=tmp_path / "outside.json"))


def test_specialized_profile_never_uses_general_score(tmp_path, monkeypatch):
    from value_investment_agent.application.research import value_research_priority_v2 as module
    evaluate = module.evaluate_financial_quality
    monkeypatch.setattr(module, "evaluate_financial_quality",
        lambda *a, **kw: replace(evaluate(*a, **kw), model_type="bank"))
    result = module.build_value_research_priority_v2(**_inputs(tmp_path))
    assert not result["deep_research_priority"]
    assert all(not row["supported_quality_profile"] and row["quality_score"] is None
        for row in result["evidence_enrichment_work_queue"])


def test_cli_opt_in_and_legacy_default(tmp_path, monkeypatch, capsys):
    args = _inputs(tmp_path)
    path = Path(__file__).resolve().parents[1] / "scripts/current/build_value_research_queue.py"
    spec = importlib.util.spec_from_file_location("b6_queue_cli", path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    common = [str(path), "--report", str(args["report_path"]), "--report-sha256", args["report_sha256"],
        "--receipt", str(args["receipt_path"]), "--receipt-sha256", args["receipt_sha256"]]
    legacy = tmp_path / "runtime/legacy.json"
    monkeypatch.setattr(sys, "argv", common + ["--output", str(legacy)])
    assert cli.main() == 0
    assert json.loads(legacy.read_bytes())["schema_version"] == "value-research-queue-v1"
    new = tmp_path / "runtime/new.json"
    monkeypatch.setattr(sys, "argv", common + ["--output", str(new), "--priority-version", "v2",
        "--financial-export", str(args["financial_export_path"]),
        "--financial-export-sha256", args["financial_export_sha256"]])
    assert cli.main() == 0
    assert json.loads(new.read_bytes())["schema_version"] == "value-research-priority-v2"
    capsys.readouterr()
