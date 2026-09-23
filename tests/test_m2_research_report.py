from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

import pytest

from value_investment_agent.m2_research_report import (
    DEFAULT_RESEARCH_REPORT_PATH,
    VERDICT_INSUFFICIENT,
    VERDICT_PENDING,
    VERDICT_REJECTED,
    build_m2_research_reports,
    load_m2_research_report_policy,
)


ROOT = Path(__file__).resolve().parents[1]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _point(
    symbol: str,
    field_name: str,
    value: str,
    *,
    status: str = "verified",
    period_label: str = "2026-06-30",
) -> dict:
    return {
        "symbol": symbol,
        "field_name": field_name,
        "period_label": period_label,
        "value": value,
        "unit": "CNY",
        "validation_status": status,
        "source_name": "fixture source",
        "source_url": "https://example.test/disclosure.pdf",
        "sha256": _sha(f"{symbol}:{field_name}:{value}"),
        "published_at": "2026-08-18T00:00:00+00:00",
        "created_at": "2026-09-01T00:00:00+00:00",
        "fetched_at": "2026-09-01T00:00:00+00:00",
    }


def _audit_payload() -> dict:
    return {
        "schema_version": "m2-coverage-audit-v1",
        "sampling_version": "20260923-v1",
        "action": "no_order",
        "audit_status": "MACHINE_CHECKS_PASS",
        "strata": [
            {
                "stratum_id": "selected_leads",
                "source": "candidate",
                "samples": [
                    {
                        "symbol": "600011",
                        "name": "华能国际",
                        "channel": "dividend_cash_return",
                        "candidate_class": "LEAD",
                        "data_status": "PARTIAL",
                        "metrics": {"pe_ttm": "9", "pb": "1.6"},
                    },
                    {
                        "symbol": "600582",
                        "name": "天地科技",
                        "channel": "dividend_cash_return",
                        "candidate_class": "LEAD",
                        "data_status": "PARTIAL",
                        "metrics": {"pe_ttm": "18", "pb": "0.8"},
                    },
                    {
                        "symbol": "603799",
                        "name": "华友钴业",
                        "channel": "cyclical",
                        "candidate_class": "LEAD",
                        "data_status": "PARTIAL",
                        "metrics": {
                            "pe_ttm": "10",
                            "pb": "1.3",
                            "normalized_earnings": None,
                            "current_vs_normalized_roe": None,
                        },
                    },
                    {
                        "symbol": "000913",
                        "name": "钱江摩托",
                        "channel": "cyclical",
                        "candidate_class": "LEAD",
                        "data_status": "PARTIAL",
                        "metrics": {"pe_ttm": "9", "pb": "1.2"},
                    },
                    {
                        "symbol": "600999",
                        "name": "未来报告期测试公司",
                        "channel": "value",
                        "candidate_class": "LEAD",
                        "data_status": "PARTIAL",
                        "metrics": {"pe_ttm": "10", "pb": "1.0"},
                    },
                ],
            }
        ],
    }


def _financial_payload() -> dict:
    points = [
        _point("600011", "net_income", "100"),
        _point("600011", "operating_cash_flow", "200"),
        _point("600011", "free_cash_flow", "50"),
        _point("600582", "net_income", "100"),
        _point("600582", "operating_cash_flow", "-20"),
        _point("600582", "free_cash_flow", "-30"),
        _point("603799", "net_income", "100"),
        _point("603799", "operating_cash_flow", "50"),
        _point("603799", "free_cash_flow", "-10"),
        _point("600999", "net_income", "100", period_label="2026-09-30"),
        _point("600999", "operating_cash_flow", "200", period_label="2026-09-30"),
        _point("600999", "free_cash_flow", "50", period_label="2026-09-30"),
    ]
    return {
        "points": points,
        "retained_generated_at": "2026-09-23T15:12:00+00:00",
    }


def _dividend_row(symbol: str, name: str, cash_per_ten: str, yield_ratio: str) -> list:
    values = [None] * 18
    values[0] = symbol
    values[1] = name
    values[5] = cash_per_ten
    values[6] = yield_ratio
    values[13] = "2026-04-01"
    values[14] = "2026-05-01"
    values[15] = "2026-05-02"
    values[16] = "实施分配"
    values[17] = "2026-04-20"
    return values


def _dividend_payload() -> dict:
    return {
        "adapter_version": "fixture",
        "fetched_at": "2026-09-23T13:23:11+00:00",
        "fiscal_year": "2025",
        "source_name": "fixture dividend",
        "source_url": "https://example.test/dividend",
        "rows": [
            _dividend_row("600011", "华能国际", "4", "0.05"),
            _dividend_row("600582", "天地科技", "3", "0.055"),
        ],
    }


def _receipt_payload() -> dict:
    return {
        "schema_version": "m2-opportunity-discovery-v2",
        "run_id": "fixture-run",
        "action": "no_order",
        "generated_at": "2026-09-23T15:12:00+00:00",
        "as_of": "2026-09-23",
    }


