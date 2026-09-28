from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT_PATH = ROOT / "scripts/cases/build_registered_public_event_projection_v4.py"
SPEC = importlib.util.spec_from_file_location("registered_public_event_builder_v4", SCRIPT_PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def _case_repo(tmp_path: Path) -> Path:
    predecessor = tmp_path / builder.PREDECESSOR_PATH
    predecessor.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / builder.PREDECESSOR_PATH, predecessor)
    return tmp_path


def test_v4_excludes_future_available_notice_and_preserves_v3(tmp_path):
    root = _case_repo(tmp_path)
    predecessor = root / builder.PREDECESSOR_PATH
    before_hash = hashlib.sha256(predecessor.read_bytes()).hexdigest()

    result = builder.build_projection_payload(root)

    projection = result["projection"]
    report = result["report"]
    assert report["schema_version"] == "registered-public-event-projection-v4"
    assert report["successor_of"] == "registered-public-event-projection-v3"
    assert report["predecessor_sha256"] == builder.PREDECESSOR_SHA256
    assert report["public_event_observation_as_of"] == "2026-09-28"
    assert report["event_count"] == 8
    assert report["as_of_exclusions"] == [{
        "evidence_id": "cninfo-1225582141",
        "available_at": "2026-09-29",
        "event_ids": ["midea-2026-egm-notice-1225582141"],
        "reason": "SOURCE_NOT_AVAILABLE_AS_OF_CUTOFF",
    }]
    assert len(projection["events"]) == 8
    assert len(projection["audit_decisions"]) == 8
    assert len(projection["audit_evidence"]) == 10
    assert "midea-2026-egm-notice-1225582141" not in {
        row["event_id"] for row in projection["events"]
    }
    assert "cninfo-1225582141" not in {
        row["evidence_id"] for row in projection["audit_evidence"]
    }
    assert report["strict_pit_proven"] is False
    assert report["valuation_or_trade_conclusion_changed"] is False
    assert result["action"] == projection["action"] == "no_order"
    assert hashlib.sha256(predecessor.read_bytes()).hexdigest() == before_hash


def test_v4_rejects_tampered_v3_predecessor(tmp_path):
    root = _case_repo(tmp_path)
    predecessor = root / builder.PREDECESSOR_PATH
    predecessor.write_bytes(predecessor.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="v3 predecessor SHA-256 mismatch"):
        builder.build_projection_payload(root)
