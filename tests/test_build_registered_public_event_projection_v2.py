from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT_PATH = ROOT / "scripts/cases/build_registered_public_event_projection_v2.py"
SPEC = importlib.util.spec_from_file_location("registered_public_event_builder_v2", SCRIPT_PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def _notice_input(tmp_path: Path, *, event_id: str | None = None) -> tuple[Path, str]:
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True)
    original = runtime / "1225582141.PDF"
    original.write_bytes(b"pinned original notice bytes")
    evidence_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    notice_event_id = event_id or "midea-2026-egm-notice-1225582141"
    evidence_id = "cninfo-1225582141"
    payload = {
        "action": "no_order",
        "report": {
            "schema_version": builder.NOTICE_SCHEMA,
            "symbol": "000333",
            "announcement_id": builder.NOTICE_ID,
            "announcement_date": builder.NOTICE_DATE,
            "valuation_or_trade_conclusion_changed": False,
        },
        "projection": {
            "action": "no_order",
            "events": [{
                "event_id": notice_event_id,
                "event_type": "MATERIAL_RISK_MONITOR",
                "company_name": "美的集团",
                "what_happened": "程序性股东会通知，议案尚未表决或实施。",
                "impact_area": "治理与资本配置后续跟踪",
                "current_conclusion": "不改变估值或交易结论",
                "research_action": "MONITOR",
                "next_step": "等待正式决议及实施证据",
                "evidence_refs": [evidence_id],
                "action": "no_order",
            }],
            "audit_evidence": [{
                "evidence_id": evidence_id,
                "title": "关于召开2026年第一次临时股东会的通知",
                "artifact_type": "cninfo_original_pdf",
                "path": "runtime/1225582141.PDF",
                "sha256": evidence_hash,
                "available_at": builder.NOTICE_DATE,
                "action": "no_order",
                "source_url": builder.NOTICE_URL,
            }],
            "audit_decisions": [{
                "event_id": notice_event_id,
                "state": "material_risk_monitor",
                "visible": True,
                "disposition": "MATERIAL_RISK_MONITOR",
                "evidence_refs": [evidence_id],
                "action": "no_order",
            }],
        },
    }
    projection_path = runtime / "midea-notice-projection.json"
    projection_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return projection_path, hashlib.sha256(projection_path.read_bytes()).hexdigest()


def _build(tmp_path: Path, notice_path: Path, pinned_hash: str, monkeypatch):
    load_notice = builder._load_notice_projection
    monkeypatch.setattr(
        builder,
        "_load_notice_projection",
        lambda _repository_root, path, digest: load_notice(tmp_path, path, digest),
    )
    return builder.build_projection_payload(
        ROOT,
        notice_projection_path=notice_path,
        notice_projection_sha256=pinned_hash,
    )


def test_combines_eight_base_events_with_one_pinned_notice_and_preserves_v1_rows(tmp_path, monkeypatch):
    from scripts.cases.build_registered_public_event_projection import build_projection_payload

    base = build_projection_payload(ROOT)
    notice_path, pinned_hash = _notice_input(tmp_path)
    result = _build(tmp_path, notice_path, pinned_hash, monkeypatch)

    assert result["report"]["schema_version"] == "registered-public-event-projection-v2"
    assert len(result["projection"]["events"]) == 9
    for key in ("events", "audit_evidence", "audit_decisions"):
        assert result["projection"][key][:len(base["projection"][key])] == base["projection"][key]
    evidence = result["projection"]["audit_evidence"][-1]
    assert evidence["source_url"] == builder.NOTICE_URL
    assert evidence["sha256"] == hashlib.sha256((tmp_path / "runtime/1225582141.PDF").read_bytes()).hexdigest()
    report = result["report"]
    assert report["appended_observation"]["scope"] == "ONE_EXACT_ISSUER_CNINFO_OBSERVATION_ONLY"
    assert report["formal_watermark_advanced"] is False
    assert report["continuous_coverage_claimed"] is False
    assert report["multi_channel_coverage_claimed"] is False
    assert report["strict_pit_proven"] is False
    assert report["valuation_or_trade_conclusion_changed"] is False
    assert result["action"] == "no_order"


@pytest.mark.parametrize("mutation,match", [
    ("issuer", "issuer must be 000333"),
    ("schema", "schema"),
    ("extra_event", "exactly one"),
    ("valuation", "leave valuation"),
    ("evidence_hash", "original evidence SHA-256 mismatch"),
])
def test_notice_validation_fails_closed(tmp_path, mutation, match):
    notice_path, _ = _notice_input(tmp_path)
    payload = json.loads(notice_path.read_text(encoding="utf-8"))
    if mutation == "issuer":
        payload["report"]["symbol"] = "600887"
    elif mutation == "schema":
        payload["report"]["schema_version"] = "registered-public-event-projection-v1"
    elif mutation == "extra_event":
        payload["projection"]["events"].append(dict(payload["projection"]["events"][0], event_id="extra"))
    elif mutation == "valuation":
        payload["report"]["valuation_or_trade_conclusion_changed"] = True
    elif mutation == "evidence_hash":
        payload["projection"]["audit_evidence"][0]["sha256"] = "0" * 64
    notice_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    new_hash = hashlib.sha256(notice_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match=match):
        builder._load_notice_projection(tmp_path, notice_path, new_hash)


def test_rejects_projection_hash_mismatch_path_outside_runtime_and_duplicate_ids(tmp_path, monkeypatch):
    notice_path, pinned_hash = _notice_input(tmp_path)
    with pytest.raises(ValueError, match="projection SHA-256 mismatch"):
        builder._load_notice_projection(tmp_path, notice_path, "0" * 64)

    outside = tmp_path / "outside.json"
    outside.write_bytes(notice_path.read_bytes())
    with pytest.raises(ValueError, match="under repository runtime"):
        builder._load_notice_projection(tmp_path, outside, pinned_hash)

    duplicate_path, duplicate_hash = notice_path, pinned_hash
    from scripts.cases import build_registered_public_event_projection as base_builder

    original_build = base_builder.build_projection_payload

    def duplicate_base_event(repository_root):
        payload = original_build(repository_root)
        payload["projection"]["events"].append({
            "event_id": "midea-2026-egm-notice-1225582141",
        })
        return payload

    monkeypatch.setattr(base_builder, "build_projection_payload", duplicate_base_event)
    with pytest.raises(ValueError, match="Duplicate or empty identity"):
        _build(tmp_path, duplicate_path, duplicate_hash, monkeypatch)


def test_v1_builder_output_is_unchanged():
    from scripts.cases.build_registered_public_event_projection import build_projection_payload

    first = build_projection_payload(ROOT)
    second = build_projection_payload(ROOT)
    assert first == second
    assert first["report"]["schema_version"] == "registered-public-event-projection-v1"
    assert len(first["projection"]["events"]) == 8