def _fixture_policy(tmp_path: Path) -> Path:
    audit_path = tmp_path / "audit.json"
    receipt_path = tmp_path / "receipt.json"
    financial_path = tmp_path / "financial.json"
    dividend_path = tmp_path / "dividend.json"
    policy_path = tmp_path / "policy.json"

    audit_hash = _write_json(audit_path, _audit_payload())
    receipt_hash = _write_json(receipt_path, _receipt_payload())
    financial_hash = _write_json(financial_path, _financial_payload())
    dividend_hash = _write_json(dividend_path, _dividend_payload())
    payload = json.loads(DEFAULT_RESEARCH_REPORT_PATH.read_text(encoding="utf-8"))
    payload["sampling"] = {
        "audit_report_path": str(audit_path.relative_to(tmp_path)),
        "audit_report_sha256": audit_hash,
        "sampling_version": "fixture-v1",
        "stratum_id": "selected_leads",
        "selection_rule": "fixture",
    }
    payload["evidence"] = {
        "receipt_path": str(receipt_path.relative_to(tmp_path)),
        "receipt_sha256": receipt_hash,
        "financial_points_path": str(financial_path.relative_to(tmp_path)),
        "financial_points_sha256": financial_hash,
        "dividend_path": str(dividend_path.relative_to(tmp_path)),
        "dividend_sha256": dividend_hash,
    }
    policy_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return policy_path


def test_default_policy_is_pinned_and_contains_no_execution_keys():
    payload = json.loads(DEFAULT_RESEARCH_REPORT_PATH.read_text(encoding="utf-8"))
    policy = load_m2_research_report_policy()

    assert payload["action"] == "no_order"
    assert policy.minimum_substantive_reports == 3
    assert policy.minimum_channels == 2
    assert policy.sampling["audit_report_sha256"] == (
        "3c30936a6e567bd55b8d03bf67163071c49d223ca10def66b93fcdc336a84695"
    )
    forbidden = {"buy", "sell", "target_weight", "position_size", "order_quantity"}

    def walk(value: object) -> None:
        if isinstance(value, dict):
            assert not forbidden & set(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)


def test_synthetic_reports_are_deterministic_and_pass_minimum(tmp_path):
    policy_path = _fixture_policy(tmp_path)
    policy = load_m2_research_report_policy(policy_path)
    first = build_m2_research_reports(policy, root=tmp_path)
    second = build_m2_research_reports(policy, root=tmp_path)

    assert first.as_policy() == second.as_policy()
    assert first.machine_status == "MACHINE_CHECKS_PASS"
    assert first.acceptance_status == "AC8_REVIEW_PENDING"
    by_symbol = {report.symbol: report for report in first.reports}
    assert by_symbol["600011"].verdict == VERDICT_PENDING
    assert by_symbol["600582"].verdict == VERDICT_REJECTED
    assert by_symbol["603799"].verdict == VERDICT_REJECTED
    assert by_symbol["000913"].verdict == VERDICT_INSUFFICIENT
    assert first.as_policy()["summary"]["substantive_report_count"] == 3
    assert {
        "dividend_cash_return",
        "cyclical",
    } <= set(first.as_policy()["summary"]["substantive_channels"])


def test_tampered_audit_report_hash_is_rejected(tmp_path):
    policy_path = _fixture_policy(tmp_path)
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    payload["sampling"]["audit_report_sha256"] = "0" * 64
    policy_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256"):
        build_m2_research_reports(
            load_m2_research_report_policy(policy_path),
            root=tmp_path,
        )


def test_tampered_financial_points_hash_is_rejected(tmp_path):
    policy_path = _fixture_policy(tmp_path)
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    payload["evidence"]["financial_points_sha256"] = "0" * 64
    policy_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256"):
        build_m2_research_reports(
            load_m2_research_report_policy(policy_path),
            root=tmp_path,
        )


def test_report_payload_has_no_execution_keys(tmp_path):
    policy_path = _fixture_policy(tmp_path)
    batch = build_m2_research_reports(
        load_m2_research_report_policy(policy_path),
        root=tmp_path,
    )
    forbidden = {"buy", "sell", "target_weight", "position_size", "order_quantity"}

    def walk(value: object) -> None:
        if isinstance(value, dict):
            assert not forbidden & set(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(batch.as_policy())


def test_financial_evidence_after_registered_period_is_rejected(tmp_path):
    policy_path = _fixture_policy(tmp_path)
    batch = build_m2_research_reports(
        load_m2_research_report_policy(policy_path),
        root=tmp_path,
    )
    by_symbol = {report.symbol: report for report in batch.reports}

    assert by_symbol["600999"].verdict == VERDICT_INSUFFICIENT
    assert by_symbol["600999"].evidence == ()
