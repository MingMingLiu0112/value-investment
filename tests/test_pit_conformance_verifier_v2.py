from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from value_investment_agent.application.historical_validation import (
    StrictPitConsumerBlocked,
    PIT_CONFORMANCE_SCHEMA,
    enforce_strict_pit_consumption,
    verify_pit_conformance_v2,
)


CN_TZ = timezone(timedelta(hours=8))
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]
FROZEN_HISTORICAL_VALIDATION = "806d890817611000a588c9ee76ee00cc18a2529d5e1ee9769c092cc00452c5ba"
CLI_SPEC = importlib.util.spec_from_file_location(
    "audit_pit_conformance_v2",
    ROOT / "scripts" / "audit_pit_conformance_v2.py",
)
CLI = importlib.util.module_from_spec(CLI_SPEC)
CLI_SPEC.loader.exec_module(CLI)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _sha(data)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _evidence_record(
    *,
    evidence_id: str,
    kind: str,
    path: str,
    sha256: str,
    dimensions: list[str],
    available_at: str,
    availability_basis: str = "timestamp",
    version: str | None = None,
) -> dict:
    record = {
        "evidence_id": evidence_id,
        "kind": kind,
        "path": path,
        "sha256": sha256,
        "availability_basis": availability_basis,
        "available_at": available_at,
        "source_authority": "synthetic-fixture",
        "dimensions": dimensions,
    }
    if version is not None:
        record["version"] = version
    return record


def _ref(record: dict, *, available_at: str | None = None) -> dict:
    payload = {
        "id": record["evidence_id"],
        "kind": record["kind"],
        "path": record["path"],
        "sha256": record["sha256"],
        "source_url": "https://example.test/" + record["evidence_id"],
        "role": "synthetic evidence",
    }
    if available_at is not None:
        payload["available_at"] = available_at
    return payload


def _policy_fixture(root: Path) -> None:
    _write_json(
        root / "config" / "pit-conformance-policy-v2.json",
        {
            "schema_version": "pit-conformance-policy-v2",
            "policy_version": "pit-conformance-policy-test-v2",
            "action": "no_order",
        },
    )


def _valid_replay_fixture(
    root: Path,
    *,
    filing_basis: str = "timestamp",
    filing_available_at: str = "2024-04-03T12:00:00+08:00",
    filing_published_at: str = "2024-04-03T08:00:00+08:00",
    rule_status: str = "CONTEMPORANEOUS_RULE",
    future_rule_used: bool = False,
) -> tuple[Path, Path, dict]:
    _policy_fixture(root)
    filing_bytes = b'{"facts":"fixture"}'
    price_bytes = b'{"prices":"fixture"}'
    rule_bytes = b'{"rule":"fixture"}'
    filing_path = root / "evidence" / "filing.json"
    price_path = root / "evidence" / "prices.json"
    rule_path = root / "evidence" / "rule.json"
    filing_sha = _write(filing_path, filing_bytes)
    price_sha = _write(price_path, price_bytes)
    rule_sha = _write(rule_path, rule_bytes)
    filing_record = _evidence_record(
        evidence_id="filing",
        kind="annual_filing",
        path="evidence/filing.json",
        sha256=filing_sha,
        dimensions=["facts_pit"],
        available_at=filing_available_at,
        availability_basis=filing_basis,
    )
    price_record = _evidence_record(
        evidence_id="prices",
        kind="prices",
        path="evidence/prices.json",
        sha256=price_sha,
        dimensions=["quote_pit"],
        available_at="2024-06-21T15:00:00+08:00",
    )
    rule_record = _evidence_record(
        evidence_id="rule",
        kind="versioned_file",
        path="evidence/rule.json",
        sha256=rule_sha,
        dimensions=["rule_registration"],
        available_at="2024-06-01T09:00:00+08:00",
    )
    manifest_path = root / "manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": "pit-conformance-input-v2",
            "policy_version": "pit-conformance-policy-test-v2",
            "action": "no_order",
            "evidence": [filing_record, price_record, rule_record],
        },
    )

    filing_ref_available = filing_available_at
    if filing_basis == "date_only":
        published = date.fromisoformat(filing_available_at)
        filing_ref_available = datetime.combine(
            published + timedelta(days=1), datetime.min.time(), tzinfo=CN_TZ
        ).isoformat()
    filing_ref = _ref(filing_record, available_at=filing_ref_available)
    subject = {
        "schema_version": "m3-historical-research-replay-v1",
        "replay_id": "synthetic-replay",
        "namespace": "HISTORICAL_RESEARCH_REPLAY",
        "symbol": "000000",
        "replay_date": "2024-06-21",
        "generated_at": "2026-09-25T00:00:00+00:00",
        "source_receipt": {"input_sha256": filing_sha},
        "then_known_facts": {
            "symbol": "000000",
            "period_label": "2023-12-31",
            "source_id": "filing",
            "published_at": filing_published_at,
            "parent_profit_cny": "1",
            "ending_issued_shares": "1",
            "reported_basic_eps": "1",
            "source_ref": filing_ref,
        },
        "then_known_filings": [filing_ref],
        "then_known_quote": {
            "symbol": "000000",
            "quote_date": "2024-06-21",
            "close_cny": "1",
            "source_ref": _ref(price_record, available_at="2024-06-21T15:00:00+08:00"),
        },
        "rule": {
            "rule_version": "synthetic-rule-v1",
            "model_scope": "synthetic",
            "registered_at": "2024-06-01T09:00:00+08:00",
            "rule_registration_status": rule_status,
            "entry_margin": "0.3",
            "research_quantity": 100,
            "exit_rule": "synthetic",
            "registration_evidence": [
                _ref(rule_record, available_at="2024-06-01T09:00:00+08:00")
            ],
        },
        "source_decision_state": "proposed_entry",
        "source_decision_action": "propose_entry_review",
        "final_decision": "WAIT",
        "blockers": [],
        "valuation_approved": False,
        "trade_approved": False,
        "positive_price_review_eligible": False,
        "future_facts_used": False,
        "future_rule_version_used": future_rule_used,
        "action": "no_order",
    }
    subject_path = root / "replay.json"
    _write_json(subject_path, subject)
    return subject_path, manifest_path, subject


