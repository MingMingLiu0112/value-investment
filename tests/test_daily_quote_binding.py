from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from scripts.current.daily_quote_binding import load_daily_quote_binding


def _document(url: str, raw: bytes) -> tuple[str, dict[str, str]]:
    stamp = "2026-09-26T08:10:00+00:00"
    sha = hashlib.sha256(raw).hexdigest()
    identity = hashlib.sha256((url + "\n" + stamp + "\n" + sha).encode()).hexdigest()
    return identity, {
        "source_url": url, "fetched_at": stamp, "sha256": sha,
        "http_status": 200, "raw_base64": base64.b64encode(raw).decode("ascii"),
    }


def _write_bundle(root: Path) -> Path:
    target = root / "runtime" / "quote-sessions" / "sample"
    target.mkdir(parents=True)
    documents: dict[str, dict[str, str]] = {}
    references = {}
    observations = []
    for symbol, prefix in (("600519", "sh"), ("000333", "sz")):
        tx_id, tx = _document(f"https://qt.gtimg.cn/q={prefix}{symbol}", f"tx-{symbol}".encode())
        sina_id, sina = _document(f"https://hq.sinajs.cn/list={prefix}{symbol}", f"sina-{symbol}".encode())
        documents.update({tx_id: tx, sina_id: sina})
        references[symbol] = {
            "symbol": symbol,
            "document_refs": {"tencent": tx_id, "sina": sina_id, "calendar_documents": []},
        }
        observations.append({"symbol": symbol, "observed_price": "12.34", "result": {
            "status": "matched_close", "passed": True, "expected_session": "2026-09-24",
        }})
    bundle = {
        "version": "quote-session-collection-v1", "status": "collected_not_verified",
        "request_failures": [], "finished_at": "2026-09-26T08:12:00+00:00",
        "documents": documents, "references": references,
    }
    raw = json.dumps(bundle, ensure_ascii=False, sort_keys=True).encode()
    path = target / "bundle.json"
    path.write_bytes(raw)
    (target / "report.json").write_text(json.dumps({
        "bundle_sha256": hashlib.sha256(raw).hexdigest(), "bundle_bytes": len(raw),
        "status": "collected_not_verified", "observations": observations,
        "production_database_changed": False, "financial_or_strategy_approval": False,
    }), encoding="utf-8")
    return path


def test_daily_quote_binding_requires_hash_bound_matched_close_evidence(tmp_path: Path):
    bundle = _write_bundle(tmp_path)
    binding = load_daily_quote_binding(root=tmp_path, bundle_path=bundle)
    assert binding["as_of"] == "2026-09-24"
    assert binding["action"] == "no_order"
    assert binding["quotes"] == [
        {"symbol": "000333", "price": "12.34"},
        {"symbol": "600519", "price": "12.34"},
    ]


def test_daily_quote_binding_fails_closed_on_report_or_raw_tampering(tmp_path: Path):
    bundle = _write_bundle(tmp_path)
    report = bundle.with_name("report.json")
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["observations"][0]["result"]["status"] = "stale_quote"
    report.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="DAILY_QUOTE_NOT_MATCHED_CLOSE"):
        load_daily_quote_binding(root=tmp_path, bundle_path=bundle)
