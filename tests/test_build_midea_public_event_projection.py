import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts/cases/build_midea_public_event_projection.py"
SPEC = importlib.util.spec_from_file_location("midea_projection_builder", SCRIPT_PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def _archive(tmp_path):
    index_dir = tmp_path / builder.INDEX_RELATIVE_PATH.parent
    index_dir.mkdir(parents=True)
    pdf_dir = tmp_path / builder.ARCHIVE_RELATIVE_DIR
    pdf_dir.mkdir(parents=True)
    dividend_dir = tmp_path / builder.ARCHIVE_RELATIVE_BASELINE_DIR
    dividend_dir.mkdir(parents=True)

    rows = []
    hashes = {}
    for source in builder.EVENT_SOURCES:
        path = tmp_path / source["relative_pdf_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        content = f"original archived PDF bytes {source['announcement_id']}".encode()
        path.write_bytes(content)
        hashes[source["announcement_id"]] = hashlib.sha256(content).hexdigest()
        rows.append({
            "announcementId": source["announcement_id"],
            "secCode": "000333",
            "adjunctUrl": source["url"].split("cninfo.com.cn/")[-1],
        })
    index_path = tmp_path / builder.INDEX_RELATIVE_PATH
    index_path.write_text(json.dumps({
        "symbol": "000333",
        "issuer_name": "美的集团",
        "schema_version": "prospective-cninfo-window-index-v1",
        "announcements": rows,
    }), encoding="utf-8")
    index_hash = hashlib.sha256(index_path.read_bytes()).hexdigest()
    return index_hash, hashes


def test_builds_three_historical_events_without_changing_decisions(tmp_path):
    index_hash, pdf_hashes = _archive(tmp_path)

    payload = builder.build_projection_payload(
        tmp_path, index_sha256=index_hash, pdf_sha256s=pdf_hashes,
    )

    assert payload["report"]["classification"] == "PRE_REGISTRATION_PUBLIC_HISTORICAL_MATERIAL"
    assert payload["report"]["prospective_observation_written"] is False
    assert payload["report"]["prospective_ledger_written"] is False
    assert payload["report"]["valuation_or_trade_conclusion_changed"] is False
    assert payload["report"]["action"] == "no_order"
    assert payload["action"] == "no_order"
    assert len(payload["projection"]["events"]) == 3
    assert len(payload["projection"]["audit_evidence"]) == 3
    assert [item["event_type"] for item in payload["projection"]["events"]] == [
        "MATERIAL_SUPPORTING_EVIDENCE",
        "MATERIAL_RISK_MONITOR",
        "MATERIAL_RISK_MONITOR",
    ]
    assert all(item["action"] == "no_order" for item in payload["projection"]["audit_evidence"])
    assert all(set(item) == {
        "evidence_id", "title", "artifact_type", "path", "sha256", "available_at",
        "action", "source_url",
    } for item in payload["projection"]["audit_evidence"])
    assert set(payload["report"]["evidence_source_urls"]) == {
        "1225531406", "1225544342", "1225544482"
    }
    evidence_by_id = {
        item["evidence_id"]: item for item in payload["projection"]["audit_evidence"]
    }
    assert {
        source["announcement_id"]: evidence_by_id[
            f"cninfo-{source['announcement_id']}"
        ]["source_url"]
        for source in builder.EVENT_SOURCES
    } == payload["report"]["evidence_source_urls"]


def test_rejects_tampered_pdf_hash(tmp_path):
    index_hash, pdf_hashes = _archive(tmp_path)
    pdf_hashes["1225544342"] = "0" * 64

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        builder.build_projection_payload(
            tmp_path, index_sha256=index_hash, pdf_sha256s=pdf_hashes,
        )


def test_refuses_to_overwrite_existing_output(tmp_path):
    output = tmp_path / "projection.json"
    output.write_text('{"keep":true}', encoding="utf-8")

    with pytest.raises(ValueError, match="Refusing to overwrite"):
        builder.write_new_json(output, {"replace": True})

    assert output.read_text(encoding="utf-8") == '{"keep":true}'