def _verify(root: Path, subject_path: Path, manifest_path: Path | None) -> dict:
    return verify_pit_conformance_v2(
        root,
        subject_path=subject_path,
        manifest_path=manifest_path,
        verified_at=NOW,
    )


def test_valid_contemporaneous_replay_passes_without_authorizing_action(tmp_path):
    _policy_fixture(tmp_path)
    subject_path, manifest_path, _ = _valid_replay_fixture(tmp_path)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["schema_version"] == PIT_CONFORMANCE_SCHEMA
    assert result["status"] == "PASS"
    assert result["strict_pit_admissible"] is True
    assert result["action"] == "no_order"
    assert result["performance_claim_allowed"] is False
    assert result["valuation_approved"] is False
    assert result["trade_approved"] is False
    assert result["production_authorized"] is False


def test_future_fact_is_rejected_even_when_declared_flag_is_false(tmp_path):
    subject_path, manifest_path, subject = _valid_replay_fixture(tmp_path)
    subject["then_known_facts"]["published_at"] = "2024-06-22T09:00:00+08:00"
    _write_json(subject_path, subject)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("facts_available_before_cutoff" in item for item in result["blockers"])
    assert result["strict_pit_admissible"] is False


def test_future_quote_date_is_rejected(tmp_path):
    subject_path, manifest_path, subject = _valid_replay_fixture(tmp_path)
    subject["then_known_quote"]["quote_date"] = "2024-06-22"
    _write_json(subject_path, subject)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("quote_not_future" in item for item in result["blockers"])


def test_date_only_same_day_is_future_but_prior_day_is_available(tmp_path):
    same_day_subject, same_day_manifest, subject = _valid_replay_fixture(
        tmp_path / "same-day",
        filing_basis="date_only",
        filing_available_at="2024-06-21",
        filing_published_at="2024-06-21T00:00:00+08:00",
    )

    same_day = _verify(tmp_path / "same-day", same_day_subject, same_day_manifest)

    prior_root = tmp_path / "prior-day"
    prior_subject, prior_manifest, _ = _valid_replay_fixture(
        prior_root,
        filing_basis="date_only",
        filing_available_at="2024-06-20",
        filing_published_at="2024-06-20T00:00:00+08:00",
    )
    prior = _verify(prior_root, prior_subject, prior_manifest)

    assert same_day["status"] == "FAIL"
    assert prior["status"] == "PASS"
    assert subject["then_known_facts"]["source_ref"]["available_at"].endswith("+08:00")


