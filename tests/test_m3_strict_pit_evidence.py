from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from value_investment_agent.m3_strict_pit_evidence import (
    EVIDENCE_VALID,
    FAILED,
    NOT_PROVEN,
    audit,
    load_candidate,
)
import value_investment_agent.m3_strict_pit_evidence as strict_pit_module


CLI_SPEC = importlib.util.spec_from_file_location(
    "audit_m3_strict_pit_evidence",
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "audit_m3_strict_pit_evidence.py",
)
CLI = importlib.util.module_from_spec(CLI_SPEC)
CLI_SPEC.loader.exec_module(CLI)


REPLAY_DATE = date(2024, 6, 21)
CN_TZ = timezone(__import__("datetime").timedelta(hours=8))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _replay_payload() -> dict:
    return {
        "schema_version": "m3-historical-research-replay-v1",
        "replay_id": "m3-historical-research-replay-600519-2024-06-21-v1",
        "namespace": "HISTORICAL_RESEARCH_REPLAY",
        "symbol": "600519",
        "replay_date": "2024-06-21",
        "generated_at": "2026-09-24T01:58:33+00:00",
        "source_receipt": {"input_sha256": "a" * 64},
        "then_known_facts": {
            "symbol": "600519",
            "period_label": "2023-12-31",
            "source_id": "cninfo:fixture",
            "published_at": "2024-04-03T00:00:00+08:00",
            "parent_profit_cny": "74734071550.75",
            "ending_issued_shares": "1256197800",
            "reported_basic_eps": "59.49",
            "source_ref": {
                "id": "cninfo:fixture",
                "kind": "annual_filing",
                "path": "fixtures/annual.json",
                "sha256": "a" * 64,
                "source_url": "https://example.test/annual",
                "available_at": "2024-04-03T00:00:00+08:00",
                "role": "annual filing",
            },
        },
        "then_known_filings": [],
        "then_known_quote": {
            "symbol": "600519",
            "quote_date": "2024-06-21",
            "close_cny": "1471.00",
            "source_ref": {
                "id": "prices",
                "kind": "prices",
                "path": "fixtures/prices.json",
                "sha256": "a" * 64,
                "source_url": "https://example.test/prices",
                "available_at": "2024-06-21T15:00:00+08:00",
                "role": "price file",
            },
        },
        "rule": {
            "rule_version": "contemporaneous-candidate-v1",
            "model_scope": "relative_pe_research_only",
            "registered_at": "2026-09-12T05:27:47+00:00",
            "rule_registration_status": "RETROSPECTIVE_RESEARCH_EXTENSION",
            "entry_margin": "0.30",
            "research_quantity": 100,
            "exit_rule": "close exceeds that day's median-relative value",
        },
        "source_decision_state": "proposed_entry",
        "source_decision_action": "propose_entry_review",
        "final_decision": "WAIT",
        "blockers": [],
        "valuation_approved": False,
        "trade_approved": False,
        "positive_price_review_eligible": False,
        "future_facts_used": False,
        "future_rule_version_used": True,
        "action": "no_order",
    }


def _candidate_payload(replay_payload: dict, *, available_at: str) -> dict:
    return {
        "schema_version": "m3-strict-pit-evidence-candidate-v1",
        "rule_version": replay_payload["rule"]["rule_version"],
        "replay_id": replay_payload["replay_id"],
        "replay_date": replay_payload["replay_date"],
        "evidence": [
            {
                "evidence_id": "rule-evidence-v1",
                "evidence_kind": "versioned_file",
                "path": "evidence/rule-v1.json",
                "sha256": _sha256(b'{"rule":"v1"}'),
                "source_url": "https://example.test/rule-v1.json",
                "available_at": available_at,
            }
        ],
    }


def _write_replay(tmp_path):
    replay = tmp_path / "replay.json"
    replay.write_text(json.dumps(_replay_payload()), encoding="utf-8")
    return replay


def _write_candidate(root, available_at, content=b'{"rule":"v1"}'):
    evidence = root / "evidence" / "rule-v1.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_bytes(content)
    candidate = root / "candidate.json"
    candidate.write_text(
        json.dumps(_candidate_payload(_replay_payload(), available_at=available_at)),
        encoding="utf-8",
    )
    return candidate, evidence


def test_audit_missing_candidate_is_not_proven(tmp_path):
    replay = _write_replay(tmp_path)

    receipt = audit(tmp_path, replay, None)

    assert receipt["status"] == NOT_PROVEN
    assert receipt["strict_contemporaneous_rule_pit"] == NOT_PROVEN
    assert receipt["action"] == "no_order"
    assert receipt["required_input"]["replay_date"] == "2024-06-21"


