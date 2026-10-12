import hashlib
import json

import pytest

from value_investment_agent.application.product import marketwide_daily


def _fixture(root):
    scan = root / "runtime" / "scan"
    scan.mkdir(parents=True)
    files = {}
    for role in ("lead_report", "receipt"):
        path = scan / f"{role}.json"
        path.write_text(json.dumps({"action": "no_order", "role": role}), encoding="utf-8")
        files[role] = {"path": path.relative_to(root).as_posix(),
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (scan / "manifest.json").write_text(json.dumps({
        "schema_version": "m2-run-manifest-v1", "files": files}), encoding="utf-8")
    return scan


def test_daily_binding_uses_only_manifest_pinned_inputs(tmp_path, monkeypatch):
    scan = _fixture(tmp_path)
    seen = {}

    def build(**kwargs):
        seen.update(kwargs)
        return {"action": "no_order", "selected_count": 0, "as_of": "2026-10-09", "entries": []}

    monkeypatch.setattr(marketwide_daily, "build_value_research_queue", build)
    monkeypatch.setattr(marketwide_daily, "diagnose_quality", lambda *_: {
        "action": "no_order", "status_counts": {"DATA_GAP": 2, "PASS": 0}})
    output = tmp_path / "runtime" / "queue.json"
    result = marketwide_daily.prepare_marketwide_daily(root=tmp_path, scan_dir=scan,
                                                        queue_path=output)
    assert seen["report_path"] == scan / "lead_report.json"
    assert seen["receipt_path"] == scan / "receipt.json"
    assert result["action"] == "no_order"
    assert result["value_research_queue"]["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    regime = json.loads((tmp_path / result["market_regime_observation"]["path"]).read_text())
    assert regime["regime"] == "UNKNOWN" and regime["market_breadth_ratio"] is None
    with pytest.raises(FileExistsError):
        marketwide_daily.prepare_marketwide_daily(root=tmp_path, scan_dir=scan,
                                                  queue_path=output)


def test_daily_binding_rejects_tampered_scan_without_queue(tmp_path):
    scan = _fixture(tmp_path)
    (scan / "lead_report.json").write_text("{}", encoding="utf-8")
    output = tmp_path / "runtime" / "queue.json"
    with pytest.raises(ValueError, match="hash mismatch"):
        marketwide_daily.prepare_marketwide_daily(root=tmp_path, scan_dir=scan,
                                                  queue_path=output)
    assert not output.exists()