def test_retrospective_rule_is_not_upgraded_to_strict_pit(tmp_path):
    subject_path, manifest_path, _ = _valid_replay_fixture(
        tmp_path,
        rule_status="RETROSPECTIVE_RESEARCH_EXTENSION",
        future_rule_used=True,
    )

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "NOT_PROVEN"
    assert result["strict_pit_admissible"] is False
    assert any(
        "strict_contemporaneous_rule_pit" in item for item in result["blockers"]
    )


def test_retrospective_rule_cannot_hide_future_rule_flag(tmp_path):
    subject_path, manifest_path, _ = _valid_replay_fixture(
        tmp_path,
        rule_status="RETROSPECTIVE_RESEARCH_EXTENSION",
        future_rule_used=False,
    )

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("retrospective_rule_flag" in item for item in result["blockers"])


def test_facts_source_must_be_in_then_known_filings(tmp_path):
    subject_path, manifest_path, subject = _valid_replay_fixture(tmp_path)
    subject["then_known_filings"] = []
    _write_json(subject_path, subject)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any(
        "facts_source_in_then_known_filings" in item for item in result["blockers"]
    )


def test_facts_publication_cannot_postdate_source_availability(tmp_path):
    subject_path, manifest_path, subject = _valid_replay_fixture(tmp_path)
    subject["then_known_facts"]["published_at"] = "2024-04-04T09:00:00+08:00"
    _write_json(subject_path, subject)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("facts_availability_consistent" in item for item in result["blockers"])


def test_hash_mismatch_is_fail_closed(tmp_path):
    subject_path, manifest_path, _ = _valid_replay_fixture(tmp_path)
    (tmp_path / "evidence" / "filing.json").write_bytes(b"tampered")

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("Evidence hash mismatch" in item for item in result["blockers"])


def test_path_escape_and_missing_file_are_rejected(tmp_path):
    subject_path, manifest_path, _ = _valid_replay_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evidence"][0]["path"] = "../secret.json"
    _write_json(manifest_path, manifest)

    escaped = _verify(tmp_path, subject_path, manifest_path)

    missing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing_manifest["evidence"][0]["path"] = "evidence/missing.json"
    _write_json(manifest_path, missing_manifest)
    missing = _verify(tmp_path, subject_path, manifest_path)

    assert escaped["status"] == "FAIL"
    assert missing["status"] == "FAIL"


def test_duplicate_evidence_identity_is_rejected(tmp_path):
    subject_path, manifest_path, _ = _valid_replay_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evidence"].append(deepcopy(manifest["evidence"][0]))
    _write_json(manifest_path, manifest)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("Duplicate evidence_id" in item for item in result["blockers"])


def test_naive_timestamp_is_rejected(tmp_path):
    subject_path, manifest_path, _ = _valid_replay_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evidence"][0]["available_at"] = "2024-04-03T12:00:00"
    _write_json(manifest_path, manifest)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("timezone-aware" in item for item in result["blockers"])


def _add_admission_evidence(
    root: Path,
    *,
    evidence_id: str,
    kind: str,
    dimensions: list[str],
    available_at: str,
    body: bytes | None = None,
    availability_basis: str = "timestamp",
    version: str | None = None,
) -> dict:
    relative = f"evidence/{evidence_id}.json"
    data = body or json.dumps({"evidence_id": evidence_id}).encode("utf-8")
    sha256 = _write(root / relative, data)
    return _evidence_record(
        evidence_id=evidence_id,
        kind=kind,
        path=relative,
        sha256=sha256,
        dimensions=dimensions,
        available_at=available_at,
        availability_basis=availability_basis,
        version=version,
    )


def _admission_ref(record: dict) -> dict:
    return {
        "evidence_id": record["evidence_id"],
        "kind": record["kind"],
        "path": record["path"],
        "sha256": record["sha256"],
    }


