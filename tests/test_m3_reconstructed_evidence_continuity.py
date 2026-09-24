from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json

import pytest

from value_investment_agent.m3_reconstructed_evidence_continuity import (
    ACTION_NO_ORDER,
    DIRECTION_DOWN,
    DIRECTION_UP,
    IMPACT_STRENGTHENED,
    IMPACT_WEAKENED,
    METRIC_BASIC_EPS,
    METRIC_PARENT_EQUITY,
    METRIC_PARENT_PROFIT,
    TRACE_NAMESPACE,
    TRACE_SCHEMA,
    M3ReconstructedEvidenceContinuity,
    from_payload,
)
from value_investment_agent.m3_reconstructed_evidence_workbook import (
    BOUNDARY_SHEET,
    COMPARISON_SHEET,
    CONCLUSION_SHEET,
    DISCLOSURE_SHEET,
    SOURCE_SHEET,
    build_reconstructed_evidence_workbook,
    write_reconstructed_evidence_workbook,
)


CN_TZ = timezone(timedelta(hours=8))
GENERATED_AT = datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc)
SYMBOL = "600519"


def _metric(key, value, comparative=None, *, ref: str) -> dict:
    return {
        "metric": key,
        "period_end": "2023-12-31",
        "period_basis": "BASELINE" if comparative is None else "FY",
        "current_value": value,
        "comparative_value": comparative,
        "unit": "CNY" if key != METRIC_BASIC_EPS else "CNY/share",
        "reference_id": ref,
        "validation_status": "fixture_verified",
        "source_label": key,
    }


def _disclosure_metric(key, current, comparative, *, period, basis, ref) -> dict:
    return {
        "metric": key,
        "period_end": period,
        "period_basis": basis,
        "current_value": current,
        "comparative_value": comparative,
        "unit": "CNY" if key != METRIC_BASIC_EPS else "CNY/share",
        "reference_id": ref,
        "validation_status": "fixture_verified",
        "source_label": key,
    }


