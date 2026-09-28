from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT_PATH = ROOT / "scripts/cases/build_registered_public_event_projection_v6.py"
SPEC = importlib.util.spec_from_file_location("registered_public_event_builder_v6", SCRIPT_PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
PINNED_RUNTIME_INPUTS = (
    ROOT / builder.PREDECESSOR_PATH,
    ROOT / builder.SOURCE_PATH,
    ROOT / builder.WATERMARK_PATH,
)
pytestmark = pytest.mark.skipif(
    not all(path.is_file() for path in PINNED_RUNTIME_INPUTS),
    reason="This integration test requires ignored local runtime evidence",
)


def _case_repo(tmp_path: Path) -> Path:
    for relative in (builder.PREDECESSOR_PATH, builder.SOURCE_PATH, builder.WATERMARK_PATH):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    watermarks = json.loads((tmp_path / builder.WATERMARK_PATH).read_text(encoding="utf-8"))
    for row in watermarks["current_bounded_observations"]:
        if row["scan_to"] != builder.CURRENT_AS_OF.isoformat():
            continue
        for path_key, hash_key in (
            ("scan_receipt_path", "scan_receipt_sha256"),
            ("index_path", "index_sha256"),
            ("raw_page_path", "raw_page_sha256"),
        ):
            relative = Path(row[path_key])
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
    return tmp_path


def test_v6_re_admits_only_evidence_available_by_new_cutoff_and_binds_latest_snapshots(tmp_path):
    root = _case_repo(tmp_path)

    result = builder.build_projection_payload(root)
    report = result["report"]
    projection = result["projection"]

    assert report["schema_version"] == "registered-public-event-projection-v6"
    assert report["successor_of"] == "registered-public-event-projection-v5"
    assert report["predecessor_sha256"] == builder.PREDECESSOR_SHA256
    assert report["source_evidence_sha256"] == builder.SOURCE_SHA256
    assert report["public_event_observation_as_of"] == "2026-09-29"
    assert report["strict_pit_proven"] is False
    assert report["formal_watermark_advanced"] is False
    assert report["valuation_or_trade_conclusion_changed"] is False
    assert report["as_of_exclusions"] == []
    assert len(report["resolved_prior_exclusions"]) == 1
    assert report["resolved_prior_exclusions"][0]["evidence_id"] == "cninfo-1225582141"
    assert len(report["bounded_observations"]) == 3
    assert len(projection["events"]) == 9
    assert len(projection["audit_evidence"]) == 11
    assert len(projection["audit_decisions"]) == 9
    assert any(
        row["event_id"] == "midea-2026-egm-notice-1225582141"
        and row["event_type"] == "MATERIAL_RISK_MONITOR"
        for row in projection["events"]
    )
    midea_evidence = next(row for row in projection["audit_evidence"] if row["evidence_id"] == "cninfo-1225582141")
    assert midea_evidence["available_at"] == "2026-09-29"
    assert "1225584526" not in json.dumps(projection, ensure_ascii=False)
    assert result["action"] == projection["action"] == "no_order"


@pytest.mark.parametrize("relative,label", [
    ("predecessor", "v5 predecessor"),
    ("source", "v3 source closure"),
    ("watermark", "watermark v9"),
])
def test_v6_rejects_tampered_chain_inputs(tmp_path, relative, label):
    root = _case_repo(tmp_path)
    path = root / {
        "predecessor": builder.PREDECESSOR_PATH,
        "source": builder.SOURCE_PATH,
        "watermark": builder.WATERMARK_PATH,
    }[relative]
    path.write_bytes(path.read_bytes() + b"tampered")

    with pytest.raises(ValueError, match=f"{label} SHA-256 mismatch"):
        builder.build_projection_payload(root)


def test_v6_rejects_mismatched_current_scan_receipt(tmp_path):
    root = _case_repo(tmp_path)
    watermarks = json.loads((root / builder.WATERMARK_PATH).read_text(encoding="utf-8"))
    row = next(
        item for item in watermarks["current_bounded_observations"]
        if item["symbol"] == "000333" and item["scan_to"] == builder.CURRENT_AS_OF.isoformat()
    )
    (root / row["scan_receipt_path"]).write_bytes(b"{}\n")

    with pytest.raises(ValueError, match="scan receipt SHA-256 mismatch"):
        builder.build_projection_payload(root)


def test_v6_writer_refuses_to_overwrite_existing_successor(tmp_path, monkeypatch):
    root = _case_repo(tmp_path)
    monkeypatch.setattr(builder, "ROOT", root)
    output = root / "runtime/prospective-public-event-20260929/registered-public-event-projection-v6.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("preserve", encoding="utf-8")

    with pytest.raises(ValueError, match="Refusing to overwrite"):
        builder.write_new_json(output, {})


def test_v6_is_deterministic_and_does_not_modify_its_inputs(tmp_path):
    root = _case_repo(tmp_path)
    paths = [root / builder.PREDECESSOR_PATH, root / builder.SOURCE_PATH, root / builder.WATERMARK_PATH]
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]

    first = json.dumps(builder.build_projection_payload(root), sort_keys=True)
    second = json.dumps(builder.build_projection_payload(root), sort_keys=True)

    assert first == second
    assert before == [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