def test_audit_requires_fresh_strict_pit_consumer_verification(tmp_path):
    replay = _write_replay(tmp_path)
    candidate, _ = _write_candidate(
        tmp_path,
        "2024-06-01T12:00:00+08:00",
    )

    receipt = audit(tmp_path, replay, candidate)

    assert receipt["status"] == NOT_PROVEN
    assert receipt["strict_contemporaneous_rule_pit"] == NOT_PROVEN
    assert receipt["consumer_enforcement"]["status"] == "BLOCKED"
    assert receipt["consumer_enforcement"]["strict_pit_admitted"] is False


def test_audit_after_verified_gate_binds_contemporaneous_rule(
    tmp_path, monkeypatch
):
    replay = _write_replay(tmp_path)
    candidate, _ = _write_candidate(
        tmp_path,
        "2024-06-01T12:00:00+08:00",
    )

    class Verified:
        subject_sha256 = hashlib.sha256(replay.read_bytes()).hexdigest()

        def as_receipt(self):
            return {
                "status": "PASS",
                "strict_pit_admitted": True,
                "action": "no_order",
            }

    def fake_enforcement(*args, **kwargs):
        return Verified()

    monkeypatch.setattr(
        strict_pit_module,
        "enforce_strict_pit_consumption",
        fake_enforcement,
    )
    receipt = audit(tmp_path, replay, candidate)

    assert receipt["status"] == EVIDENCE_VALID
    assert receipt["strict_contemporaneous_rule_pit"] == (
        "EVIDENCE_VALID_FOR_CONTEMPORANEOUS_BINDING"
    )
    assert receipt["consumer_enforcement"]["status"] == "PASS"
    binding = receipt["checks"][-1]["detail"]
    assert binding["rule_registration_status"] == "CONTEMPORANEOUS_RULE"
    assert binding["registered_at"] == "2024-06-01T12:00:00+08:00"
    assert binding["registration_evidence"][0]["id"] == "rule-evidence-v1"


def test_audit_rejects_post_replay_evidence(tmp_path):
    replay = _write_replay(tmp_path)
    candidate, _ = _write_candidate(
        tmp_path,
        "2024-06-22T12:00:00+08:00",
    )

    receipt = audit(tmp_path, replay, candidate)

    assert receipt["status"] == FAILED
    assert receipt["strict_contemporaneous_rule_pit"] == NOT_PROVEN
    assert "cannot postdate the replay date" in receipt["checks"][0]["detail"]


def test_audit_rejects_hash_mismatch(tmp_path):
    replay = _write_replay(tmp_path)
    candidate, evidence = _write_candidate(
        tmp_path,
        "2024-06-01T12:00:00+08:00",
    )
    evidence.write_bytes(b'{"rule":"tampered"}')

    receipt = audit(tmp_path, replay, candidate)

    assert receipt["status"] == FAILED
    assert "hash mismatch" in receipt["checks"][0]["detail"]


def test_audit_rejects_wrong_rule_or_replay_identity(tmp_path):
    replay = _write_replay(tmp_path)
    payload = _replay_payload()
    candidate, _ = _write_candidate(
        tmp_path,
        "2024-06-01T12:00:00+08:00",
    )
    data = json.loads(candidate.read_text(encoding="utf-8"))
    data["rule_version"] = "wrong-rule-v1"
    candidate.write_text(json.dumps(data), encoding="utf-8")
    receipt = audit(tmp_path, replay, candidate)
    assert receipt["status"] == FAILED
    assert "rule version" in receipt["checks"][0]["detail"]

    data["rule_version"] = payload["rule"]["rule_version"]
    data["replay_id"] = "wrong-replay"
    candidate.write_text(json.dumps(data), encoding="utf-8")
    receipt = audit(tmp_path, replay, candidate)
    assert receipt["status"] == FAILED
    assert "replay id" in receipt["checks"][0]["detail"]


def test_candidate_parser_rejects_unsupported_or_duplicate_evidence(tmp_path):
    payload = _candidate_payload(_replay_payload(), available_at="2024-06-01T12:00:00+08:00")
    payload["evidence"][0]["evidence_kind"] = "prices"
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported rule registration evidence kind"):
        load_candidate(candidate)

    payload["evidence"][0]["evidence_kind"] = "versioned_file"
    payload["evidence"].append(dict(payload["evidence"][0]))
    candidate.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate evidence id"):
        load_candidate(candidate)


def test_cli_returns_two_when_consumer_enforcement_blocks(tmp_path, monkeypatch):
    replay = _write_replay(tmp_path)
    candidate, _ = _write_candidate(
        tmp_path,
        "2024-06-01T12:00:00+08:00",
    )
    monkeypatch.setattr(CLI, "ROOT", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit_m3_strict_pit_evidence.py",
            "--replay",
            str(replay),
            "--candidate",
            str(candidate),
            "--output-dir",
            str(tmp_path / "audit-output"),
        ],
    )

    assert CLI.main() == 2
    receipt = json.loads(
        (tmp_path / "audit-output" / "receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["status"] == NOT_PROVEN
    assert receipt["consumer_enforcement"]["status"] == "BLOCKED"
