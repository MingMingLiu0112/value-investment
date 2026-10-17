"""WEB-D2 P2: decision history is projected from real, recomputable artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
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
    # A declared source is reported with the status of its recomputed digest, and
    # a missing file is never presented as if the source had been verified.
    assert item["evidence"] == [{"path": "docs/current/example.md", "sha256": "d" * 64,
                                 "status": "MISSING"}]
    assert item["verification"]["rationale_bindings"] == {
        "status": "INCOMPLETE", "verified_count": 0, "total": 1}
    assert item["admission_effect"] == "NONE"
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


def test_rationale_bindings_are_recomputed_against_real_files(tmp_path):
    source = tmp_path / "docs/current/evidence.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("真实来源", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    payload = proposal("600887", choice="A_PRESSURE_REFERENCE", growth="0", groups=[], limits=[])
    payload["rationale_bindings"] = [{"path": "docs/current/evidence.md", "sha256": digest},
                                     {"path": "docs/current/absent.md", "sha256": "e" * 64}]
    write(tmp_path, "600887-20260101.json", payload)
    item = TestClient(create_app(tmp_path)).get("/api/v1/decision-history").json()["items"][0]
    verified, missing = item["evidence"]
    assert verified == {"path": "docs/current/evidence.md", "sha256": digest,
                        "status": "VERIFIED", "actual_sha256": digest}
    assert missing["status"] == "MISSING"
    assert item["verification"]["rationale_bindings"] == {
        "status": "INCOMPLETE", "verified_count": 1, "total": 2}

    source.write_text("被改动的来源", encoding="utf-8")
    item = TestClient(create_app(tmp_path)).get("/api/v1/decision-history").json()["items"][0]
    assert item["evidence"][0]["status"] == "HASH_MISMATCH"
    assert item["evidence"][0]["actual_sha256"] != digest


def test_source_package_digest_must_match_a_real_package(tmp_path):
    package = tmp_path / "config/m1-valuation-packages-v1/600887-quality-compounder.json"
    package.parent.mkdir(parents=True, exist_ok=True)
    package.write_text('{"schema_version":"m1-valuation-package-v1"}', encoding="utf-8")
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    payload = proposal("600887", choice="A_PRESSURE_REFERENCE", growth="0", groups=[], limits=[])
    payload["source_package_sha256"] = digest
    write(tmp_path, "600887-20260101.json", payload)
    package_row = TestClient(create_app(tmp_path)).get(
        "/api/v1/decision-history").json()["items"][0]["verification"]["source_package"]
    assert package_row == {"status": "VERIFIED", "declared_sha256": digest,
                           "artifact": "config/m1-valuation-packages-v1/600887-quality-compounder.json",
                           "sha256": digest}

    payload["source_package_sha256"] = "f" * 64
    write(tmp_path, "600887-20260102-v2.json", payload)
    package_row = TestClient(create_app(tmp_path)).get(
        "/api/v1/decision-history").json()["items"][0]["verification"]["source_package"]
    assert package_row == {"status": "NOT_FOUND", "declared_sha256": "f" * 64}


def test_published_decisions_stay_separate_from_proposals(tmp_path):
    digest = write(tmp_path, "600887-20260102-v2.json",
                   proposal("600887", choice="A_PRESSURE_REFERENCE", growth="0", groups=[], limits=[]))
    published = f"pending-600887-2026-01-02-A_PRESSURE_REFERENCE-{digest[:12]}"
    body = build_research_history(tmp_path, published_versions={"600887": published},
                                  published_decisions={"600887": {
                                      "research_version": published,
                                      "candidate_action": "NO_ACTION",
                                      "decision_cutoff": "2026-01-03",
                                      "artifact": "runtime/example-explanation.json",
                                      "sha256": "a" * 64}})
    history = body["published_decision_history"]
    assert history["status"] == "CURRENT_ONLY"
    assert history["history"] == []
    assert history["current_published_decisions"] == [{
        "symbol": "600887", "research_version": published, "candidate_action": "NO_ACTION",
        "decision_cutoff": "2026-01-03", "artifact": "runtime/example-explanation.json",
        "sha256": "a" * 64}]
    item = body["items"][0]
    assert item["published_decision"]["status"] == "CURRENT_PUBLICATION_ONLY"
    assert item["published_decision"]["decision_cutoff"] == "2026-01-03"
    assert item["timeline"]["proposal_available_at"] is None
    assert item["timeline"]["proposal_available_at_status"] == "NOT_RECORDED_IN_PROPOSAL"
    assert item["timeline"]["published_decision_cutoff"] == "2026-01-03"
    assert body["historical_reconstruction"]["status"] == "NOT_AVAILABLE"


def test_corrupt_proposal_is_reported_not_silently_dropped(tmp_path):
    write(tmp_path, "600519-20260101.json",
          proposal("600519", choice="A", growth="0", groups=[], limits=[]))
    bad = tmp_path / "config/research-proposals/600519-20260102-v2.json"
    bad.write_text("{not json", encoding="utf-8")
    wrong = tmp_path / "config/research-proposals/600519-20260103-v3.json"
    wrong.write_text(json.dumps({"schema_version": "other", "action": "no_order",
                                 "symbol": "600519"}), encoding="utf-8")
    body = TestClient(create_app(tmp_path)).get("/api/v1/decision-history").json()
    assert body["counts"] == {"symbols": 1, "versions": 1}
    assert body["skipped_proposals"] == [
        {"artifact": "config/research-proposals/600519-20260102-v2.json",
         "reason": "UNREADABLE_JSON"},
        {"artifact": "config/research-proposals/600519-20260103-v3.json",
         "reason": "UNKNOWN_SCHEMA"}]


def _published_runtime_artifacts_present() -> bool:
    """The verified publication lives under the git-ignored runtime/ tree.

    A bare source checkout keeps the pointer but not the receipt, so the live
    test skips instead of inventing a publication or treating its absence as a
    pass.
    """
    try:
        pointer = json.loads(
            (ROOT / "config" / "current-trial-workbook.json").read_text(encoding="utf-8"))
        receipt = pointer["current_publication"]["receipt"]
    except (OSError, KeyError, TypeError, ValueError):
        return False
    return isinstance(receipt, str) and (ROOT / receipt).is_file()


@pytest.mark.skipif(not _published_runtime_artifacts_present(),
                    reason="runtime publication artifacts are absent from this checkout")
def test_live_history_binds_real_published_decisions():
    body = TestClient(create_app(ROOT)).get("/api/v1/decision-history").json()
    assert body["status"] == "CONNECTED"
    assert body["published_decision_history"]["status"] == "CURRENT_ONLY"
    assert body["published_decision_history"]["history"] == []
    current = {row["symbol"]: row for row in
               body["published_decision_history"]["current_published_decisions"]}
    assert current["600887"]["candidate_action"] == "NO_ACTION"
    assert current["600887"]["decision_cutoff"] == "2026-10-11"
    item = next(row for row in body["items"] if row["symbol"] == "600887")
    assert item["published_decision"]["status"] == "CURRENT_PUBLICATION_ONLY"
    assert item["verification"]["source_package"]["status"] == "VERIFIED"
    assert item["verification"]["rationale_bindings"]["verified_count"] >= 1
    assert item["timeline"]["proposal_available_at_status"] == "NOT_RECORDED_IN_PROPOSAL"


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
