from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts/cases/build_registered_public_event_projection.py"
SPEC = importlib.util.spec_from_file_location("registered_public_event_builder", SCRIPT_PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def test_composes_registered_issuer_events_and_keeps_all_evidence_pinned():
    payload = builder.build_projection_payload()
    projection = payload["projection"]
    assert payload["action"] == projection["action"] == "no_order"
    assert payload["report"]["scope"] == ["000333", "600887", "601088"]
    assert payload["report"]["strict_pit_proven"] is False
    assert payload["report"]["valuation_or_trade_conclusion_changed"] is False
    assert len(projection["events"]) == 8
    assert {row["company_name"] for row in projection["events"]} == {
        "美的集团", "伊利股份", "中国神华",
    }
    yili = next(row for row in projection["events"] if row["event_id"] == "cninfo-600887-1225578520-third-phase-share-purchase")
    assert yili["event_type"] == "EVIDENCE_GAP"
    assert "224,997,098.71" in yili["what_happened"]
    assert all(row["action"] == "no_order" for row in projection["events"])
    assert {row["evidence_id"] for row in projection["audit_evidence"]} >= {
        source["evidence_id"] for source in builder.YILI_SOURCES
    }
    evidence_by_id = {row["evidence_id"]: row for row in projection["audit_evidence"]}
    for source in builder.YILI_SOURCES:
        assert evidence_by_id[source["evidence_id"]]["source_url"] == source["source_url"]
    assert builder.YILI_SOURCES[1]["source_url"] is None
    assert evidence_by_id[builder.YILI_SOURCES[1]["evidence_id"]]["source_url"] is None


def test_composite_fails_closed_when_yili_source_bytes_change(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    for module in (
        "build_midea_public_event_projection",
        "build_shenhua_public_event_projection",
    ):
        spec = importlib.util.spec_from_file_location(
            f"test_{module}", Path(__file__).parents[1] / f"scripts/cases/{module}.py"
        )
        item = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(item)
        if module.startswith("build_midea"):
            source_paths = [
                item.INDEX_RELATIVE_PATH.as_posix(),
                *(source["relative_pdf_path"].as_posix() for source in item.EVENT_SOURCES),
            ]
        else:
            source_paths = [source["path"] for source in item.EVIDENCE_SOURCES]
        for relative in set(source_paths):
            original = item.REPOSITORY_ROOT / relative
            if not original.is_file():
                continue
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
    for source in builder.YILI_SOURCES:
        original = Path(__file__).parents[1] / source["path"]
        target = root / source["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
    tampered = root / builder.YILI_SOURCES[0]["path"]
    tampered.write_bytes(tampered.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="Yili evidence SHA-256 mismatch"):
        builder.build_projection_payload(root)


def test_writer_refuses_to_replace_existing_projection(tmp_path: Path):
    target = tmp_path / "projection.json"
    original = b'{"action":"no_order"}\n'
    target.write_bytes(original)
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        builder.write_new_json(target, {"action": "no_order"})
    assert target.read_bytes() == original


def test_yili_evidence_hashes_match_retained_source_bytes():
    for source in builder.YILI_SOURCES:
        path = Path(__file__).parents[1] / source["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