def _payload() -> dict:
    return {
        "trace_id": "600519-reconstructed-evidence-continuity-v1",
        "schema_version": TRACE_SCHEMA,
        "namespace": TRACE_NAMESPACE,
        "symbol": SYMBOL,
        "generated_at": GENERATED_AT.isoformat(),
        "baseline": {
            "baseline_date": "2024-06-21",
            "source_replay_id": "m3-historical-research-replay-600519-2024-06-21-v1",
            "rule_version": "moutai-pe-mid-paper-contract-v2-2025-extension",
            "rule_registered_at": "2026-09-12T05:27:47+00:00",
            "rule_registration_status": "RETROSPECTIVE_RESEARCH_EXTENSION",
            "future_rule_version_used": True,
            "strict_contemporaneous_rule_pit": False,
            "facts": [
                _metric(METRIC_PARENT_PROFIT, "74734071550.75", ref="annual-2023"),
                _metric(METRIC_PARENT_EQUITY, "215668571607.43", ref="annual-2023"),
                _metric(METRIC_BASIC_EPS, "59.49", ref="annual-2023"),
                _metric("close_price", "1471.00", ref="price-2024"),
                _metric("cash_per_share", "30.876", ref="distribution-2024"),
            ],
            "note": "公开 fixture：只测试重建边界，不使用真实账户。",
        },
        "disclosures": [
            {
                "observation_id": "obs-2024-annual",
                "disclosure_id": "cninfo:fixture-2024",
                "title": "贵州茅台2024年年度报告（fixture）",
                "report_period": "2024-12-31",
                "period_basis": "FY",
                "available_at": "2025-04-04T00:00:00+08:00",
                "evidence_quality": "fixture_issuer_original",
                "metrics": [
                    _disclosure_metric(
                        METRIC_PARENT_PROFIT,
                        "86228146421.62",
                        "74734071550.75",
                        period="2024-12-31",
                        basis="FY",
                        ref="annual-2024",
                    ),
                    _disclosure_metric(
                        METRIC_PARENT_EQUITY,
                        "233105984399.47",
                        "215668571607.43",
                        period="2024-12-31",
                        basis="FY",
                        ref="annual-2024",
                    ),
                    _disclosure_metric(
                        METRIC_BASIC_EPS,
                        "68.64",
                        "59.49",
                        period="2024-12-31",
                        basis="FY",
                        ref="annual-2024",
                    ),
                ],
            },
            {
                "observation_id": "obs-2025-annual",
                "disclosure_id": "cninfo:fixture-2025",
                "title": "贵州茅台2025年年度报告（fixture）",
                "report_period": "2025-12-31",
                "period_basis": "FY",
                "available_at": "2026-04-18T00:00:00+08:00",
                "evidence_quality": "fixture_issuer_original",
                "metrics": [
                    _disclosure_metric(
                        METRIC_PARENT_PROFIT,
                        "82320067101.68",
                        "86228146421.62",
                        period="2025-12-31",
                        basis="FY",
                        ref="annual-2025",
                    ),
                    _disclosure_metric(
                        METRIC_PARENT_EQUITY,
                        "244637811032.18",
                        "233105984399.47",
                        period="2025-12-31",
                        basis="FY",
                        ref="annual-2025",
                    ),
                    _disclosure_metric(
                        METRIC_BASIC_EPS,
                        "65.66",
                        "68.64",
                        period="2025-12-31",
                        basis="FY",
                        ref="annual-2025",
                    ),
                ],
            },
            {
                "observation_id": "obs-2026-h1",
                "disclosure_id": "cninfo:fixture-2026-h1",
                "title": "贵州茅台2026年半年度报告（fixture）",
                "report_period": "2026-06-30",
                "period_basis": "YTD",
                "available_at": "2026-08-16T00:00:00+08:00",
                "evidence_quality": "fixture_issuer_original",
                "metrics": [
                    _disclosure_metric(
                        METRIC_PARENT_PROFIT,
                        "44516880421.86",
                        "45402962298.10",
                        period="2026-06-30",
                        basis="YTD",
                        ref="interim-2026-h1",
                    )
                ],
            },
        ],
        "comparisons": [
            {
                "dimension": METRIC_PARENT_PROFIT,
                "baseline_value": "74734071550.75",
                "observation_id": "obs-2024-annual",
                "observation_value": "86228146421.62",
                "change_direction": DIRECTION_UP,
                "impact": IMPACT_STRENGTHENED,
                "arithmetic_note": "FY2024 对 FY2023 上升",
                "evidence_ref_ids": ["annual-2023", "annual-2024"],
            },
            {
                "dimension": METRIC_PARENT_PROFIT,
                "baseline_value": "74734071550.75",
                "observation_id": "obs-2025-annual",
                "observation_value": "82320067101.68",
                "change_direction": DIRECTION_UP,
                "impact": IMPACT_STRENGTHENED,
                "arithmetic_note": "FY2025 仍高于基准，但低于 FY2024",
                "evidence_ref_ids": ["annual-2023", "annual-2025"],
            },
            {
                "dimension": METRIC_PARENT_PROFIT,
                "baseline_value": "74734071550.75",
                "observation_id": "obs-2026-h1",
                "observation_value": "44516880421.86",
                "change_direction": DIRECTION_DOWN,
                "impact": IMPACT_WEAKENED,
                "arithmetic_note": "2026H1 对 2025H1 下降",
                "evidence_ref_ids": ["annual-2023", "interim-2026-h1"],
            },
        ],
        "evidence_references": [
            {
                "ref_id": "annual-2023",
                "kind": "filing",
                "path": "fixtures/annual-2023.pdf",
                "sha256": "a" * 64,
                "source_url": "https://example.test/annual-2023.pdf",
                "available_at": "2024-04-04T00:00:00+08:00",
                "role": "2023 annual filing",
            },
            {
                "ref_id": "annual-2024",
                "kind": "filing",
                "path": "fixtures/annual-2024.pdf",
                "sha256": "b" * 64,
                "source_url": "https://example.test/annual-2024.pdf",
                "available_at": "2025-04-04T00:00:00+08:00",
                "role": "2024 annual filing",
            },
            {
                "ref_id": "annual-2025",
                "kind": "filing",
                "path": "fixtures/annual-2025.pdf",
                "sha256": "c" * 64,
                "source_url": "https://example.test/annual-2025.pdf",
                "available_at": "2026-04-18T00:00:00+08:00",
                "role": "2025 annual filing",
            },
            {
                "ref_id": "interim-2026-h1",
                "kind": "filing",
                "path": "fixtures/interim-2026-h1.pdf",
                "sha256": "d" * 64,
                "source_url": "https://example.test/interim-2026-h1.pdf",
                "available_at": "2026-08-16T00:00:00+08:00",
                "role": "2026 interim filing",
            },
            {
                "ref_id": "distribution-2024",
                "kind": "filing",
                "path": "fixtures/distribution-2024.pdf",
                "sha256": "e" * 64,
                "source_url": "https://example.test/distribution-2024.pdf",
                "available_at": "2024-06-12T00:00:00+08:00",
                "role": "distribution filing",
            },
            {
                "ref_id": "price-2024",
                "kind": "price_file",
                "path": "fixtures/price-2024.json",
                "sha256": "f" * 64,
                "source_url": "https://example.test/price-2024.json",
                "available_at": "2024-06-21T15:00:00+08:00",
                "role": "authenticated price file",
            },
        ],
        "conclusion_status": "RECONSTRUCTED_EVIDENCE_ONLY",
        "actual_entry_present": False,
        "human_decision": None,
        "requires_human_review": True,
        "blockers": [
            "retrospective_rule_not_contemporaneous",
            "no_actual_entry_or_human_decision",
            "arithmetic_trend_is_not_a_thesis_verdict",
        ],
        "action": ACTION_NO_ORDER,
    }