def _valid_admission_fixture(
    root: Path,
    *,
    model_sessions: bool = True,
    universe_proof: bool = True,
    benchmark_proof: bool = True,
) -> tuple[Path, Path, dict]:
    _policy_fixture(root)
    cutoff = "2024-06-20T12:00:00+08:00"
    records: list[dict] = []
    by_id: dict[str, dict] = {}

    def add(evidence_id: str, kind: str, dimensions: list[str], **kwargs) -> dict:
        record = _add_admission_evidence(
            root,
            evidence_id=evidence_id,
            kind=kind,
            dimensions=dimensions,
            available_at=kwargs.pop("available_at", cutoff),
            **kwargs,
        )
        records.append(record)
        by_id[evidence_id] = record
        return record

    facts = add("facts", "annual_filing", ["facts_pit"])
    assumptions = add("assumptions", "valuation_assumptions", ["assumptions_pit"])
    valuation = add("valuation", "valuation", ["valuation_pit"])
    quote = add(
        "quote",
        "prices",
        ["quote_pit"],
        available_at="2024-06-21T15:00:00+08:00",
    )
    corporate = add("corporate", "corporate_actions", ["corporate_actions_pit"])
    fees = add("fees", "fees", ["fees_pit"])
    portfolio = add("portfolio", "portfolio_context", ["portfolio_context"])
    benchmark = add(
        "benchmark",
        "benchmark",
        ["benchmark_contract"],
        available_at="2024-06-20",
        availability_basis="date_only",
        version="benchmark-v1",
    )
    benchmark_return = add(
        "benchmark-return",
        "index_total_return",
        ["benchmark_contract"],
        available_at="2024-06-21T00:00:00+08:00",
    )
    benchmark_corporate = add(
        "benchmark-corporate",
        "benchmark_contract",
        ["benchmark_contract"],
        available_at="2024-06-21T00:00:00+08:00",
    )
    universe_snapshot = add(
        "universe-snapshot",
        "universe_snapshot",
        ["universe_pit"],
        available_at="2024-06-20",
        availability_basis="date_only",
    )
    universe_rule = add(
        "universe-rule",
        "universe_coverage",
        ["universe_pit"],
        available_at="2024-06-21T00:00:00+08:00",
        version="universe-v1",
    )
    universe_delisted = add(
        "universe-delisted", "universe_coverage", ["universe_pit"]
    )
    universe_suspended = add(
        "universe-suspended", "universe_coverage", ["universe_pit"]
    )
    universe_control = add(
        "universe-control", "universe_coverage", ["universe_pit"]
    )
    execution = add("execution", "execution_contract", ["execution_contract"])
    rule = add(
        "rule",
        "versioned_file",
        ["rule_registration"],
        available_at="2024-06-01T08:00:00+08:00",
    )

    dimension_refs = {
        "facts_pit": [_admission_ref(facts)],
        "assumptions_pit": [_admission_ref(assumptions)],
        "valuation_pit": [_admission_ref(valuation)],
        "quote_pit": [_admission_ref(quote)],
        "corporate_actions_pit": [_admission_ref(corporate)],
        "fees_pit": [_admission_ref(fees)],
        "portfolio_context": [_admission_ref(portfolio)],
        "benchmark_contract": [
            _admission_ref(benchmark),
            _admission_ref(benchmark_return),
            _admission_ref(benchmark_corporate),
        ],
        "universe_pit": [
            _admission_ref(universe_snapshot),
            _admission_ref(universe_rule),
            _admission_ref(universe_delisted),
            _admission_ref(universe_suspended),
            _admission_ref(universe_control),
        ],
    }
    assessments = {
        name: {
            "status": "VERIFIED",
            "detail": f"{name} synthetic proof",
            "evidence_refs": refs,
            "blockers": [],
        }
        for name, refs in dimension_refs.items()
    }
    subject = {
        "schema_version": "historical-validation-admission-v1",
        "policy_version": "historical-validation-policy-v1",
        "admission_id": "synthetic-admission",
        "symbol": "000000",
        "scope": "synthetic",
        "window": {"start": "2024-06-21", "end": "2024-06-21"},
        "information_cutoff_policy": "available_at <= decision_at",
        "rule_version": "synthetic-rule-v1",
        "rule_registration_status": "CONTEMPORANEOUS_RULE",
        "rule_evidence_refs": ["rule"],
        **assessments,
        "execution_contract": {
            "signal_to_fill": "next_session_open",
            "settlement": "T+1",
            "board_lot": 100,
            "cash_policy": "cash only",
            "suspension_policy": "block suspended fills",
            "price_limit_policy": "block missing limits",
            "liquidity_policy": "research assumption",
            "corporate_action_policy": "record-date entitlement",
            "fee_policy": "dated fees",
            "status": "VERIFIED",
            "evidence_refs": [_admission_ref(execution)],
            "blockers": [],
        },
        "survivorship_status": "CONTROLLED",
        "approved_value_model_sessions": 1 if model_sessions else 0,
        "classification": "STRICT_CONTEMPORANEOUS_REPLAY",
        "admission_status": "ADMITTED_FOR_STRICT_REPLAY",
        "blockers": [],
        "evidence_refs": [_admission_ref(record) for record in records],
        "action": "no_order",
    }
    manifest = {
        "schema_version": "pit-conformance-input-v2",
        "policy_version": "pit-conformance-policy-test-v2",
        "action": "no_order",
        "evidence": records,
        "benchmark": {
            "benchmark_id": "synthetic-index",
            "version": "benchmark-v1",
            "as_of": "2024-06-20",
            "methodology_evidence_id": "benchmark",
            "return_series_evidence_id": "benchmark-return",
            "corporate_action_evidence_id": "benchmark-corporate",
        } if benchmark_proof else None,
        "universe": {
            "as_of": "2024-06-20",
            "selection_rule_version": "universe-v1",
            "snapshot_evidence_id": "universe-snapshot",
            "selection_rule_evidence_id": "universe-rule",
            "delisted_coverage_evidence_id": "universe-delisted",
            "suspended_coverage_evidence_id": "universe-suspended",
            "survivorship_control_evidence_id": "universe-control",
        } if universe_proof else None,
        "model_sessions": (
            [
                {
                    "session_id": "session-1",
                    "decision_at": "2024-06-21T15:00:00+08:00",
                    "model_evidence_id": "valuation",
                    "valuation_evidence_id": "valuation",
                    "assumptions_evidence_id": "assumptions",
                    "quote_evidence_id": "quote",
                    "approved": True,
                }
            ]
            if model_sessions
            else []
        ),
        "rule_registration": {
            "rule_version": "synthetic-rule-v1",
            "status": "CONTEMPORANEOUS_RULE",
            "registered_at": "2024-06-01T09:00:00+08:00",
            "evidence_ids": ["rule"],
        },
    }
    subject_path = root / "admission.json"
    manifest_path = root / "manifest.json"
    _write_json(subject_path, subject)
    _write_json(manifest_path, manifest)
    return subject_path, manifest_path, subject


