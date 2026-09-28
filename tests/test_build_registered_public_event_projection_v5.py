from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT_PATH = ROOT / "scripts/cases/build_registered_public_event_projection_v5.py"
SPEC = importlib.util.spec_from_file_location("registered_public_event_builder_v5", SCRIPT_PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def _case_repo(tmp_path: Path) -> Path:
    for relative in (builder.PREDECESSOR_PATH, builder.SOURCE_PATH):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return tmp_path


def test_v5_binds_future_source_to_audit_only_quarantine_without_reintroducing_event(tmp_path):
    root = _case_repo(tmp_path)
    result = builder.build_projection_payload(root)
    projection = result["projection"]
    report = result["report"]
    excluded = projection["as_of_excluded_evidence"]

    assert report["schema_version"] == "registered-public-event-projection-v5"
    assert report["successor_of"] == "registered-public-event-projection-v4"
    assert report["predecessor_sha256"] == builder.PREDECESSOR_SHA256
    assert report["source_evidence_sha256"] == builder.SOURCE_SHA256
    assert report["as_of_excluded_evidence_count"] == 1
    assert len(projection["events"]) == 8
    assert len(projection["audit_decisions"]) == 8
    assert len(projection["audit_evidence"]) == 10
    assert len(excluded) == 1
    assert excluded[0]["evidence"]["evidence_id"] == "cninfo-1225582141"
    assert excluded[0]["evidence"]["available_at"] == "2026-09-29"
    assert excluded[0]["evidence"]["sha256"] == "94629a0271834020e0a1efd417837bbd04677f226650d940b4a6d523a26e9686"
    assert excluded[0]["reason"] == "SOURCE_NOT_AVAILABLE_AS_OF_CUTOFF"
    assert excluded[0]["related_event_ids"] == ["midea-2026-egm-notice-1225582141"]
    assert "cninfo-1225582141" not in {
        row["evidence_id"] for row in projection["audit_evidence"]
    }
    assert "midea-2026-egm-notice-1225582141" not in {
        row["event_id"] for row in projection["events"] + projection["audit_decisions"]
    }
    assert report["strict_pit_proven"] is False
    assert report["valuation_or_trade_conclusion_changed"] is False
    assert result["action"] == "no_order"


@pytest.mark.parametrize("relative", ["v4", "v3"])
def test_v5_rejects_tampered_projection_chain(tmp_path, relative):
    root = _case_repo(tmp_path)
    path = root / (builder.PREDECESSOR_PATH if relative == "v4" else builder.SOURCE_PATH)
    path.write_bytes(path.read_bytes() + b"tampered")

    label = "v4 predecessor" if relative == "v4" else "v3 source closure"
    with pytest.raises(ValueError, match=f"{label} SHA-256 mismatch"):
        builder.build_projection_payload(root)


def test_v5_writer_refuses_to_overwrite_existing_successor(tmp_path):
    root = _case_repo(tmp_path)
    output = root / "runtime/prospective-public-event-20260928/registered-public-event-projection-v5.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("preserve", encoding="utf-8")

    with pytest.raises(ValueError, match="Refusing to overwrite"):
        builder.write_new_json(output, {})


def test_v5_successor_is_deterministic_and_does_not_modify_predecessors(tmp_path):
    root = _case_repo(tmp_path)
    predecessor = root / builder.PREDECESSOR_PATH
    source = root / builder.SOURCE_PATH
    before = (hashlib.sha256(predecessor.read_bytes()).hexdigest(), hashlib.sha256(source.read_bytes()).hexdigest())
    first = json.dumps(builder.build_projection_payload(root), sort_keys=True)
    second = json.dumps(builder.build_projection_payload(root), sort_keys=True)

    assert first == second
    assert before == (
        hashlib.sha256(predecessor.read_bytes()).hexdigest(),
        hashlib.sha256(source.read_bytes()).hexdigest(),
    )