def _trace() -> M3ReconstructedEvidenceContinuity:
    return from_payload(_payload())


def _all_text(workbook) -> str:
    return "\n".join(
        str(cell.value)
        for sheet in workbook
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )


def test_trace_reconstructs_public_evidence_and_stays_no_order():
    trace = _trace()

    assert trace.symbol == SYMBOL
    assert trace.namespace == TRACE_NAMESPACE
    assert trace.conclusion_status == "RECONSTRUCTED_EVIDENCE_ONLY"
    assert trace.baseline.future_rule_version_used is True
    assert trace.baseline.strict_contemporaneous_rule_pit is False
    assert trace.actual_entry_present is False
    assert trace.human_decision is None
    assert trace.requires_human_review is True
    assert trace.action == ACTION_NO_ORDER
    assert len(trace.trace_sha256) == 64


def test_metric_arithmetic_is_correct():
    trace = _trace()

    fy2024 = trace.disclosures[0].metric(METRIC_PARENT_PROFIT)
    assert fy2024 is not None
    assert fy2024.change_direction == DIRECTION_UP
    assert fy2024.percentage_change > Decimal("15.3")
    assert fy2024.percentage_change < Decimal("15.5")

    fy2025 = trace.disclosures[1].metric(METRIC_PARENT_PROFIT)
    assert fy2025 is not None
    assert fy2025.change_direction == DIRECTION_DOWN
    assert fy2025.percentage_change < Decimal("-4.4")


def test_trace_rejects_private_or_false_pit_claims():
    payload = _payload()
    payload["actual_entry_present"] = True
    with pytest.raises(ValueError, match="cannot contain an actual entry"):
        from_payload(payload)

    payload = _payload()
    payload["human_decision"] = "CONFIRM_BUY"
    with pytest.raises(ValueError, match="cannot contain a human decision"):
        from_payload(payload)

    payload = _payload()
    payload["baseline"]["strict_contemporaneous_rule_pit"] = True
    with pytest.raises(ValueError, match="cannot claim strict PIT"):
        from_payload(payload)

    payload = _payload()
    payload["action"] = "buy"
    with pytest.raises(ValueError, match="must remain no_order"):
        from_payload(payload)


def test_trace_rejects_unknown_references_and_chronology_errors():
    payload = _payload()
    payload["comparisons"][0]["observation_id"] = "missing-observation"
    with pytest.raises(ValueError, match="unknown observation"):
        from_payload(payload)

    payload = _payload()
    payload["disclosures"][0]["available_at"] = "2024-06-20T00:00:00+08:00"
    with pytest.raises(ValueError, match="cannot predate"):
        from_payload(payload)

    payload = _payload()
    payload["evidence_references"] = payload["evidence_references"][:-1]
    with pytest.raises(ValueError, match="unknown evidence"):
        from_payload(payload)


def test_workbook_shows_reconstructed_boundary_without_order_fields():
    workbook = build_reconstructed_evidence_workbook(_trace())

    assert workbook.sheetnames == [
        BOUNDARY_SHEET,
        "01_历史基准",
        DISCLOSURE_SHEET,
        COMPARISON_SHEET,
        CONCLUSION_SHEET,
        SOURCE_SHEET,
    ]
    text = _all_text(workbook)
    assert "RECONSTRUCTED_EVIDENCE_ONLY" in text
    assert "no_order" in text
    assert "追溯扩展，不是同期规则" in text
    assert "目标仓位" not in text
    assert "下单" not in text
    assert "自动卖出" not in text
    assert "买入" not in text
    assert "加仓" not in text


def test_writer_is_hash_pinned_and_never_overwrites(tmp_path):
    trace = _trace()
    result = write_reconstructed_evidence_workbook(
        trace,
        output=tmp_path / "reconstructed.xlsx",
        root=tmp_path,
    )

    target = tmp_path / result["workbook_path"]
    assert target.is_file()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == result["workbook_sha256"]
    assert result["trace_sha256"] == trace.trace_sha256
    assert result["action"] == ACTION_NO_ORDER

    with pytest.raises(ValueError, match="already exists"):
        write_reconstructed_evidence_workbook(
            trace,
            output=tmp_path / "reconstructed.xlsx",
            root=tmp_path,
        )


def test_payload_round_trip_preserves_trace_hash():
    payload = _payload()
    trace = from_payload(payload)
    restored = json.loads(trace.to_json())

    assert restored["trace_id"] == payload["trace_id"]
    assert restored["comparisons"] == payload["comparisons"]
    assert from_payload(restored).trace_sha256 == trace.trace_sha256
