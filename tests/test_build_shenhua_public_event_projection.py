import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts/cases/build_shenhua_public_event_projection.py"
SPEC = importlib.util.spec_from_file_location("shenhua_projection_builder", SCRIPT_PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def _isolated_evidence_root(tmp_path):
    for source in builder.EVIDENCE_SOURCES:
        original = builder.REPOSITORY_ROOT / source["path"]
        target = tmp_path / source["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
    return tmp_path


def test_builds_all_bounded_events_with_pinned_evidence_and_no_order(tmp_path):
    v1_path = builder.REPOSITORY_ROOT / "runtime/prospective-public-event-20260927/shenhua-finance-risk-projection-v1.json"
    v2_path = builder.REPOSITORY_ROOT / "runtime/prospective-public-event-20260927/shenhua-event-projection-v2.json"
    old_projection_bytes = (v1_path.read_bytes(), v2_path.read_bytes())

    payload = builder.build_projection_payload()

    assert payload["report"]["schema_version"] == "shenhua-public-event-projection-v1"
    assert payload["report"]["strict_pit_proven"] is False
    assert payload["report"]["source_time_independently_certified"] is False
    assert payload["report"]["valuation_or_trade_conclusion_changed"] is False
    assert payload["report"]["action"] == payload["action"] == "no_order"
    events = payload["projection"]["events"]
    decisions = payload["projection"]["audit_decisions"]
    assert {event["event_id"] for event in events} == {source["event_id"] for source in builder.EVENT_SOURCES}
    assert {row["event_id"]: row["state"] for row in decisions} == {
        "cninfo-601088-1225546779-1225579981-interim-distribution": "material_supporting_evidence",
        "cninfo-601088-1225565223-2026-08-operations": "material_risk_monitor",
        "cninfo-601088-1225185584": "material_risk_monitor",
        "cninfo-601088-1225579956": "material_risk_monitor",
    }
    assert all(row["visible"] for row in decisions)
    assert all(row["action"] == "no_order" for row in decisions)
    assert all(row["action"] == "no_order" for row in events)
    assert {row["sha256"] for row in payload["projection"]["audit_evidence"]} == {
        source["sha256"] for source in builder.EVIDENCE_SOURCES
    }
    unlock = next(event for event in events if event["event_id"] == "cninfo-601088-1225579956")
    assert "2026-10-08" in unlock["what_happened"]
    assert "457,665,903" in unlock["what_happened"]
    assert "2.11%" in unlock["what_happened"]
    assert "不是新增发行" in unlock["what_happened"]
    assert "不是卖出信号" in unlock["what_happened"]
    assert any("发行人自评" in text for text in payload["report"]["limitations"])
    assert any("严格PIT" in text for text in payload["report"]["limitations"])
    assert (v1_path.read_bytes(), v2_path.read_bytes()) == old_projection_bytes


@pytest.mark.parametrize("tamper", [True, False], ids=["tampered", "missing"])
def test_rejects_tampered_or_missing_source_pdf(tmp_path, tamper):
    root = _isolated_evidence_root(tmp_path)
    source = builder.EVIDENCE_SOURCES[-1]
    target = root / source["path"]
    if tamper:
        target.write_bytes(target.read_bytes() + b"tampered")
        expected_message = "SHA-256 mismatch"
    else:
        target.unlink()
        expected_message = "Missing source PDF"

    with pytest.raises(ValueError, match=expected_message):
        builder.build_projection_payload(root)


def test_write_is_exclusive_and_does_not_replace_prior_bytes(tmp_path):
    target = tmp_path / "shenhua-event-projection-v3.json"
    original = b'{"existing":"v2 bytes stay untouched"}\n'
    target.write_bytes(original)

    with pytest.raises(ValueError, match="Refusing to overwrite"):
        builder.write_new_json(target, {"new": True})

    assert target.read_bytes() == original


def test_projection_pdf_hashes_are_fixed_and_recomputed():
    payload = builder.build_projection_payload()
    evidence = {row["evidence_id"]: row for row in payload["projection"]["audit_evidence"]}
    for source in builder.EVIDENCE_SOURCES:
        path = builder.REPOSITORY_ROOT / source["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == source["sha256"] == evidence[source["evidence_id"]]["sha256"]