def test_valid_strict_admission_passes_only_with_complete_proofs(tmp_path):
    subject_path, manifest_path, _ = _valid_admission_fixture(tmp_path)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "PASS"
    assert result["strict_pit_admissible"] is True
    assert result["action"] == "no_order"


def test_missing_benchmark_proof_remains_not_proven(tmp_path):
    subject_path, manifest_path, _ = _valid_admission_fixture(
        tmp_path, benchmark_proof=False
    )

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "NOT_PROVEN"
    assert any("benchmark_proof_present" in item for item in result["blockers"])


def test_missing_universe_or_survivorship_proof_remains_not_proven(tmp_path):
    subject_path, manifest_path, _ = _valid_admission_fixture(
        tmp_path, universe_proof=False
    )

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "NOT_PROVEN"
    assert any("universe_proof_present" in item for item in result["blockers"])


def test_positive_model_session_count_without_proof_is_rejected(tmp_path):
    subject_path, manifest_path, subject = _valid_admission_fixture(tmp_path)
    subject["approved_value_model_sessions"] = 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["model_sessions"] = []
    _write_json(subject_path, subject)
    _write_json(manifest_path, manifest)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("model_session_count_matches" in item for item in result["blockers"])


def test_benchmark_version_or_date_mismatch_is_rejected(tmp_path):
    subject_path, manifest_path, _ = _valid_admission_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["benchmark"]["version"] = "wrong-version"
    _write_json(manifest_path, manifest)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("benchmark_version_matches" in item for item in result["blockers"])


