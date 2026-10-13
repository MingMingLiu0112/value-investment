"""WEB-D2 P2: decision history is projected from real, recomputable artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from value_investment_agent.presentation.read_models.research_history import build_research_history
from value_investment_agent.presentation.web_api.app import create_app

ROOT = Path(__file__).resolve().parents[2]


def proposal(symbol: str, *, choice: str, growth: str, groups: list[dict], limits: list[str]) -> dict:
    return {
        "schema_version": "finite-earnings-path-proposal-v1",
        "symbol": symbol,
        "action": "no_order",
        "source_package_sha256": "c" * 64,
        "profit_anchor_field": "ttm_ex_nonrecurring_parent_profit_cny",
        "profit_basis": "disclosed_proxy_not_verified",
        "income_growth": {"bear": "-0.05", "base": growth, "bull": "0.05"},
        "rationale_bindings": [{"path": "docs/current/example.md", "sha256": "d" * 64}],
        "choices": [{"id": choice}],
        "economic_review_items": ["是否可以用 TTM 作为利润锚？"],
        "human_review_groups": groups,
        "assurance_limits": limits,
        "research_preference": {
            "choice_id": choice, "scope": "INDEPENDENT_RESEARCH_HYPOTHESIS_NOT_APPROVAL",
            "confidence": "低", "reason": "真实提案理由", "countercase": "真实反证",
            "reopen_triggers": ["下一期经营性现金流", "渠道库存变化"],
        },
    }


def write(root: Path, name: str, payload: dict) -> str:
    directory = root / "config/research-proposals"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_history_without_real_artifacts_stays_not_connected(tmp_path):
    body = TestClient(create_app(tmp_path)).get("/api/v1/decision-history").json()
    assert body["action"] == "no_order"
    assert body["status"] == "NOT_CONNECTED"
    assert body["items"] == []


def test_two_real_versions_are_compared_field_by_field(tmp_path):
    old = proposal("600519", choice="A_PRESSURE_REFERENCE", growth="0",
                   groups=[], limits=["旧限制"])
    new = proposal("600519", choice="B_CONTINUITY_ALTERNATIVE", growth="0.02",
                   groups=[{"id": "EARNINGS", "question": "历史盈利能力是否可持续？",
                            "support": "支持", "countercase": "反例", "impact": "影响",
                            "field_paths": ["facts.operating_inputs"]}],
                   limits=["旧限制", "新限制"])
    write(tmp_path, "600519-20260101.json", old)
    digest = write(tmp_path, "600519-20260102-v2.json", new)
    body = TestClient(create_app(tmp_path)).get("/api/v1/decision-history").json()
    assert body["status"] == "CONNECTED"
    assert body["counts"] == {"symbols": 1, "versions": 2}
    item = body["items"][0]
    assert item["symbol"] == "600519"
    assert item["action"] == "no_order"
    assert item["candidate_action"] == "no_order"
    assert item["versions"][0]["version_label"] == "600519-20260102-v2"
    assert item["versions"][0]["sha256"] == digest
    assert item["versions"][1]["research_date"] == "20260101"
    assert item["attention"]["choice_id"] == "B_CONTINUITY_ALTERNATIVE"
    assert item["evidence"] == [{"path": "docs/current/example.md", "sha256": "d" * 64}]
    assert item["review_items"][0]["question"] == "历史盈利能力是否可持续？"
    comparison = item["comparison"]
    assert comparison["status"] == "COMPARED"
    assert comparison["observation"] == "EVIDENCE_UPDATED"
    assert comparison["admission_effect"] == "NONE"
    assert set(comparison["changed_fields"]) >= {"income_growth", "choices",
                                                "human_review_groups", "assurance_limits"}
    assert comparison["review_group_changes"] == {"added": ["EARNINGS"], "removed": [], "changed": []}
    assert comparison["from_version"] == "600519-20260101"
    assert comparison["to_version"] == "600519-20260102-v2"


def test_identical_versions_report_unchanged(tmp_path):
    payload = proposal("600887", choice="A_PRESSURE_REFERENCE", growth="0", groups=[], limits=[])
    write(tmp_path, "600887-20260101.json", payload)
    write(tmp_path, "600887-20260102-v2.json", payload)
    item = TestClient(create_app(tmp_path)).get("/api/v1/decision-history").json()["items"][0]
    assert item["comparison"]["observation"] == "UNCHANGED"
    assert item["comparison"]["changed_fields"] == []


def test_single_version_reports_previous_unavailable(tmp_path):
    write(tmp_path, "600887-20260101.json",
          proposal("600887", choice="A_PRESSURE_REFERENCE", growth="0", groups=[], limits=[]))
    item = TestClient(create_app(tmp_path)).get("/api/v1/decision-history").json()["items"][0]
    assert item["comparison"]["status"] == "PREVIOUS_UNAVAILABLE"
    assert item["comparison"]["observation"] == "UNKNOWN"
    assert item["comparison"]["changed_fields"] == []


def test_published_version_binding_is_explicit(tmp_path):
    digest = write(tmp_path, "600519-20260102-v2.json",
                   proposal("600519", choice="B_CONTINUITY_ALTERNATIVE", growth="0",
                            groups=[], limits=[]))
    published = f"pending-600519-2026-01-02-B_CONTINUITY_ALTERNATIVE-{digest[:12]}"
    body = build_research_history(tmp_path, published_versions={"600519": published})
    item = body["items"][0]
    assert item["published_research_version"] == published
    assert item["versions"][0]["bound_to_current_publication"] is True


def test_live_600519_series_hashes_are_recomputable():
    body = TestClient(create_app(ROOT)).get("/api/v1/decision-history").json()
    assert body["status"] == "CONNECTED"
    item = next(row for row in body["items"] if row["symbol"] == "600519")
    assert len(item["versions"]) >= 3
    for row in item["versions"]:
        raw = (ROOT / row["artifact"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]
    assert item["comparison"]["status"] == "COMPARED"
    assert item["comparison"]["admission_effect"] == "NONE"
