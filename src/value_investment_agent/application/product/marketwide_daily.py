"""Bind one M2 scan to a replayable, research-only daily value queue."""
from __future__ import annotations

from pathlib import Path

from value_investment_agent.application.research.value_research_queue import build_value_research_queue
from .m2_quality_diagnostic import diagnose_quality
from .common import load_json_object, require_inside, sha256_file, write_new_json


def prepare_marketwide_daily(*, root: Path, scan_dir: Path, queue_path: Path,
                             budget: int = 10) -> dict:
    root = root.resolve()
    scan_dir = require_inside(root / "runtime", scan_dir, "M2 scan")
    queue_path = require_inside(root / "runtime", queue_path, "M2 queue")
    if queue_path.exists():
        raise FileExistsError("M2 queue output already exists")
    manifest = load_json_object(scan_dir / "manifest.json", "M2 manifest")
    if manifest.get("schema_version") != "m2-run-manifest-v1":
        raise ValueError("unsupported M2 manifest")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("M2 manifest has no bound files")

    def bound(role: str) -> tuple[Path, str]:
        item = files.get(role)
        if not isinstance(item, dict):
            raise ValueError(f"M2 {role} binding missing")
        path = require_inside(scan_dir, root / item["path"], f"M2 {role}")
        digest = item["sha256"]
        if sha256_file(path) != digest:
            raise ValueError(f"M2 {role} hash mismatch")
        return path, digest

    report, report_hash = bound("lead_report")
    receipt, receipt_hash = bound("receipt")
    queue = build_value_research_queue(root=root, report_path=report,
        report_sha256=report_hash, receipt_path=receipt,
        receipt_sha256=receipt_hash, budget=budget)
    write_new_json(queue_path, queue)
    quality_path = queue_path.with_name(queue_path.stem + "-quality.json")
    quality = diagnose_quality(receipt, root)
    quality["schema_version"] = "m2-quality-diagnostic-v1"
    write_new_json(quality_path, quality)
    market_path = queue_path.with_name(queue_path.stem + "-market-regime.json")
    market = {"schema_version": "market-regime-observation-v1", "action": "no_order",
              "scope": "OBSERVATION_ONLY", "status": "UNKNOWN", "regime": "UNKNOWN",
              "reason": "UNVERIFIED_PROVIDER_TRADE_DATE",
              "reported_quote_date": manifest.get("summary", {}).get("quote_date"),
              "market_breadth_ratio": None, "turnover_change_ratio": None,
              "position_guidance": None,
              "source_binding": {"path": report.relative_to(root).as_posix(), "sha256": report_hash}}
    write_new_json(market_path, market)
    return {"action": "no_order", "scan_manifest": {
                "path": (scan_dir / "manifest.json").relative_to(root).as_posix(),
                "sha256": sha256_file(scan_dir / "manifest.json")},
            "value_discovery_report": {"path": report.relative_to(root).as_posix(), "sha256": report_hash},
            "value_research_queue": {"path": queue_path.relative_to(root).as_posix(),
                                     "sha256": sha256_file(queue_path)},
            "m2_quality_diagnostic": {"path": quality_path.relative_to(root).as_posix(),
                                      "sha256": sha256_file(quality_path)},
            "market_regime_observation": {"path": market_path.relative_to(root).as_posix(),
                                          "sha256": sha256_file(market_path)},
            "selected_count": queue["selected_count"],
            "as_of": queue["as_of"]}
