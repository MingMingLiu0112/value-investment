import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts/cases/build_midea_egm_notice_projection.py"
SPEC = importlib.util.spec_from_file_location("midea_egm_notice_projection_builder", SCRIPT_PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def _evidence_fixture(tmp_path):
    source_dir = builder.REPOSITORY_ROOT / builder.EVIDENCE_DIR
    target_dir = tmp_path / builder.EVIDENCE_DIR
    target_dir.mkdir(parents=True)
    for name in builder.INPUT_SHA256:
        shutil.copyfile(source_dir / name, target_dir / name)
    return target_dir


def test_builds_one_strictly_bounded_notice_event(tmp_path):
    _evidence_fixture(tmp_path)

    payload = builder.build_projection_payload(tmp_path)

    report = payload["report"]
    assert report["schema_version"] == "midea-egm-notice-projection-v2"
    assert report["successor_of"] == "midea-egm-notice-projection-v1"
    assert report["announcement_date"] == "2026-09-28"
    assert report["source_available_at"] == "2026-09-29T00:00:00+08:00"
    assert report["source_time_precision"] == "DATE_ONLY_CONSERVATIVE_NEXT_DAY"
    assert report["strict_pit_admissible"] is False
    assert report["watermark_status"] == "UNCHANGED"
    assert report["coverage_status"] == "SINGLE_DAY_SNAPSHOT_ONLY"
    assert report["valuation_or_trade_conclusion_changed"] is False
    assert report["action"] == payload["action"] == "no_order"
    assert report["input_sha256"] == builder.INPUT_SHA256
    assert len(payload["projection"]["events"]) == 1
    event = payload["projection"]["events"][0]
    assert event["event_type"] == "MATERIAL_RISK_MONITOR"
    assert "2026-10-13" in event["what_happened"]
    assert "待审议" in event["what_happened"]
    assert "不证明议案通过或实施" in event["what_happened"]
    assert "分红金额或注销股数" in event["what_happened"]
    assert "决议及表决结果" in event["next_step"]
    assert event["action"] == "no_order"

    evidence = payload["projection"]["audit_evidence"]
    assert len(evidence) == 1
    assert evidence[0]["source_url"] == builder.CNINFO_URL
    assert evidence[0]["path"].endswith("/1225582141.PDF")
    assert evidence[0]["sha256"] == builder.INPUT_SHA256["1225582141.PDF"]
    assert "公告日2026-09-28" in evidence[0]["title"]
    assert evidence[0]["available_at"] == "2026-09-29"


@pytest.mark.parametrize("name", builder.INPUT_SHA256)
def test_rejects_tampering_of_each_pinned_input(tmp_path, name):
    target_dir = _evidence_fixture(tmp_path)
    path = target_dir / name
    path.write_bytes(path.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        builder.build_projection_payload(tmp_path)


def test_refuses_to_overwrite_existing_output(tmp_path):
    output = tmp_path / "projection.json"
    original = '{"keep":true}'
    output.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="Refusing to overwrite"):
        builder.write_new_json(output, {"replace": True})

    assert output.read_text(encoding="utf-8") == original


def test_hashes_match_independently_for_fixture_files(tmp_path):
    target_dir = _evidence_fixture(tmp_path)

    assert {
        name: hashlib.sha256((target_dir / name).read_bytes()).hexdigest()
        for name in builder.INPUT_SHA256
    } == builder.INPUT_SHA256
