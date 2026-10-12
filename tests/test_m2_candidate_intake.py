from datetime import datetime, timezone
import hashlib
import json

import pytest

from value_investment_agent.application.product import m2_candidate_intake as intake


def test_pending_new_company_reaches_shared_application_without_admission(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    report = runtime / "lead.json"
    report.write_text("bound M2 lead", encoding="utf-8")
    queue_path = runtime / "queue.json"
    queue = {"schema_version": "value-research-queue-v1", "action": "no_order",
             "admission": "RESEARCH_QUEUE_ONLY", "budget": 1,
             "inputs": {"report_path": "runtime/lead.json", "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                        "receipt_path": "runtime/receipt.json", "receipt_sha256": "0" * 64,
                        "previous_queue_path": None, "previous_queue_sha256": None},
             "entries": [{"symbol": "600741", "queue_status": "SELECTED_FOR_DATA_CHECK"}]}
    queue_path.write_text(json.dumps(queue), encoding="utf-8")
    monkeypatch.setattr(intake, "build_value_research_queue", lambda **kwargs: queue)
    monkeypatch.setattr(intake, "_verified_lead", lambda root, path, digest, symbol: {
        "lead": {"symbol": "600741", "company_name": "华域汽车",
                 "channels": ["value", "cyclical"], "candidate_class": "LEAD"},
        "report_path": report, "report_hash": hashlib.sha256(report.read_bytes()).hexdigest(),
    })
    row = dict(secCode="600741", secName="华域汽车", orgId="gssh0600741",
               announcementId="1225052214", announcementTitle="华域汽车2025年年度报告",
               announcementTime=int(datetime(2026, 3, 31, tzinfo=timezone.utc).timestamp() * 1000),
               adjunctUrl="finalpage/2026-03-31/1225052214.PDF")
    monkeypatch.setattr(intake, "search_latest_reports", lambda symbol, name: [row])

    def search_window(symbol, start, end, issuer, raw_response_sink):
        body = json.dumps({"announcements": [row]}).encode("utf-8")
        raw_response_sink(body, {"sha256": hashlib.sha256(body).hexdigest(),
                                 "url": "https://www.cninfo.com.cn/new/hisAnnouncement/query"})
        return {"announcements": [row]}

    def download(url, target):
        target.write_bytes(b"%PDF-1.4 synthetic test bytes")
        return hashlib.sha256(target.read_bytes()).hexdigest()

    monkeypatch.setattr(intake, "search_announcement_window", search_window)
    monkeypatch.setattr(intake, "download_disclosure_pdf", download)
    result = intake.open_pending_m2_research(root=tmp_path, queue_path=queue_path,
        queue_sha256=hashlib.sha256(queue_path.read_bytes()).hexdigest(), symbol="600741",
        profile_id="mature_manufacturing",
        output_dir=runtime / "pending")
    assert result["action"] == "no_order"
    assert result["application_status"] == "COMPLETED_WITH_BLOCKERS"
    assert result["research_status"] == "PENDING_REVIEW"
    assert result["issuer_identity_status"] == "NOT_READY"
    assert result["valuation_status"] == "not_ready"
    assert result["decision_admitted"] is False and result["quote_admitted"] is False
    assert result["source_sha256"] == hashlib.sha256(b"%PDF-1.4 synthetic test bytes").hexdigest()
    assert (runtime / "pending" / "pending-research.json").is_file()
    monkeypatch.setattr(intake, "search_announcement_window", lambda *args, **kwargs: {
        "announcements": [{**row, "announcementTitle": "伪造标题"}],
    })
    with pytest.raises(ValueError, match="retained official index"):
        intake.open_pending_m2_research(root=tmp_path, queue_path=queue_path,
            queue_sha256=hashlib.sha256(queue_path.read_bytes()).hexdigest(), symbol="600741",
            profile_id="mature_manufacturing", output_dir=runtime / "tampered")


def test_m2_intake_rejects_unbound_report_before_network(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    report = runtime / "lead.json"
    report.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="queue hash mismatch"):
        intake.open_pending_m2_research(root=tmp_path, queue_path=report,
            queue_sha256="0" * 64, symbol="600741", profile_id="mature_manufacturing",
            output_dir=runtime / "pending")
    assert not (runtime / "pending").exists()
    with pytest.raises(ValueError, match="UNSUPPORTED_MODEL"):
        intake.open_pending_m2_research(root=tmp_path, queue_path=report,
            queue_sha256="0" * 64, symbol="600741", profile_id="cyclical_cash_return",
            output_dir=runtime / "unsupported")
