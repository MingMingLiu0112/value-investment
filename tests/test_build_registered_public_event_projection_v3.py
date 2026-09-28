from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT_PATH = ROOT / "scripts/cases/build_registered_public_event_projection_v3.py"
SPEC = importlib.util.spec_from_file_location("registered_public_event_builder_v3", SCRIPT_PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)

NOTICE_SCRIPT = ROOT / "scripts/cases/build_midea_egm_notice_projection.py"
NOTICE_SPEC = importlib.util.spec_from_file_location("midea_egm_notice_builder_v2", NOTICE_SCRIPT)
notice_builder = importlib.util.module_from_spec(NOTICE_SPEC)
NOTICE_SPEC.loader.exec_module(notice_builder)


def _case_repo(tmp_path: Path) -> tuple[Path, Path, str]:
    root = tmp_path
    predecessor = root / builder.PREDECESSOR_PATH
    predecessor.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / builder.PREDECESSOR_PATH, predecessor)

    source_dir = ROOT / notice_builder.EVIDENCE_DIR
    target_dir = root / notice_builder.EVIDENCE_DIR
    target_dir.mkdir(parents=True)
    for name in notice_builder.INPUT_SHA256:
        shutil.copyfile(source_dir / name, target_dir / name)

    payload = notice_builder.build_projection_payload(root)
    notice_path = root / "runtime/midea-egm-notice-projection-v2.json"
    notice_builder.write_new_json(notice_path, payload)
    digest = hashlib.sha256(notice_path.read_bytes()).hexdigest()
    return root, notice_path, digest


def _build(root: Path, notice_path: Path, digest: str):
    return builder.build_projection_payload(
        root,
        notice_projection_path=notice_path,
        notice_projection_sha256=digest,
    )


def test_v3_only_corrects_notice_pit_date_and_binds_v2_predecessor(tmp_path):
    root, notice_path, notice_hash = _case_repo(tmp_path)
    previous = json.loads((root / builder.PREDECESSOR_PATH).read_text(encoding="utf-8"))
    result = _build(root, notice_path, notice_hash)

    report = result["report"]
    assert report["schema_version"] == "registered-public-event-projection-v3"
    assert report["successor_of"] == "registered-public-event-projection-v2"
    assert report["predecessor_sha256"] == builder.PREDECESSOR_SHA256
    assert report["appended_observation"]["announcement_date"] == "2026-09-28"
    assert report["appended_observation"]["pit_available_at"] == "2026-09-29T00:00:00+08:00"
    assert report["availability_correction"] == {
        "evidence_id": "cninfo-1225582141",
        "announcement_date": "2026-09-28",
        "previous_available_at": "2026-09-28",
        "corrected_available_at": "2026-09-29",
        "source_available_at": "2026-09-29T00:00:00+08:00",
    }
    assert result["projection"]["events"] == previous["projection"]["events"]
    assert result["projection"]["audit_decisions"] == previous["projection"]["audit_decisions"]
    assert result["projection"]["audit_evidence"][:-1] == previous["projection"]["audit_evidence"][:-1]
    old_evidence = previous["projection"]["audit_evidence"][-1]
    new_evidence = result["projection"]["audit_evidence"][-1]
    assert old_evidence["available_at"] == "2026-09-28"
    assert new_evidence["available_at"] == "2026-09-29"
    assert "公告日2026-09-28" in new_evidence["title"]
    assert {key: value for key, value in new_evidence.items() if key not in {"title", "available_at"}} == {
        key: value for key, value in old_evidence.items() if key not in {"title", "available_at"}
    }
    assert report["strict_pit_proven"] is False
    assert report["valuation_or_trade_conclusion_changed"] is False
    assert result["action"] == "no_order"


def test_v3_rejects_tampered_predecessor(tmp_path):
    root, notice_path, notice_hash = _case_repo(tmp_path)
    predecessor = root / builder.PREDECESSOR_PATH
    predecessor.write_bytes(predecessor.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="v2 predecessor SHA-256 mismatch"):
        _build(root, notice_path, notice_hash)


def test_v3_rejects_same_day_as_pit_available_for_date_only_source(tmp_path):
    root, notice_path, _ = _case_repo(tmp_path)
    payload = json.loads(notice_path.read_text(encoding="utf-8"))
    payload["report"]["source_available_at"] = "2026-09-28T00:00:00+08:00"
    payload["projection"]["audit_evidence"][0]["available_at"] = "2026-09-28"
    notice_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tampered_hash = hashlib.sha256(notice_path.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="does not match reverified source bytes and PIT contract"):
        _build(root, notice_path, tampered_hash)


def test_v3_refuses_to_overwrite_existing_output(tmp_path):
    output = tmp_path / "projection.json"
    output.write_text('{"keep":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        builder.write_new_json(output, {"replace": True})
    assert output.read_text(encoding="utf-8") == '{"keep":true}'
