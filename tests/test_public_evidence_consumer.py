"""Offline consumer tests; retained loader runs with synthetic PDF extraction."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest
import requests

from value_investment_agent.application.research import public_evidence as mod
from value_investment_agent.infrastructure.filings import official_report_acquisition as adapter


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return dict(path=path.name, sha256=digest(path))


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def forbidden(*args, **kwargs):
    raise AssertionError("Consumer must not acquire, download, or write")


def bundle(root, monkeypatch):
    # Only transport and PDF decoding are synthetic; actual retained receipt,
    # raw-index replay, hash/identity/clock validation remain in use.
    row = dict(secCode="000544", orgId="test-org", announcementId="123",
        announcementTitle="2026年半年度报告", adjunctUrl="finalpage/2026-08-24/123.PDF",
        announcementTime=int(datetime(2026, 8, 24, tzinfo=adapter.CHINA).timestamp() * 1000))

    def query(parameters, *, raw_response_sink):
        rows = [row] if parameters.get("stock") else [dict(secCode="000544", orgId="test-org")]
        payload = dict(announcements=rows, totalAnnouncement=len(rows))
        raw = json.dumps(payload).encode()
        raw_response_sink(raw, dict(url=adapter.disclosures.SEARCH_URL, request=parameters,
            sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw),
            acquired_at=datetime.now(timezone.utc).isoformat()))
        return payload

    def download(url, path):
        path.write_bytes(b"%PDF-TEST_ONLY\\n%%EOF")
        return digest(path)

    monkeypatch.setattr(adapter.disclosures, "_request_json", query)
    monkeypatch.setattr(adapter, "download_official_pdf", download)
    monkeypatch.setattr(adapter, "extract_pages", lambda *a, **kw: [
        "证券代码：000544 中原环保股份有限公司 2026年半年度报告"])
    monkeypatch.setattr(adapter, "validate_pdf_original", lambda _: None)
    folder = root / "runtime/public-test"
    acquired = adapter.acquire_official_report(root=root, symbol="000544", issuer_name="中原环保",
        period="2026-06-30", output_dir=folder / "acquisition", allow_network=True)
    export = folder / "financial-export.json"
    write(export, dict(generated_at=datetime.now(timezone.utc).isoformat(), action="no_order",
        formal_eligibility=False, points=[], annual_points=[], value_enrichment_sources=[]))
    request = dict(symbol="000544", issuer_name="中原环保", period="2026-06-30", exchange="SZSE")
    packet = dict(schema_version=mod.VERSION, action="no_order", scope="REQUESTED_REPORTS_ONLY",
        formal_eligibility=False, strict_historical_pit=False, status="VERIFIED",
        generated_at=datetime.now(timezone.utc).isoformat(), requests=[request],
        financial_export=mod._binding(root, export),
        items=[dict(request=request, status="VERIFIED", reused=True, fresh_index_checked=False,
            reason="RETAINED_ORIGINAL_NOT_LATEST_REPORT_ASSERTION",
            receipt=mod._binding(root, folder / "acquisition/receipt.json"),
            fact_snapshot=None, fact_status="UNSUPPORTED_INTERIM_FACT_PARSER", adopted_fact_count=0)])
    path = folder / "bundle.json"
    write(path, packet)
    # All acquisition and writer entrypoints forbidden during consumption.
    monkeypatch.setattr(adapter.disclosures, "_request_json", forbidden)
    monkeypatch.setattr(adapter, "download_official_pdf", forbidden)
    monkeypatch.setattr(mod, "acquire_official_report", forbidden)
    monkeypatch.setattr(mod, "_write", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    return dict(root=root, bundle_path=path, bundle_sha256=digest(path),
        financial_export_path=export, financial_export_sha256=digest(export)), packet, acquired


def test_complete_bundle_consumes_exact_export_and_replays_original_without_writes(tmp_path, monkeypatch):
    args, packet, acquired = bundle(tmp_path, monkeypatch)
    before = snapshot(tmp_path)
    real = mod.load_retained_official_report
    calls = []
    def retained(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)
    monkeypatch.setattr(mod, "load_retained_official_report", retained)
    result = mod.validate_queue_public_evidence(**args)
    assert result == packet
    assert len(calls) == 1
    assert calls[0]["symbol"] == "000544"
    assert calls[0]["issuer_name"] == "中原环保"
    assert calls[0]["period"] == "2026-06-30"
    assert snapshot(tmp_path) == before
    receipt_path = tmp_path / packet["items"][0]["receipt"]["path"]
    assert json.loads(receipt_path.read_bytes())["fetched_at"] == acquired["fetched_at"]
    assert result["items"][0]["adopted_fact_count"] == 0  # source verification is not fact completeness


@pytest.mark.parametrize("damage", ["bundle_hash", "export_hash", "same_bytes_other_path",
    "missing_item", "receipt_missing", "original_drift", "index_drift",
    "issuer_mismatch", "export_drift", "outside", "malformed_hash"])
def test_invalid_consumer_rejects_without_write_or_network(tmp_path, monkeypatch, damage):
    args, packet, acquired = bundle(tmp_path, monkeypatch)
    if damage == "bundle_hash":
        args["bundle_sha256"] = "0" * 64
    elif damage == "export_hash":
        args["financial_export_sha256"] = "0" * 64
    elif damage == "same_bytes_other_path":
        clone = tmp_path / "runtime/same-bytes.json"
        clone.write_bytes(args["financial_export_path"].read_bytes())
        args["financial_export_path"] = clone
    elif damage == "missing_item":
        packet["items"] = []
    elif damage == "receipt_missing":
        packet["items"][0]["receipt"] = None
    elif damage == "original_drift":
        (tmp_path / acquired["source"]["path"]).write_bytes(b"CHANGED ORIGINAL")
    elif damage == "index_drift":
        (tmp_path / acquired["index_bindings"][0]["path"]).write_bytes(b"{}")
    elif damage == "issuer_mismatch":
        packet["requests"][0]["issuer_name"] = "其他企业"
    elif damage == "export_drift":
        args["financial_export_path"].write_bytes(b"{}")
    elif damage == "outside":
        args["financial_export_path"] = tmp_path / "outside.json"
    elif damage == "malformed_hash":
        args["financial_export_sha256"] = None
    if damage in {"missing_item", "receipt_missing", "issuer_mismatch"}:
        write(args["bundle_path"], packet)
        args["bundle_sha256"] = digest(args["bundle_path"])
    before = snapshot(tmp_path)
    with pytest.raises((ValueError, OSError)):
        mod.validate_queue_public_evidence(**args)
    assert snapshot(tmp_path) == before


def cli(root, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/current/build_value_research_queue.py"
    spec = importlib.util.spec_from_file_location("public_evidence_queue_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", root)
    return module


def arguments(args):
    return ["queue", "--report", "runtime/report.json", "--report-sha256", "a" * 64,
        "--receipt", "runtime/discovery-receipt.json", "--receipt-sha256", "b" * 64,
        "--output", "runtime/result.json", "--priority-version", "v2",
        "--financial-export", str(args["financial_export_path"]),
        "--financial-export-sha256", args["financial_export_sha256"]]


@pytest.mark.parametrize("options", [
    ["--public-evidence-bundle", "runtime/bundle.json"],
    ["--public-evidence-sha256", "a" * 64],
    ["--priority-version", "v1", "--public-evidence-bundle", "runtime/bundle.json",
     "--public-evidence-sha256", "a" * 64],
])
def test_cli_requires_pair_and_v2_before_any_write(tmp_path, monkeypatch, options):
    module = cli(tmp_path, monkeypatch)
    args = dict(financial_export_path=tmp_path / "runtime/export.json", financial_export_sha256="c" * 64)
    monkeypatch.setattr(module, "write_new_json", forbidden)
    monkeypatch.setattr(sys, "argv", arguments(args) + options)
    before = snapshot(tmp_path)
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    assert snapshot(tmp_path) == before


def test_cli_rejects_before_builder_writer_or_explicit_enrichment(tmp_path, monkeypatch):
    args, packet, _ = bundle(tmp_path, monkeypatch)
    module = cli(tmp_path, monkeypatch)
    from value_investment_agent.application.research import value_research_priority_v2 as priority
    monkeypatch.setattr(priority, "build_value_research_priority_v2", forbidden)
    monkeypatch.setattr(module, "write_new_json", forbidden)
    monkeypatch.setattr(sys, "argv", arguments(args) + [
        "--public-evidence-bundle", str(args["bundle_path"]), "--public-evidence-sha256", "0" * 64,
        "--execute-enrichment", "--allow-public-evidence-downloads"])
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        module.main()
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("partial", [False, True])
def test_existing_v2_cli_builds_identical_queue_with_bound_bundle(tmp_path, monkeypatch, capsys, partial):
    from test_value_research_priority_v2 import _inputs
    base = _inputs(tmp_path)
    args, packet, _ = bundle(tmp_path, monkeypatch)
    if partial:
        add_gap(packet, "MISSING")
        rebind(args, packet)
    module = cli(tmp_path, monkeypatch)
    common = arguments(args) + [
        "--report", str(base["report_path"]), "--report-sha256", base["report_sha256"],
        "--receipt", str(base["receipt_path"]), "--receipt-sha256", base["receipt_sha256"]]
    monkeypatch.setattr(sys, "argv", common)
    assert module.main() == 0
    previous = json.loads((tmp_path / "runtime/result.json").read_bytes())
    monkeypatch.setattr(sys, "argv", common + [
        "--output", "runtime/with-bundle.json",
        "--public-evidence-bundle", str(args["bundle_path"]),
        "--public-evidence-sha256", args["bundle_sha256"]])
    assert module.main() == 0
    output = json.loads((tmp_path / "runtime/with-bundle.json").read_bytes())
    assert output == previous
    assert output["schema_version"] == "value-research-priority-v2"
    assert output["action"] == "no_order"
    assert output["new_verification_or_approval_count"] == 0
    capsys.readouterr()


def add_gap(packet, status):
    request = dict(symbol="600519", issuer_name="TEST_ONLY missing issuer",
                   period="2026-06-30", exchange="SSE")
    packet["requests"].append(request)
    packet["items"].append(dict(request=request, status=status, reused=False,
        fresh_index_checked=False, reason="TEST_ONLY unavailable", receipt=None,
        fact_snapshot=None, fact_status="NOT_RUN", adopted_fact_count=0))
    packet["status"] = "PARTIAL"


def rebind(args, packet):
    write(args["bundle_path"], packet)
    args["bundle_sha256"] = digest(args["bundle_path"])


@pytest.mark.parametrize("gap_status", ["MISSING", "UNSUPPORTED", "CONFLICT"])
@pytest.mark.parametrize("retained_status", ["VERIFIED", "PARTIAL"])
def test_partial_preserves_gaps_and_replays_healthy_original(tmp_path, monkeypatch, gap_status, retained_status):
    args, packet, acquired = bundle(tmp_path, monkeypatch)
    packet["items"][0]["status"] = retained_status
    add_gap(packet, gap_status)
    rebind(args, packet)
    before = snapshot(tmp_path)
    calls = []
    real = mod.load_retained_official_report

    def replay(**kwargs):
        calls.append(kwargs["symbol"])
        return real(**kwargs)

    monkeypatch.setattr(mod, "load_retained_official_report", replay)
    result = mod.validate_queue_public_evidence(**args)
    assert calls == ["000544"]
    assert result == packet
    assert result["status"] == "PARTIAL"
    assert result["items"][1]["status"] == gap_status
    assert result["items"][1]["receipt"] is None
    assert result["items"][1]["adopted_fact_count"] == 0
    assert result["scope"] == "REQUESTED_REPORTS_ONLY"
    assert result["formal_eligibility"] is False
    assert result["strict_historical_pit"] is False
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("status", ["MISSING", "UNSUPPORTED", "CONFLICT"])
def test_all_failed_sources_explicitly_rejected_without_writes(tmp_path, monkeypatch, status):
    args, packet, _ = bundle(tmp_path, monkeypatch)
    packet["items"][0].update(status=status, receipt=None, fact_snapshot=None,
        adopted_fact_count=0, fact_status="NOT_RUN")
    packet["status"] = "PARTIAL"
    rebind(args, packet)
    before = snapshot(tmp_path)
    monkeypatch.setattr(mod, "load_retained_official_report", forbidden)
    with pytest.raises(ValueError, match="PUBLIC_EVIDENCE_NO_VERIFIABLE_SOURCE"):
        mod.validate_queue_public_evidence(**args)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("bad_field", ["receipt", "fact_snapshot", "adopted_fact_count"])
def test_partial_gap_cannot_smuggle_facts_or_receipt(tmp_path, monkeypatch, bad_field):
    args, packet, _ = bundle(tmp_path, monkeypatch)
    add_gap(packet, "MISSING")
    packet["items"][1][bad_field] = (
        1 if bad_field == "adopted_fact_count" else packet["items"][0]["receipt"])
    rebind(args, packet)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        mod.validate_queue_public_evidence(**args)
    assert snapshot(tmp_path) == before


def test_partial_with_corrupt_declared_original_rejects_before_queue_write(tmp_path, monkeypatch):
    args, packet, acquired = bundle(tmp_path, monkeypatch)
    add_gap(packet, "MISSING")
    rebind(args, packet)
    (tmp_path / acquired["source"]["path"]).write_bytes(b"CORRUPTED RETAINED ORIGINAL")
    module = cli(tmp_path, monkeypatch)
    from value_investment_agent.application.research import value_research_priority_v2 as priority
    monkeypatch.setattr(priority, "build_value_research_priority_v2", forbidden)
    monkeypatch.setattr(module, "write_new_json", forbidden)
    monkeypatch.setattr(sys, "argv", arguments(args) + [
        "--public-evidence-bundle", str(args["bundle_path"]),
        "--public-evidence-sha256", args["bundle_sha256"],
        "--execute-enrichment", "--allow-public-evidence-downloads"])
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="Retained official evidence binding invalid"):
        module.main()
    assert snapshot(tmp_path) == before
