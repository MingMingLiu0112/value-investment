from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from fastapi.testclient import TestClient

from value_investment_agent.presentation.web_api.app import create_app


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _canonical_digest(payload: dict) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(raw).hexdigest()


def _fixture(root: Path) -> Path:
    audit_dir = root / "artifacts/current/research-funnel-audit-fixture"
    audit_dir.mkdir(parents=True)
    result = {
        "schema_version": "research-funnel-audit-v1",
        "task_id": "W6-FUNNEL-AUDIT-V1",
        "action": "no_order",
        "trade_intent": "NO_TRADE",
        "admission": "READ_ONLY_AUDIT",
        "as_of": "2026-10-12",
        "universe_count": 3,
        "industry_count": 3,
        "market_snapshot_count": 3,
        "lead_count": 2,
        "dividend_evidence_count": 1,
        "same_period_complete_symbol_count": 0,
        "financial": {"point_count": 18, "symbol_count": 2},
        "quality_effective_status_counts": {
            "PASS": 0,
            "DATA_GAP": 2,
            "INSUFFICIENT_EVIDENCE": 1,
        },
        "capital_return_roic": {
            "available": False,
            "status": "UNAVAILABLE",
            "reason": "No accepted capital-return facts.",
        },
        "quote": {
            "quote_date": "2026-10-12",
            "trade_date_verified": False,
            "verified_quote_count": 0,
            "unverified_quote_count": 3,
        },
        "queue": {
            "entry_count": 2,
            "selected_count": 1,
            "deferred_count": 1,
            "selected_symbols": ["000001"],
        },
        "channels": {
            "quality": {
                "effective_status_counts": {
                    "PASS": 0,
                    "DATA_GAP": 2,
                    "INSUFFICIENT_EVIDENCE": 1,
                },
                "top_reasons": [{"reason": "缺少同一报告期证据"}],
            },
            "value": {
                "effective_status_counts": {"PASS": 1, "REJECTED": 2},
                "top_reasons": [{"reason": "估值偏高"}],
            },
            "dividend_cash_return": {
                "effective_status_counts": {"PASS": 1, "NOT_EVALUATED": 2},
                "top_reasons": [{"reason": "没有分红记录"}],
            },
            "cyclical": {
                "effective_status_counts": {"PASS": 0, "DATA_GAP": 3},
                "top_reasons": [{"reason": "缺少 PE/PB"}],
            },
        },
        "human_review": {"status": "HUMAN_REVIEW_PENDING"},
        "source_files": {
            "official": {"path": "runtime/official.json", "sha256": "a" * 64}
        },
    }
    result["audit_sha256"] = _canonical_digest(result)
    packet = {
        "schema_version": "research-funnel-human-review-packet-v1",
        "action": "no_order",
        "approved": False,
        "review_status": "HUMAN_REVIEW_PENDING",
        "source_audit_sha256": result["audit_sha256"],
        "sample": [
            {
                "symbol": "000001",
                "company_name": "示例公司",
                "industry": "制造业",
                "channels": ["value"],
                "research_state": "DATA_CHECK",
                "gaps": ["QUOTE_DATE_UNVERIFIED"],
            }
        ],
    }
    packet["packet_sha256"] = _canonical_digest(packet)

    result_path = audit_dir / "result.json"
    report_path = audit_dir / "report.md"
    packet_path = audit_dir / "human-review-packet.json"
    _write(result_path, result)
    report_path.write_text("# fixture audit\n", encoding="utf-8")
    _write(packet_path, packet)

    manifest = {
        "schema_version": "research-funnel-audit-manifest-v1",
        "task_id": "W6-FUNNEL-AUDIT-V1",
        "action": "no_order",
        "trade_intent": "NO_TRADE",
        "review_status": "HUMAN_REVIEW_PENDING",
        "audit_sha256": result["audit_sha256"],
        "packet_sha256": packet["packet_sha256"],
        "source_hashes": {"official": "a" * 64},
        "outputs": {
            path.name: {
                "path": path.relative_to(root).as_posix(),
                "sha256": _digest(path),
            }
            for path in (result_path, report_path, packet_path)
        },
    }
    manifest_path = audit_dir / "manifest.json"
    _write(manifest_path, manifest)
    _write(
        root / "config/current-research-funnel-audit.json",
        {
            "schema_version": "current-research-funnel-audit-v1",
            "action": "no_order",
            "status": "VERIFIED",
            "manifest_path": manifest_path.relative_to(root).as_posix(),
            "manifest_sha256": _digest(manifest_path),
        },
    )
    return result_path


def test_research_funnel_api_serves_a_verified_no_order_projection(tmp_path):
    _fixture(tmp_path)
    response = TestClient(create_app(tmp_path)).get("/api/v1/research-funnel-status")
    body = response.json()

    assert response.status_code == 200
    assert body["schema_version"] == "public-research-funnel-status-v1"
    assert body["action"] == "no_order"
    assert body["status"] == "VERIFIED"
    assert body["universe"]["securities"] == 3
    assert body["evidence"]["quality_pass"] == 0
    assert body["quote"]["trade_date_verified"] is False
    assert body["queue"]["selected_count"] == 1
    assert body["sample"][0]["symbol"] == "000001"
    assert body["blockers"] == [
        "QUOTE_DATE_UNVERIFIED",
        "QUALITY_ZERO_PASS",
        "CAPITAL_RETURN_UNAVAILABLE",
        "HUMAN_REVIEW_PENDING",
        "QUEUE_IS_DATA_CHECK_ONLY",
    ]
    assert body["artifacts"]["manifest"]["path"].endswith("manifest.json")


def test_research_funnel_api_fails_closed_on_tampered_result(tmp_path):
    result_path = _fixture(tmp_path)
    result_path.write_text("{}\n", encoding="utf-8")

    body = TestClient(create_app(tmp_path)).get("/api/v1/research-funnel-status").json()

    assert body["action"] == "no_order"
    assert body["status"] == "INVALID"
    assert body["reason"] == "FUNNEL_OUTPUT_HASH_MISMATCH"
    assert body["universe"] is None
    assert body["sample"] == []


def test_research_funnel_api_fails_closed_on_tampered_report(tmp_path):
    _fixture(tmp_path)
    report_path = tmp_path / "artifacts/current/research-funnel-audit-fixture/report.md"
    report_path.write_text("# changed\n", encoding="utf-8")

    body = TestClient(create_app(tmp_path)).get("/api/v1/research-funnel-status").json()

    assert body["status"] == "INVALID"
    assert body["reason"] == "FUNNEL_OUTPUT_HASH_MISMATCH"
    assert body["evidence"] is None


def test_research_funnel_api_reports_missing_pointer_without_inventing_data(tmp_path):
    body = TestClient(create_app(tmp_path)).get("/api/v1/research-funnel-status").json()

    assert body["status"] == "UNAVAILABLE"
    assert body["reason"] == "FUNNEL_POINTER_MISSING"
    assert body["queue"] is None
