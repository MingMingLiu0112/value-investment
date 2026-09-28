from __future__ import annotations

import base64
import hashlib
import json
from calendar import monthrange
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.current.daily_quote_binding import load_daily_quote_binding
from value_investment_agent.quote_sessions import CALENDAR_PATH, SSE_2026_CLOSURE_NOTICE_URL


FINISHED = "2026-09-26T08:12:00+00:00"


def _document(url: str, raw: bytes, fetched_at: str = FINISHED) -> tuple[str, dict[str, object]]:
    sha = hashlib.sha256(raw).hexdigest()
    identity = hashlib.sha256(f"{url}\n{fetched_at}\n{sha}".encode()).hexdigest()
    return identity, {
        "source_url": url, "fetched_at": fetched_at, "sha256": sha,
        "http_status": 200, "raw_base64": base64.b64encode(raw).decode("ascii"),
    }


def _quote_bytes(symbol: str, provider: str) -> bytes:
    prefix = "sz" if symbol.startswith(("0", "3")) else "sh"
    identity = prefix + symbol
    fields = [""] * (33 if provider == "sina" else 31)
    if provider == "tencent":
        fields[2], fields[3], fields[5], fields[6] = symbol, "12.34", "12.00", "1000"
        fields[30] = "20260924150000"
        text = f'v_{identity}="{"~".join(fields)}";'
    else:
        fields[1], fields[3], fields[8] = "12.00", "12.34", "1000"
        fields[30], fields[31], fields[32] = "2026-09-24", "15:00:00", "00"
        text = f'var hq_str_{identity}="{",".join(fields)}";'
    return text.encode("gb18030")


