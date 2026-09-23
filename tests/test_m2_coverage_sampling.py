from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from value_investment_agent.m2_coverage_sampling import (
    DEFAULT_SAMPLING_PATH,
    load_m2_coverage_sampling,
    load_pinned_receipt,
    run_m2_coverage_audit,
)
from value_investment_agent.m2_opportunity_discovery import (
    ACTION_NO_ORDER,
    CANDIDATE_CLASS_LEAD,
    CHANNEL_CYCLICAL,
    CHANNEL_DIVIDEND,
    CHANNEL_QUALITY,
    CHANNEL_VALUE,
    CHANNELS,
    DATA_COMPLETE,
    DATA_PARTIAL,
    EVALUATION_BUDGET_EXCLUDED,
    EVALUATION_DATA_GAP,
    EVALUATION_NOT_EVALUATED,
    EVALUATION_PASS,
    EVALUATION_REJECTED,
    EVALUATION_UNSUPPORTED,
    PROFILE_SUPPORTED,
    PROFILE_UNSUPPORTED,
    PRIORITY_B,
    M2_RULE_VERSION,
    M2_SCHEMA_VERSION,
    CandidateReason,
    ChannelEvaluation,
    ChannelResult,
    DataHealth,
    DiscoveryRunReceipt,
    EvidenceReference,
    ExcludedSecurity,
    LegacyComparison,
    UniverseRecord,
    UniverseSnapshot,
    candidate_signature,
    coverage_signature,
)


ROOT = Path(__file__).resolve().parents[1]
_GENERATED_AT = datetime(2026, 9, 23, 8, 5, tzinfo=timezone.utc)
_QUOTE_DATE = "2026-09-23"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _reference() -> EvidenceReference:
    return EvidenceReference(
        id="fixture",
        path="runtime/fixture.json",
        sha256=_sha("fixture"),
        source_name="fixture",
        source_url="https://example.test/fixture",
        fetched_at=datetime(2026, 9, 23, 7, 0, tzinfo=timezone.utc),
    )


def _universe() -> UniverseSnapshot:
    records = tuple(
        UniverseRecord(
            symbol=symbol,
            name=f"公司{symbol[-2:]}",
            board="主板",
            exchange="SSE",
            listed_on="2000-01-01",
            official_industry="制造业",
            security_type="A股",
        )
        for symbol in (
            "600001",
            "600002",
            "600003",
            "600004",
            "600005",
            "600006",
            "600007",
            "600008",
            "600009",
        )
    )
    return UniverseSnapshot(
        schema_version=M2_SCHEMA_VERSION,
        as_of=date(2026, 9, 23),
        complete=True,
        scope="fixture",
        records=records,
        evidence_refs=(_reference(),),
    )


def _evaluation(
    symbol: str,
    channel: str,
    status: str,
    reason: str,
) -> ChannelEvaluation:
    if status == EVALUATION_BUDGET_EXCLUDED:
        reason = "已通过通道规则，但超出单通道展示预算 50；仍保留在覆盖率分母，未静默删除"
    return ChannelEvaluation(
        symbol=symbol,
        name=f"公司{symbol[-2:]}",
        channel=channel,
        status=status,
        reason=reason,
        profile_status=(
            PROFILE_UNSUPPORTED if status == EVALUATION_UNSUPPORTED else PROFILE_SUPPORTED
        ),
        evidence_date=_QUOTE_DATE,
    )


def _candidate(symbol: str, channel: str) -> CandidateReason:
    return CandidateReason(
        symbol=symbol,
        name=f"公司{symbol[-2:]}",
        channel=channel,
        reasons=("fixture research lead", "deep evidence still missing"),
        metrics={"pe_ttm": "8", "pb": "1", "fcf_yield": None},
        evidence_refs=(_reference(),),
        evidence_date=_QUOTE_DATE,
        data_status=DATA_PARTIAL if channel != CHANNEL_QUALITY else DATA_COMPLETE,
        profile_status=PROFILE_SUPPORTED,
        priority_tier=PRIORITY_B,
        candidate_class=CANDIDATE_CLASS_LEAD,
    )


