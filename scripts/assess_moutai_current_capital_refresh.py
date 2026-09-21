#!/usr/bin/env python3
"""Turn a complete bounded CNINFO zero-result index into refresh evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-dir", type=Path, required=True)
    parser.add_argument("--start", default="2026-09-14")
    parser.add_argument("--through", required=True)
    args = parser.parse_args()
    index_dir = args.index_dir.resolve()
    if not index_dir.is_relative_to(ROOT.resolve()):
        raise ValueError("Index must remain in the project")
    records = list(index_dir.glob("600519-*.json"))
    if len(records) != 1:
        raise ValueError("Expected exactly one bounded 600519 index page")
    source = json.loads(records[0].read_text(encoding="utf-8"))
    query, response = source.get("query") or {}, source.get("response") or {}
    if (query.get("seDate") != args.start + "~" + args.through or query.get("stock", "").split(",")[0] != "600519"
            or query.get("category") != "" or response.get("hasMore") or response.get("totalAnnouncement") != 0
            or response.get("announcements") not in (None, [])):
        raise ValueError("Capital refresh query is incomplete or outside the bounded zero-result scope")
    evidence = {
        "symbol": "600519", "refresh_version": "moutai-current-capital-refresh-v1",
        "query_index": {"path": str(records[0].relative_to(ROOT)), "sha256": digest(records[0])},
        "query_window": query["seDate"], "fetched_at": source["fetched_at"],
        "complete": True, "new_or_changed_announcements": 0,
        "conclusion": "No CNINFO announcement was returned in this bounded window; previously verified ordinary shares and capital facts may be carried only through the stated date.",
        "limitations": ["A zero-result index is not a shareholder-register confirmation.", "Later dates require a new bounded query."],
    }
    output = ROOT / "runtime/company-research" / ("600519-current-capital-refresh-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    path = output / "evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "evidence_sha256": digest(path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "through": args.through, "complete": True}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