def test_generic_evidence_cannot_cover_multiple_critical_dimensions(tmp_path):
    subject_path, manifest_path, subject = _valid_admission_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assumptions = next(
        item for item in manifest["evidence"] if item["evidence_id"] == "assumptions"
    )
    assumptions["kind"] = "versioned_file"
    assumptions["dimensions"] = ["assumptions_pit", "valuation_pit"]
    manifest["evidence"] = [
        item for item in manifest["evidence"] if item["evidence_id"] != "valuation"
    ]
    subject["valuation_pit"]["evidence_refs"] = [_admission_ref(assumptions)]
    subject["evidence_refs"] = [
        item for item in subject["evidence_refs"] if item["evidence_id"] != "valuation"
    ]
    manifest["model_sessions"][0]["model_evidence_id"] = "assumptions"
    manifest["model_sessions"][0]["valuation_evidence_id"] = "assumptions"
    _write_json(subject_path, subject)
    _write_json(manifest_path, manifest)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("dimension_evidence_disjoint" in item for item in result["blockers"])


def test_missing_manifest_is_not_proven_not_pass(tmp_path):
    subject_path, _, _ = _valid_replay_fixture(tmp_path)

    result = _verify(tmp_path, subject_path, None)

    assert result["status"] == "NOT_PROVEN"
    assert result["strict_pit_admissible"] is False


def test_verifier_does_not_mutate_inputs_or_frozen_contract(tmp_path):
    subject_path, manifest_path, _ = _valid_replay_fixture(tmp_path)
    before_subject = subject_path.read_bytes()
    before_manifest = manifest_path.read_bytes()
    frozen_path = ROOT / "src" / "value_investment_agent" / "historical_validation.py"
    before_frozen = frozen_path.read_bytes()

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "PASS"
    assert subject_path.read_bytes() == before_subject
    assert manifest_path.read_bytes() == before_manifest
    assert hashlib.sha256(before_frozen).hexdigest() == FROZEN_HISTORICAL_VALIDATION
    assert frozen_path.read_bytes() == before_frozen


def test_future_filing_evidence_is_rejected(tmp_path):
    subject_path, manifest_path, subject = _valid_replay_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    late = "2024-06-22T09:00:00+08:00"
    manifest["evidence"][0]["available_at"] = late
    subject["then_known_facts"]["source_ref"]["available_at"] = late
    subject["then_known_filings"][0]["available_at"] = late
    _write_json(subject_path, subject)
    _write_json(manifest_path, manifest)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("future_facts_flag_consistent" in item for item in result["blockers"])


def test_future_quote_evidence_is_rejected(tmp_path):
    subject_path, manifest_path, subject = _valid_replay_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    late = "2024-06-21T16:00:00+08:00"
    manifest["evidence"][1]["available_at"] = late
    subject["then_known_quote"]["source_ref"]["available_at"] = late
    _write_json(subject_path, subject)
    _write_json(manifest_path, manifest)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("future_facts_flag_consistent" in item for item in result["blockers"])


def test_unsupported_availability_basis_is_rejected(tmp_path):
    subject_path, manifest_path, _ = _valid_replay_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evidence"][0]["availability_basis"] = "unknown"
    _write_json(manifest_path, manifest)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("availability_basis" in item for item in result["blockers"])


def test_duplicate_kind_hash_pair_is_rejected(tmp_path):
    subject_path, manifest_path, _ = _valid_replay_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    duplicate = deepcopy(manifest["evidence"][0])
    duplicate["evidence_id"] = "filing-copy"
    manifest["evidence"].append(duplicate)
    _write_json(manifest_path, manifest)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("Duplicate evidence kind/hash" in item for item in result["blockers"])


def test_contemporaneous_rule_cannot_be_registered_after_cutoff(tmp_path):
    subject_path, manifest_path, subject = _valid_replay_fixture(tmp_path)
    subject["rule"]["registered_at"] = "2024-06-22T09:00:00+08:00"
    _write_json(subject_path, subject)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("contemporaneous_rule_before_cutoff" in item for item in result["blockers"])


def test_missing_universe_control_is_not_proven(tmp_path):
    subject_path, manifest_path, _ = _valid_admission_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["universe"]["delisted_coverage_evidence_id"]
    _write_json(manifest_path, manifest)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "NOT_PROVEN"
    assert any("proof_evidence_id_present" in item for item in result["blockers"])


def test_execution_contract_board_lot_is_checked(tmp_path):
    subject_path, manifest_path, subject = _valid_admission_fixture(tmp_path)
    subject["execution_contract"]["board_lot"] = 1
    _write_json(subject_path, subject)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("execution_board_lot" in item for item in result["blockers"])