def _channel_results() -> dict[str, ChannelResult]:
    quality_statuses = {
        "600001": EVALUATION_REJECTED,
        "600002": EVALUATION_REJECTED,
        "600003": EVALUATION_DATA_GAP,
        "600004": EVALUATION_UNSUPPORTED,
        "600005": EVALUATION_REJECTED,
        "600006": EVALUATION_REJECTED,
        "600007": EVALUATION_REJECTED,
        "600008": EVALUATION_DATA_GAP,
        "600009": EVALUATION_UNSUPPORTED,
    }
    dividend_statuses = {
        "600001": EVALUATION_REJECTED,
        "600002": EVALUATION_REJECTED,
        "600003": EVALUATION_NOT_EVALUATED,
        "600004": EVALUATION_UNSUPPORTED,
        "600005": EVALUATION_REJECTED,
        "600006": EVALUATION_REJECTED,
        "600007": EVALUATION_NOT_EVALUATED,
        "600008": EVALUATION_REJECTED,
        "600009": EVALUATION_REJECTED,
    }
    value_statuses = {
        "600001": EVALUATION_BUDGET_EXCLUDED,
        "600002": EVALUATION_PASS,
        "600003": EVALUATION_DATA_GAP,
        "600004": EVALUATION_UNSUPPORTED,
        "600005": EVALUATION_REJECTED,
        "600006": EVALUATION_REJECTED,
        "600007": EVALUATION_REJECTED,
        "600008": EVALUATION_DATA_GAP,
        "600009": EVALUATION_REJECTED,
    }
    cyclical_statuses = {
        "600001": EVALUATION_NOT_EVALUATED,
        "600002": EVALUATION_REJECTED,
        "600003": EVALUATION_DATA_GAP,
        "600004": EVALUATION_UNSUPPORTED,
        "600005": EVALUATION_REJECTED,
        "600006": EVALUATION_REJECTED,
        "600007": EVALUATION_NOT_EVALUATED,
        "600008": EVALUATION_REJECTED,
        "600009": EVALUATION_REJECTED,
    }
    status_maps = {
        CHANNEL_QUALITY: quality_statuses,
        CHANNEL_DIVIDEND: dividend_statuses,
        CHANNEL_VALUE: value_statuses,
        CHANNEL_CYCLICAL: cyclical_statuses,
    }
    results: dict[str, ChannelResult] = {}
    for channel, statuses in status_maps.items():
        evaluations = tuple(
            _evaluation(symbol, channel, status, f"{channel} {status} fixture reason")
            for symbol, status in sorted(statuses.items())
        )
        candidates = ()
        if channel == CHANNEL_VALUE:
            candidates = (_candidate("600002", CHANNEL_VALUE),)
        excluded = ()
        if channel == CHANNEL_DIVIDEND:
            excluded = (
                ExcludedSecurity(
                    symbol="600008",
                    name="公司08",
                    reason="explicit unsupported profile fixture",
                    profile_status=PROFILE_UNSUPPORTED,
                    evidence_date=_QUOTE_DATE,
                ),
            )
        results[channel] = ChannelResult(
            channel=channel,
            title=f"{channel} fixture",
            candidates=candidates,
            excluded=excluded,
            missing=(),
            rule_version=M2_RULE_VERSION,
            evaluations=evaluations,
        )
    return results


def _receipt() -> DiscoveryRunReceipt:
    channel_results = _channel_results()
    return DiscoveryRunReceipt(
        schema_version=M2_SCHEMA_VERSION,
        run_id="m2-coverage-audit-fixture",
        rule_version=M2_RULE_VERSION,
        generated_at=_GENERATED_AT,
        as_of=date(2026, 9, 23),
        quote_date=_QUOTE_DATE,
        action=ACTION_NO_ORDER,
        universe=_universe(),
        data_health=DataHealth(
            universe_count=9,
            quote_count=9,
            matched_quote_count=9,
            missing_quote_count=0,
            extra_quote_count=0,
            price_conflict_count=0,
            industry_mapping_count=9,
            financial_evidence_count=2,
            dividend_evidence_count=2,
            unsupported_financial_count=2,
            status="COMPLETE",
            blockers=(),
        ),
        channel_results=channel_results,
        legacy_comparison=LegacyComparison(
            legacy_candidate_count=2,
            legacy_candidates=("600001", "600009"),
            new_candidate_count=1,
            overlap_count=1,
            note="fixture legacy baseline",
        ),
        evidence_refs=(_reference(),),
        coverage_signature=coverage_signature(channel_results),
        candidate_signature=candidate_signature(channel_results),
    )


