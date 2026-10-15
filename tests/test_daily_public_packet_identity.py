"""TL10-RC: one publication identity over every content-deciding input.

These tests pin the TL10-A contract: the daily public packet mints a new
``publication_id`` whenever the verified publication chain, the registered
quote or evidence inputs, the engine revision or the business clock change,
while read-time stamps such as ``generated_at`` and ``excel_sync`` never do.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from value_investment_agent.application.product import daily_public_packet
from value_investment_agent.application.product.daily_public_packet import (
    build_daily_public_packet,
    packet_content_sha256,
)


NOW = datetime(2026, 10, 13, 4, 0, tzinfo=timezone.utc)


def _write_bytes(root: Path, path: str, raw: bytes) -> dict:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return {"path": path, "sha256": hashlib.sha256(raw).hexdigest()}


def _write_json(root: Path, path: str, value) -> dict:
    return _write_bytes(root, path, json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))


def _build(root: Path) -> dict:
    packet = build_daily_public_packet(root, generated_at=NOW)
    assert packet["packet_status"] == "CURRENT", packet.get("chain_error")
    assert packet["publication_id"].startswith("pub-")
    return packet


def build_verified_tree(root: Path) -> Path:
    """A minimal, fully verified publication chain under ``root``.

    Mirrors the shipped layout: the trial-workbook pointer leads to the
    receipt -> sources -> handoff -> read-model chain, the daily state is
    hash-bound and one explanation binding exists for 600519.
    """
    extensions = {
        "value_research_queue": {
            "schema_version": "value-research-queue-v1", "action": "no_order",
            "admission": "RESEARCH_QUEUE_ONLY", "as_of": "2026-10-12",
            "entries": [{"symbol": "002612", "company_name": "Lead",
                         "queue_status": "SELECTED_FOR_DATA_CHECK"}],
        }
    }
    bindings = {role: _write_json(root, f"runtime/{role}.json",
                                  dict(value, semantic_content=value))
                for role, value in extensions.items()}
    explanation = _write_json(root, "runtime/600519-value-decision-explanation.json", {
        "schema_version": "public-value-decision-explanation-v1", "symbol": "600519",
        "action": "no_order", "candidate_explanation": "Pending evidence",
        "blockers": ["G3"]})
    snapshot = {
        "action": "no_order", "as_of": "2026-10-12",
        "companies": [{"symbol": "600519", "company_name": "贵州茅台", "action": "no_order"}],
        "opportunities": [],
    }
    model = {
        "schema_version": "historical-company-read-model-preview-v1", "action": "no_order",
        "snapshot": snapshot, "product_extensions": bindings,
        "additional_evidence_bindings": [explanation],
        "historical_preview": True, "canonical_written": False,
    }
    model_binding = _write_json(root, "runtime/model.json", model)
    handoff = _write_json(root, "runtime/handoff.json", {
        "schema_version": "research-publication-input-v1", "action": "no_order",
        "snapshot": snapshot, "read_model_binding": model_binding})
    sources = _write_json(root, "runtime/sources.json", {
        "schema_version": "existing-workbench-preview-bindings-v1",
        "publication_input_binding": handoff})
    receipt = _write_json(root, "runtime/publication.json", {
        "schema_version": "canonical-reviewed-research-publication-v1",
        "canonical_written": True,
        "source_bindings_path": sources["path"], "source_bindings_sha256": sources["sha256"]})
    state = _write_json(root, "runtime/state.json", {
        "action": "no_order", "content": {"extensions": extensions}})
    _write_json(root, "config/current-trial-workbook.json", {
        "schema_version": "m7-current-trial-workbook-v5", "action": "no_order",
        "current_publication": {
            "status": "PUBLISHED_WPS_READONLY_VERIFIED",
            "receipt": receipt["path"], "receipt_sha256": receipt["sha256"]},
        "daily_product_state_binding": state})
    return root


def _write_registry(root: Path, evidence: dict | None) -> dict:
    entry = {
        "name": "华域汽车", "status": "PENDING_RESEARCH", "valuation_route": "fcff",
        "summary": "已登记待研究", "missing_inputs": ["估值输入未注册"],
        "required_actor": "ENGINEERING", "next_step": "补齐输入后再评估",
        "evidence": [evidence] if evidence else [],
    }
    return _write_json(root, "config/current-company-research-registry.json", {
        "schema_version": "current-company-research-registry-v1", "action": "no_order",
        "companies": {"600741": entry}})


def _register_quote(root: Path, symbol: str = "600887") -> dict:
    bundle = _write_json(root, f"runtime/quote-bundle-{symbol}.json", {"sources": []})
    package = _write_json(root, f"runtime/research-package-{symbol}.json", {
        "symbol": symbol, "package_version": "tl10-test",
        "point_in_time": {"research_as_of": "2026-10-11"}})
    _write_json(root, "config/current-quote-bridge.json", {
        "schema_version": "current-quote-bridge-v1", "action": "no_order",
        "registered_at": "2026-10-13T00:00:00+00:00",
        "quotes": {symbol: {
            "quote_bundle": bundle["path"], "quote_bundle_sha256": bundle["sha256"],
            "research_package": package["path"],
            "research_package_sha256": package["sha256"],
            "registered_at": "2026-10-13T00:00:00+00:00"}}})
    return bundle


def test_identity_inputs_cover_the_chain_and_the_business_clock(tmp_path):
    root = build_verified_tree(tmp_path)
    packet = _build(root)
    inputs = packet["identity_inputs"]
    assert inputs["schema"] == "daily-public-packet-identity-v9"
    assert inputs["engine"] == packet["engine_version"]
    assert inputs["natural_date"] == "2026-10-13"
    assert {item["role"] for item in inputs["chain"]} == {
        "publication_receipt", "publication_sources", "publication_handoff",
        "read_model", "daily_product_state"}
    assert all(item["sha256"] for item in inputs["chain"])
    assert inputs["quote_bridge_pointer"] == {
        "path": "config/current-quote-bridge.json", "observed_sha256": None}
    assert inputs["research_registry"] is None
    assert inputs["quote_bundles"] == []
    assert inputs["registered_evidence"] == []
    explanation = root / "runtime/600519-value-decision-explanation.json"
    assert inputs["bound_explanations"] == [
        {"path": "runtime/600519-value-decision-explanation.json",
         "observed_sha256": hashlib.sha256(explanation.read_bytes()).hexdigest()}]


def test_same_business_day_keeps_the_identity_and_next_day_mints_a_new_one(tmp_path):
    root = build_verified_tree(tmp_path)
    morning = _build(root)
    evening = build_daily_public_packet(
        root, generated_at=datetime(2026, 10, 13, 10, 30, tzinfo=timezone.utc))
    tomorrow = build_daily_public_packet(
        root, generated_at=datetime(2026, 10, 14, 4, 0, tzinfo=timezone.utc))
    assert evening["packet_status"] == "CURRENT"
    assert evening["publication_id"] == morning["publication_id"]
    assert tomorrow["publication_id"] != morning["publication_id"]
    assert morning["identity_inputs"]["natural_date"] == "2026-10-13"
    assert tomorrow["identity_inputs"]["natural_date"] == "2026-10-14"


def test_research_registry_content_mints_a_new_identity(tmp_path):
    root = build_verified_tree(tmp_path)
    before = _build(root)
    assert before["identity_inputs"]["research_registry"] is None
    evidence = _write_json(root, "docs/current/tl10-registry-evidence.json", {"receipt": "v1"})
    registry = _write_registry(root, evidence)
    after = _build(root)
    assert after["publication_id"] != before["publication_id"]
    assert after["identity_inputs"]["research_registry"] == {
        "path": "config/current-company-research-registry.json",
        "observed_sha256": registry["sha256"]}
    assert "600741" in after["company_statuses"]


def test_registered_evidence_change_mints_a_new_identity(tmp_path):
    root = build_verified_tree(tmp_path)
    evidence = _write_json(root, "docs/current/tl10-registry-evidence.json", {"receipt": "v1"})
    _write_registry(root, evidence)
    before = _build(root)
    changed = _write_json(root, "docs/current/tl10-registry-evidence.json", {"receipt": "v2"})
    after = _build(root)
    assert after["publication_id"] != before["publication_id"]
    observed = {item["path"]: item["observed_sha256"]
                for item in after["identity_inputs"]["registered_evidence"]}
    assert observed["docs/current/tl10-registry-evidence.json"] == changed["sha256"]
    assert set(after["company_statuses"]["600741"]["blockers"]) == {
        "RESEARCH_ASSESSMENT_NOT_BOUND", "VALUATION_NOT_ADMITTED", "REGISTERED_EVIDENCE_CHANGED"}
    assert "REGISTERED_EVIDENCE_CHANGED:600741" in after["blockers"]
    assert "REGISTERED_EVIDENCE_CHANGED:600741" not in before["blockers"]


def test_partial_registry_without_bound_assessment_exposes_research_gaps_and_engineering_work(tmp_path):
    root = build_verified_tree(tmp_path)
    _write_registry(root, None)
    path = root / "config/current-company-research-registry.json"
    registry = json.loads(path.read_bytes())
    partial = registry["companies"]["600741"]
    partial["status"] = "PARTIAL"
    registry["companies"] = {symbol: dict(partial) for symbol in ("000333", "000651", "600741")}
    _write_json(root, path.relative_to(root).as_posix(), registry)
    packet = _build(root)
    assert packet["engine_version"] == daily_public_packet.ENGINE_VERSION
    for symbol in registry["companies"]:
        entry = packet["company_statuses"][symbol]
        assert {"RESEARCH_ASSESSMENT_NOT_BOUND", "VALUATION_NOT_ADMITTED"} <= set(entry["blockers"])
        work = next(item for item in entry["pending_actions"] if item["code"] == "BIND_CURRENT_RESEARCH_ASSESSMENT")
        assert work["actor"] == "ENGINEERING"
        assert "不代表不存在历史研究" in work["label"]
        fallback = packet["value_price_conditions"][symbol]
        assert set(entry["blockers"]) <= set(fallback["blockers"])
        assert fallback["required_confirmations"] == fallback["blockers"]
        assert work["label"] in fallback["next_observation"]
        assert "不是仅缺行情" in fallback["explanation"]
        assert fallback["action_eligibility"] is False


def test_f3_engine_revision_mints_new_identity(tmp_path, monkeypatch):
    root = build_verified_tree(tmp_path)
    current = _build(root)
    monkeypatch.setattr(daily_public_packet, "ENGINE_VERSION", "daily-public-packet-engine-v10")
    previous = _build(root)
    assert current["publication_id"] != previous["publication_id"]


def test_quote_bundle_content_mints_a_new_identity(tmp_path):
    root = build_verified_tree(tmp_path)
    bundle = _register_quote(root)
    before = _build(root)
    changed = _write_json(root, bundle["path"], {"sources": ["changed"]})
    after = _build(root)
    assert after["publication_id"] != before["publication_id"]
    observed = {(item["role"], item["path"]): item["observed_sha256"]
                for item in after["identity_inputs"]["quote_bundles"]}
    assert observed[("quote_bundle:600887", bundle["path"])] == changed["sha256"]
    assert "SOURCE_BINDING_HASH_MISMATCH:quote_bundle:600887" in after["blockers"]


def test_bound_explanation_content_mints_a_new_identity(tmp_path):
    root = build_verified_tree(tmp_path)
    before = _build(root)
    assert before["company_statuses"]["600519"]["blockers"] == []
    path = "runtime/600519-value-decision-explanation.json"
    changed = _write_json(root, path, {
        "schema_version": "public-value-decision-explanation-v1",
        "symbol": "600519", "action": "no_order",
        "candidate_explanation": "drifted", "blockers": ["G3"]})
    after = _build(root)
    assert after["publication_id"] != before["publication_id"]
    assert after["identity_inputs"]["bound_explanations"] == [
        {"path": path, "observed_sha256": changed["sha256"]}]
    assert ("VALUE_EXPLANATION_BINDING_UNAVAILABLE"
            in after["company_statuses"]["600519"]["blockers"])
    assert ("VALUE_EXPLANATION_BINDING_UNAVAILABLE"
            not in before["company_statuses"]["600519"]["blockers"])


def test_engine_version_mints_a_new_identity(tmp_path, monkeypatch):
    root = build_verified_tree(tmp_path)
    before = _build(root)
    monkeypatch.setattr(daily_public_packet, "ENGINE_VERSION",
                        "daily-public-packet-engine-v2-tl10-test")
    after = _build(root)
    assert after["publication_id"] != before["publication_id"]
    assert after["engine_version"] == "daily-public-packet-engine-v2-tl10-test"
    assert after["identity_inputs"]["engine"] == "daily-public-packet-engine-v2-tl10-test"


def test_packet_content_digest_ignores_stamps_and_covers_decisions():
    base = {
        "schema_version": "daily-public-packet-v1", "engine_version": "engine",
        "action": "no_order", "publication_id": "pub-base",
        "generated_at": "2026-10-13T04:00:00+00:00",
        "generated_at_china": "2026-10-13T12:00:00+08:00",
        "content_sha256": None, "excel_sync": {"status": "NOT_VERIFIED"},
        "blockers": ["NO_FORMAL_ADMISSION"],
        "dates": {"research_as_of": "2026-10-12"},
        "company_statuses": {},
    }
    recomposed = {
        **base,
        "generated_at": "2026-10-13T09:59:59+00:00",
        "generated_at_china": "2026-10-13T17:59:59+08:00",
        "content_sha256": "stale-digest-of-another-run",
        "excel_sync": {"status": "MATCHED", "checked_at": "later"},
    }
    assert packet_content_sha256(base) == packet_content_sha256(recomposed)
    moved = {**base, "blockers": ["NO_FORMAL_ADMISSION", "PRICE_NOT_ADMITTED:600887"]}
    assert packet_content_sha256(moved) != packet_content_sha256(base)
    dated = {**base, "dates": {"research_as_of": "2026-10-13"}}
    assert packet_content_sha256(dated) != packet_content_sha256(base)
