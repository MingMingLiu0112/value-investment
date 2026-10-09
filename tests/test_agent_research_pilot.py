from __future__ import annotations

import ast
from datetime import date, datetime, timezone
import json
from pathlib import Path

import pytest

from value_investment_agent.application.research.agent_review import supervisor
from value_investment_agent.application.research.agent_review.snapshot import ResearchSnapshot
from value_investment_agent.application.product import agent_research_surface
from value_investment_agent.application.product.common import sha256_file


def test_agent_domain_and_research_application_have_no_io_or_presentation_imports():
    root = Path(__file__).resolve().parents[1] / "src" / "value_investment_agent"
    domain = root / "domain" / "agent_research"
    application = root / "application" / "research" / "agent_review"
    forbidden = ("requests", "httpx", "psycopg", "openpyxl", "subprocess", "langchain",
                 "langgraph", "deepagents", "presentation")
    for directory in (domain, application):
        for path in directory.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                else:
                    continue
                assert all(not any(part in module for part in forbidden) for module in modules), path


def _snapshot() -> ResearchSnapshot:
    ref = {"id": "filing-1", "available_at": "2026-10-07T12:00:00+08:00",
           "path": "runtime/source.json", "sha256": "c" * 64}
    statement = {"text": "Source-bound research question", "evidence_refs": ["filing-1"]}
    return ResearchSnapshot(
        symbol="600519", as_of=date(2026, 10, 8), input_fingerprint="a" * 64,
        workbench_sha256="b" * 64, evidence=(ref,), positives=(statement,),
        counter_evidence=(statement,), next_events=(), thesis_breakers=(statement,),
    )


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict]:
    monkeypatch.setattr(supervisor, "load_research_snapshot", lambda **_: _snapshot())
    output = tmp_path / "runtime" / "agent" / "findings.json"
    packet = supervisor.run_agent_research_pilot(
        root=tmp_path, workbench=output, workbench_sha256="b" * 64,
        symbol="600519", output=output,
    )
    return output, packet


def test_three_roles_are_pending_non_admitted_and_idempotent(tmp_path, monkeypatch):
    output, packet = _run(tmp_path, monkeypatch)
    assert [row["agent_role"] for row in packet["findings"]] == [
        "FUNDAMENTAL", "COUNTER_EVIDENCE", "EVENT",
    ]
    assert packet["action"] == "no_order"
    assert packet["formal_fact_count"] == packet["approval_count"] == 0
    assert packet["decision_changed"] is False
    assert all(row["verification_status"] == "PENDING_HUMAN_REVIEW" for row in packet["findings"])
    assert supervisor.run_agent_research_pilot(
        root=tmp_path, workbench=output, workbench_sha256="b" * 64,
        symbol="600519", output=output,
    ) == packet


def test_existing_packet_tamper_fails_closed(tmp_path, monkeypatch):
    output, packet = _run(tmp_path, monkeypatch)
    packet["findings"][0]["confidence"] = "HIGH"
    output.write_text(json.dumps(packet), encoding="utf-8")
    with pytest.raises(FileExistsError, match="identical verified replay"):
        supervisor.run_agent_research_pilot(
            root=tmp_path, workbench=output, workbench_sha256="b" * 64,
            symbol="600519", output=output,
        )


def test_product_projection_replays_full_finding_and_never_changes_decision(tmp_path, monkeypatch):
    output, packet = _run(tmp_path, monkeypatch)
    monkeypatch.setattr(agent_research_surface, "load_research_snapshot", lambda **_: _snapshot())
    payload = {
        "as_of": "2026-10-08", "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit": {"evidence": []},
        "companies": [{"symbol": "600519", "decision_status": "WAIT"}],
    }
    agent_research_surface.project_verified_agent_packet(
        payload, root=tmp_path, path=output, expected_sha256=sha256_file(output),
    )
    assert len(payload["companies"][0]["agent_research"]) == 3
    assert payload["audit"]["evidence"][0]["evidence_id"] == "filing-1"
    assert payload["companies"][0]["decision_status"] == "WAIT"
    packet["findings"][0]["source_available_at"] = "2026-10-09T12:00:00+08:00"
    output.write_text(json.dumps(packet), encoding="utf-8")
    fresh = {"as_of": "2026-10-08", "generated_at": datetime.now(timezone.utc).isoformat(),
             "audit": {"evidence": []},
             "companies": [{"symbol": "600519", "decision_status": "WAIT"}]}
    with pytest.raises(ValueError, match="verified replay"):
        agent_research_surface.project_verified_agent_packet(
            fresh, root=tmp_path, path=output, expected_sha256=sha256_file(output),
        )
    assert fresh["companies"][0]["decision_status"] == "WAIT"


def test_product_projection_rejects_conflicting_audit_source(tmp_path, monkeypatch):
    output, _ = _run(tmp_path, monkeypatch)
    monkeypatch.setattr(agent_research_surface, "load_research_snapshot", lambda **_: _snapshot())
    payload = {
        "as_of": "2026-10-08", "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit": {"evidence": [{"evidence_id": "filing-1", "path": "wrong.json",
                                "sha256": "d" * 64, "available_at": "2026-10-07",
                                "action": "no_order"}]},
        "companies": [{"symbol": "600519", "decision_status": "WAIT"}],
    }
    with pytest.raises(ValueError, match="conflicts with product evidence"):
        agent_research_surface.project_verified_agent_packet(
            payload, root=tmp_path, path=output, expected_sha256=sha256_file(output),
        )
    assert "agent_research" not in payload["companies"][0]