def _write_receipt(directory: Path) -> tuple[Path, str]:
    path = directory / "receipt.json"
    data = json.dumps(_receipt().as_policy(), ensure_ascii=False).encode("utf-8")
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def _write_policy(directory: Path, receipt_path: Path, receipt_sha256: str) -> Path:
    payload = json.loads(DEFAULT_SAMPLING_PATH.read_text(encoding="utf-8"))
    payload["receipt"] = {
        "path": str(receipt_path.relative_to(directory)),
        "sha256": receipt_sha256,
        "run_id": "m2-coverage-audit-fixture",
        "coverage_signature": _receipt().coverage_signature,
        "candidate_signature": _receipt().candidate_signature,
        "quote_date": "2026-09-23",
    }
    path = directory / "policy.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _default_strata_ids() -> set[str]:
    return {stratum.id for stratum in load_m2_coverage_sampling().strata}


def test_default_policy_pins_real_receipt_and_registers_all_required_strata():
    payload = json.loads(DEFAULT_SAMPLING_PATH.read_text(encoding="utf-8"))
    policy = load_m2_coverage_sampling()

    assert payload["action"] == ACTION_NO_ORDER
    assert payload["receipt"]["run_id"] == "m2-replay-20260923T232854Z"
    assert policy.receipt_sha256 == "869044a72c514be2d274308383c4479f7536bb393bfbf5ca10e492eee24bc220"
    assert {
        "selected_leads",
        "rejected",
        "data_gap",
        "unsupported",
        "budget_excluded",
        "not_evaluated",
        "excluded_security",
        "legacy_set",
    } <= _default_strata_ids()


def test_default_policy_contains_no_execution_keys():
    payload = json.loads(DEFAULT_SAMPLING_PATH.read_text(encoding="utf-8"))
    forbidden = {
        "trade_approved",
        "target_weight",
        "position_size",
        "order_quantity",
        "proposed_entry",
        "buy",
        "sell",
        "live_eligible",
        "return_threshold",
        "backtest_return",
    }

    def walk(value: object) -> None:
        if isinstance(value, dict):
            assert not forbidden & set(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)


def test_synthetic_audit_is_deterministic_and_covers_every_required_stratum(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    receipt_path, receipt_sha256 = _write_receipt(project)
    policy_path = _write_policy(project, receipt_path, receipt_sha256)
    policy = load_m2_coverage_sampling(policy_path)
    receipt = load_pinned_receipt(policy, root=project)

    first = run_m2_coverage_audit(policy, receipt)
    second = run_m2_coverage_audit(policy, receipt)

    assert first.as_policy() == second.as_policy()
    assert first.audit_status == "MACHINE_CHECKS_PASS"
    assert first.acceptance_status == "AC9_REVIEW_PENDING"
    by_id = {stratum.stratum_id: stratum for stratum in first.strata}
    for stratum in policy.strata:
        assert by_id[stratum.id].population_count >= stratum.minimum_population
    assert all(check.status == "PASS" for check in first.structural_checks)
    assert first.quality_empty_explanation["finding"].startswith("Quality zero")


def test_audit_rejects_tampered_receipt_file_hash(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    receipt_path, receipt_sha256 = _write_receipt(project)
    policy_path = _write_policy(project, receipt_path, receipt_sha256)
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["channel_results"]["value"]["evaluations"][0]["status"] = "REJECTED"
    receipt_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256"):
        load_pinned_receipt(load_m2_coverage_sampling(policy_path), root=project)


def test_audit_rejects_tampered_coverage_signature(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    receipt_path, _ = _write_receipt(project)
    receipt_sha256 = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    payload = json.loads(DEFAULT_SAMPLING_PATH.read_text(encoding="utf-8"))
    payload["receipt"] = {
        "path": str(receipt_path.relative_to(project)),
        "sha256": receipt_sha256,
        "run_id": "m2-coverage-audit-fixture",
        "coverage_signature": "0" * 64,
        "candidate_signature": _receipt().candidate_signature,
        "quote_date": "2026-09-23",
    }
    policy_path = project / "policy.json"
    policy_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="coverage signature"):
        load_pinned_receipt(load_m2_coverage_sampling(policy_path), root=project)


def test_audit_report_has_no_execution_keys(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    receipt_path, receipt_sha256 = _write_receipt(project)
    policy_path = _write_policy(project, receipt_path, receipt_sha256)
    receipt = load_pinned_receipt(load_m2_coverage_sampling(policy_path), root=project)
    report = run_m2_coverage_audit(load_m2_coverage_sampling(policy_path), receipt).as_policy()
    forbidden = {"buy", "sell", "target_weight", "position_size", "order_quantity"}

    def walk(value: object) -> None:
        if isinstance(value, dict):
            assert not forbidden & set(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(report)