def test_zero_approved_model_sessions_is_not_proven(tmp_path):
    subject_path, manifest_path, _ = _valid_admission_fixture(
        tmp_path, model_sessions=False
    )

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "NOT_PROVEN"
    assert any("model_session_count_positive" in item for item in result["blockers"])


def test_replay_cannot_claim_valuation_or_trade_approval(tmp_path):
    subject_path, manifest_path, subject = _valid_replay_fixture(tmp_path)
    subject["valuation_approved"] = True
    _write_json(subject_path, subject)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("no_approval_boundary" in item for item in result["blockers"])


def test_cli_exit_codes_distinguish_pass_and_not_proven(tmp_path, capsys):
    subject_path, manifest_path, _ = _valid_replay_fixture(tmp_path)

    assert CLI.main(
        [
            "--root",
            str(tmp_path),
            "--subject",
            str(subject_path),
            "--manifest",
            str(manifest_path),
        ]
    ) == 0
    capsys.readouterr()
    assert CLI.main(
        ["--root", str(tmp_path), "--subject", str(subject_path)]
    ) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "NOT_PROVEN"


def test_missing_or_malformed_policy_never_passes(tmp_path):
    missing_root = tmp_path / "missing-policy"
    missing_subject, missing_manifest, _ = _valid_replay_fixture(missing_root)
    (missing_root / "config" / "pit-conformance-policy-v2.json").unlink()

    missing = _verify(missing_root, missing_subject, missing_manifest)

    malformed_root = tmp_path / "malformed-policy"
    malformed_subject, malformed_manifest, _ = _valid_replay_fixture(malformed_root)
    (malformed_root / "config" / "pit-conformance-policy-v2.json").write_text(
        "{not-json", encoding="utf-8"
    )
    malformed = _verify(malformed_root, malformed_subject, malformed_manifest)

    assert missing["status"] == "NOT_PROVEN"
    assert malformed["status"] == "FAIL"
    assert missing["strict_pit_admissible"] is False
    assert malformed["strict_pit_admissible"] is False


def test_manifest_policy_version_must_match_loaded_policy(tmp_path):
    subject_path, manifest_path, _ = _valid_replay_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["policy_version"] = "different-policy"
    _write_json(manifest_path, manifest)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "FAIL"
    assert any("policy_version" in item for item in result["blockers"])


def test_subject_and_manifest_paths_cannot_escape_root(tmp_path):
    root = tmp_path / "repo"
    subject_path, manifest_path, _ = _valid_replay_fixture(root)
    outside_subject = tmp_path / "outside-subject.json"
    outside_manifest = tmp_path / "outside-manifest.json"
    outside_subject.write_bytes(subject_path.read_bytes())
    outside_manifest.write_bytes(manifest_path.read_bytes())

    escaped_subject = _verify(root, outside_subject, manifest_path)
    escaped_manifest = _verify(root, subject_path, outside_manifest)

    assert escaped_subject["status"] == "FAIL"
    assert escaped_manifest["status"] == "FAIL"
    assert any("outside the repository root" in item for item in escaped_manifest["blockers"])


def test_cli_exit_code_one_for_integrity_failure(tmp_path, capsys):
    subject_path, manifest_path, _ = _valid_replay_fixture(tmp_path)
    (tmp_path / "evidence" / "filing.json").write_bytes(b"tampered")

    assert CLI.main(
        [
            "--root",
            str(tmp_path),
            "--subject",
            str(subject_path),
            "--manifest",
            str(manifest_path),
        ]
    ) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "FAIL"


def test_verifier_result_binds_exact_subject_and_manifest_bytes(tmp_path):
    subject_path, manifest_path, _ = _valid_replay_fixture(tmp_path)

    result = _verify(tmp_path, subject_path, manifest_path)

    assert result["status"] == "PASS"
    assert result["subject"]["sha256"] == _sha(subject_path.read_bytes())
    assert result["manifest"]["sha256"] == _sha(manifest_path.read_bytes())