def _write_bundle(root: Path) -> Path:
    target = root / "runtime" / "quote-sessions" / "sample"
    target.mkdir(parents=True)
    documents: dict[str, dict[str, object]] = {}
    references = {}
    observations = []
    for symbol in ("600519", "000333", "600887"):
        prefix = "sh" if symbol.startswith("6") else "sz"
        ids = {}
        for provider, host, path in (
            ("tencent", "qt.gtimg.cn", f"/q={prefix}{symbol}"),
            ("sina", "hq.sinajs.cn", f"/list={prefix}{symbol}"),
        ):
            identity, doc = _document(f"https://{host}{path}", _quote_bytes(symbol, provider))
            documents[identity] = doc
            ids[provider] = identity
        calendar_refs = []
        if symbol.startswith("0"):
            rows = [
                {"jyrq": f"2026-09-{day:02d}", "jybz": "1" if day <= 24 and datetime(2026, 9, day).weekday() < 5 else "0"}
                for day in range(1, monthrange(2026, 9)[1] + 1)
            ]
            calendar_raw = json.dumps({"nowdate": "2026-09-26", "data": rows}).encode()
            identity, doc = _document(f"https://www.szse.cn{CALENDAR_PATH}?month=2026-09", calendar_raw)
            documents[identity] = doc
            calendar_refs.append(identity)
        else:
            calendar_raw = (
                "<!doctype html><html><body>关于上海证券交易所2026年部分节假日休市安排的通知 "
                "1月1日（星期四）至1月3日（星期六）休市 "
                "2月15日（星期日）至2月23日（星期一）休市 "
                "4月4日（星期六）至4月6日（星期一）休市 "
                "5月1日（星期五）至5月5日（星期二）休市 "
                "6月19日（星期五）至6月21日（星期日）休市 "
                "9月25日（星期五）至9月27日（星期日）休市 "
                "10月1日（星期四）至10月7日（星期三）休市</body></html>"
            ).encode()
            identity, doc = _document(SSE_2026_CLOSURE_NOTICE_URL, calendar_raw)
            documents[identity] = doc
            calendar_refs.append(identity)
        references[symbol] = {
            "symbol": symbol,
            "calendar_exchange": "SSE" if symbol.startswith("6") else "SZSE",
            "document_refs": {**ids, "calendar_documents": calendar_refs},
        }
        observations.append({"symbol": symbol, "observed_price": "12.34", "result": {
            "status": "matched_close", "passed": True, "expected_session": "2026-09-24",
        }})
    bundle = {
        "version": "quote-session-collection-v1", "status": "collected_not_verified",
        "request_failures": [], "finished_at": FINISHED,
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


def _binding(root: Path, bundle: Path):
    return load_daily_quote_binding(
        root=root, bundle_path=bundle,
        registration_receipt_sha256="a" * 64,
        registration_sha256="b" * 64, plan_sha256="c" * 64,
        registered_symbols=("000333", "600887", "601088"), excluded_symbols=("600519",),
    )


def test_daily_quote_binding_reparses_raw_bytes_and_rejects_unsafe_symbol_set(tmp_path: Path):
    bundle = _write_bundle(tmp_path)
    binding = _binding(tmp_path, bundle)
    assert binding["as_of"] == "2026-09-24"
    assert binding["action"] == "no_order"
    assert binding["quotes"] == [
        {"symbol": "000333", "price": "12.34"},
        {"symbol": "600887", "price": "12.34"},
    ]
    assert binding["coverage_status"] == "PARTIAL"
    assert binding["missing_symbols"] == ["601088"]
    assert binding["excluded_symbols"] == ["600519"]
    assert binding["pit_cutoff"] == FINISHED
    assert binding["registration_receipt_sha256"] == "a" * 64
    assert binding["registration_sha256"] == "b" * 64
    assert binding["plan_sha256"] == "c" * 64
    assert binding["source_evidence"]["000333"]["tencent"]["sha256"]
    assert binding["source_evidence"]["000333"]["sina"]["sha256"]
    assert binding["source_evidence"]["000333"]["calendar"][0]["sha256"]


def test_daily_quote_binding_rejects_unregistered_symbols(tmp_path: Path):
    bundle = _write_bundle(tmp_path)
    with pytest.raises(ValueError, match="DAILY_QUOTE_UNREGISTERED_SYMBOLS:600519"):
        load_daily_quote_binding(root=tmp_path, bundle_path=bundle,
                                 registration_receipt_sha256="a" * 64,
                                 registration_sha256="b" * 64, plan_sha256="c" * 64,
                                 registered_symbols=("000333", "600887", "601088"))


def test_daily_quote_binding_rejects_duplicate_registration(tmp_path: Path):
    bundle = _write_bundle(tmp_path)
    with pytest.raises(ValueError, match="DAILY_QUOTE_REGISTERED_SYMBOLS_INVALID"):
        load_daily_quote_binding(root=tmp_path, bundle_path=bundle,
                                 registration_receipt_sha256="a" * 64,
                                 registration_sha256="b" * 64, plan_sha256="c" * 64,
                                 registered_symbols=("000333", "000333"))


def test_daily_quote_binding_rejects_invalid_registration_hashes(tmp_path: Path):
    bundle = _write_bundle(tmp_path)
    with pytest.raises(ValueError, match="DAILY_QUOTE_REGISTRATION_RECEIPT_HASH_INVALID"):
        load_daily_quote_binding(
            root=tmp_path, bundle_path=bundle, registered_symbols=("000333",),
            registration_receipt_sha256="not-a-hash", registration_sha256="b" * 64,
            plan_sha256="c" * 64,
        )


def test_daily_quote_binding_rejects_source_fetched_after_cutoff(tmp_path: Path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    doc_id, document = next(iter(payload["documents"].items()))
    document["fetched_at"] = "2026-09-26T08:13:00+00:00"
    new_id = hashlib.sha256(
        f"{document['source_url']}\n{document['fetched_at']}\n{document['sha256']}".encode()
    ).hexdigest()
    payload["documents"][new_id] = payload["documents"].pop(doc_id)
    for reference in payload["references"].values():
        refs = reference["document_refs"]
        for key, value in list(refs.items()):
            if isinstance(value, list):
                refs[key] = [new_id if item == doc_id else item for item in value]
            elif value == doc_id:
                refs[key] = new_id
    bundle.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    report = bundle.with_name("report.json")
    report_payload = json.loads(report.read_text(encoding="utf-8"))
    raw = bundle.read_bytes()
    report_payload["bundle_sha256"] = hashlib.sha256(raw).hexdigest()
    report_payload["bundle_bytes"] = len(raw)
    report.write_text(json.dumps(report_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="DAILY_QUOTE_EVIDENCE_AFTER_CUTOFF"):
        _binding(tmp_path, bundle)


def test_daily_quote_binding_rejects_future_cutoff(tmp_path: Path):
    bundle = _write_bundle(tmp_path)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    payload["finished_at"] = "2999-01-01T00:00:00+00:00"
    bundle.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    report = bundle.with_name("report.json")
    report_payload = json.loads(report.read_text(encoding="utf-8"))
    raw = bundle.read_bytes()
    report_payload["bundle_sha256"] = hashlib.sha256(raw).hexdigest()
    report_payload["bundle_bytes"] = len(raw)
    report.write_text(json.dumps(report_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="DAILY_QUOTE_CUTOFF_IN_FUTURE"):
        _binding(tmp_path, bundle)


def test_daily_quote_binding_rejects_forged_report_price_and_date(tmp_path: Path):
    bundle = _write_bundle(tmp_path)
    report = bundle.with_name("report.json")
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["observations"][0]["observed_price"] = "99.99"
    report.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="DAILY_QUOTE_RAW_REVALIDATION_FAILED"):
        _binding(tmp_path, bundle)

    payload["observations"][0]["observed_price"] = "12.34"
    payload["observations"][0]["result"]["expected_session"] = "2026-09-23"
    report.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="DAILY_QUOTE_RAW_REVALIDATION_FAILED"):
        _binding(tmp_path, bundle)


def test_daily_quote_binding_fails_closed_on_report_status_or_document_tampering(tmp_path: Path):
    bundle = _write_bundle(tmp_path)
    report = bundle.with_name("report.json")
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["observations"][0]["result"]["status"] = "stale_quote"
    report.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="DAILY_QUOTE_RAW_REVALIDATION_FAILED"):
        _binding(tmp_path, bundle)

    bundle = _write_bundle(tmp_path.parent / "second")
    data = json.loads(bundle.read_text(encoding="utf-8"))
    first = next(iter(data["documents"].values()))
    first["raw_base64"] = base64.b64encode(b"tampered").decode()
    bundle.write_text(json.dumps(data), encoding="utf-8")
    report = bundle.with_name("report.json")
    payload = json.loads(report.read_text(encoding="utf-8"))
    bundle_raw = bundle.read_bytes()
    payload["bundle_sha256"] = hashlib.sha256(bundle_raw).hexdigest()
    payload["bundle_bytes"] = len(bundle_raw)
    report.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="DAILY_QUOTE_DOCUMENT_HASH_MISMATCH"):
        _binding(bundle.parents[3], bundle)