def test_consumer_enforcement_returns_byte_bound_no_order_receipt(tmp_path):
    subject_path, manifest_path, _ = _valid_replay_fixture(tmp_path)

    verified = enforce_strict_pit_consumption(
        tmp_path,
        subject_path=subject_path,
        manifest_path=manifest_path,
        consumed_at=NOW,
    )
    receipt = verified.as_receipt()

    assert receipt["schema_version"] == "pit-conformance-consumer-enforcement-v1"
    assert receipt["verification_mode"] == "IN_PROCESS_FRESH_RECHECK"
    assert receipt["subject"]["sha256"] == _sha(subject_path.read_bytes())
    assert receipt["manifest"]["sha256"] == _sha(manifest_path.read_bytes())
    assert receipt["strict_pit_admitted"] is True
    assert receipt["action"] == "no_order"
    assert receipt["performance_claim_allowed"] is False
    assert receipt["valuation_approved"] is False
    assert receipt["trade_approved"] is False
    assert receipt["production_authorized"] is False


def test_consumer_enforcement_blocks_missing_or_retrospective_proof(tmp_path):
    subject_path, manifest_path, _ = _valid_replay_fixture(tmp_path)

    with pytest.raises(StrictPitConsumerBlocked):
        enforce_strict_pit_consumption(
            tmp_path,
            subject_path=subject_path,
            manifest_path=None,
            consumed_at=NOW,
        )

    retrospective_subject, retrospective_manifest, _ = _valid_replay_fixture(
        tmp_path / "retrospective",
        rule_status="RETROSPECTIVE_RESEARCH_EXTENSION",
        future_rule_used=True,
    )
    with pytest.raises(StrictPitConsumerBlocked) as error:
        enforce_strict_pit_consumption(
            tmp_path / "retrospective",
            subject_path=retrospective_subject,
            manifest_path=retrospective_manifest,
            consumed_at=NOW,
        )
    assert error.value.verifier_result["status"] == "NOT_PROVEN"
    assert error.value.verifier_result["strict_pit_admissible"] is False


def test_consumer_enforcement_rejects_stale_or_forged_verifier_hashes(
    tmp_path, monkeypatch
):
    subject_path, manifest_path, _ = _valid_replay_fixture(tmp_path)

    def forged_verifier(*args, **kwargs):
        return {
            "schema_version": PIT_CONFORMANCE_SCHEMA,
            "status": "PASS",
            "strict_pit_admissible": True,
            "action": "no_order",
            "policy_version": "forged-policy",
            "verified_at": NOW.isoformat(),
            "subject": {"path": str(subject_path), "sha256": "0" * 64},
            "manifest": {"path": str(manifest_path), "sha256": "1" * 64},
        }

    monkeypatch.setattr(
        "value_investment_agent.application.historical_validation.consumer_enforcement.verify_pit_conformance_v2",
        forged_verifier,
    )

    with pytest.raises(StrictPitConsumerBlocked, match="bytes changed"):
        enforce_strict_pit_consumption(
            tmp_path,
            subject_path=subject_path,
            manifest_path=manifest_path,
            consumed_at=NOW,
        )


@pytest.mark.parametrize("target", ["subject", "manifest"])
def test_consumer_enforcement_blocks_bytes_changed_during_verification(
    tmp_path, monkeypatch, target
):
    subject_path, manifest_path, _ = _valid_replay_fixture(tmp_path)
    changing_path = subject_path if target == "subject" else manifest_path

    def racing_verifier(*args, **kwargs):
        result = verify_pit_conformance_v2(*args, **kwargs)
        changing_path.write_bytes(changing_path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(
        "value_investment_agent.application.historical_validation.consumer_enforcement.verify_pit_conformance_v2",
        racing_verifier,
    )

    with pytest.raises(StrictPitConsumerBlocked, match="bytes changed"):
        enforce_strict_pit_consumption(
            tmp_path,
            subject_path=subject_path,
            manifest_path=manifest_path,
            consumed_at=NOW,
        )


def test_consumer_enforcement_blocks_zero_model_sessions(tmp_path):
    subject_path, manifest_path, _ = _valid_admission_fixture(
        tmp_path, model_sessions=False
    )

    with pytest.raises(StrictPitConsumerBlocked) as error:
        enforce_strict_pit_consumption(
            tmp_path,
            subject_path=subject_path,
            manifest_path=manifest_path,
            consumed_at=NOW,
        )

    assert error.value.verifier_result["status"] == "NOT_PROVEN"
    assert any(
        "model_session_count_positive" in item
        for item in error.value.verifier_result["blockers"]
    )
