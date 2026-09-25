from datetime import date, datetime, timezone
import hashlib

import pytest

from scripts.verify_m5_financial_fact_candidates import verify


PAGE = """合并利润表
2026 年 1—6月
单位：元 币种：人民币
项目 附注 2026 年半年度 2025 年半年度
其中：营业收入 43 90,703,260,964.48 89,389,354,416.84
五、净利润（净亏损以“-”号填
列） 46,033,330,566.78 46,986,681,449.24
母公司利润表
2026 年 1—6月
单位：元 币种：人民币
项目 附注 2026 年半年度 2025 年半年度
四、净利润（净亏损以“-”号填
列） 17,062,381,326.67 18,679,911,266.59
"""


class _Page:
    def extract_text(self):
        return PAGE


class _Reader:
    def __init__(self, _path):
        self.pages = [_Page()]


def _inputs(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.verify_m5_financial_fact_candidates.PdfReader", _Reader)
    pdf = tmp_path / "official.pdf"
    pdf.write_bytes(b"frozen-pdf-bytes")
    pdf_sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    source_url = "https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF"
    candidate = {
        "schema_version": "m5-financial-fact-candidate-extraction-v1",
        "symbol": "600519", "announcement_id": "1225475868",
        "published_at": "2026-08-15T00:00:00+08:00", "action": "no_order",
        "pdf": {"sha256": pdf_sha, "page_count": 1},
        "numeric_facts": [{
            "field": "operating_revenue", "value": "90703260964.48", "unit": "CNY",
            "unit_basis": "yuan", "statement_scope": "consolidated",
            "statement_type": "consolidated_income_statement",
            "column_basis": "current_period_first_column", "page_number": 1,
            "page_text_sha256": hashlib.sha256(PAGE.encode()).hexdigest(),
            "source_line": "其中：营业收入 43 90,703,260,964.48 89,389,354,416.84",
        }],
    }
    source_record = {
        "announcement_id": "1225475868", "published_at": candidate["published_at"],
        "source_url": source_url,
        "evidence_refs": [{"sha256": pdf_sha, "source_url": source_url}],
    }
    return {
        "candidate": candidate, "pdf": pdf, "source_record": source_record,
        "period_start": date(2026, 1, 1), "period_end": date(2026, 6, 30),
        "available_at": datetime.fromisoformat("2026-08-16T00:00:00+08:00"),
        "verified_at": datetime(2026, 9, 25, tzinfo=timezone.utc),
        "run_id": "synthetic-verification-test",
    }


def test_verified_fact_binds_pdf_row_scope_unit_column_and_conservative_time(tmp_path, monkeypatch):
    args = _inputs(tmp_path, monkeypatch)
    envelope, pending = verify(**args)
    assert not pending
    fact = envelope.payload_object()["facts"][0]
    assert fact["value"] == "90703260964.48"
    assert fact["statement_scope"] == "consolidated"
    assert fact["report_period_end"] == "2026-06-30"
    assert envelope.identity.artifact_type == "financial_facts"


def test_wrong_pdf_or_source_binding_fails_closed(tmp_path, monkeypatch):
    args = _inputs(tmp_path, monkeypatch)
    args["pdf"].write_bytes(b"tampered")
    with pytest.raises(ValueError, match="PDF byte hash changed"):
        verify(**args)
    args = _inputs(tmp_path, monkeypatch)
    args["source_record"]["announcement_id"] = "other"
    with pytest.raises(ValueError, match="archived announcement index"):
        verify(**args)


def test_parent_profit_cannot_be_promoted_as_consolidated(tmp_path, monkeypatch):
    args = _inputs(tmp_path, monkeypatch)
    fact = args["candidate"]["numeric_facts"][0]
    fact.update(field="net_profit", value="17062381326.67",
                source_line="四、净利润（净亏损以“-”号填 列） 17,062,381,326.67 18,679,911,266.59")
    envelope, pending = verify(**args)
    assert envelope is None
    assert pending[0]["reason"] == "candidate_pdf_or_statement_context_mismatch"


def test_date_only_publication_cannot_be_used_at_midnight(tmp_path, monkeypatch):
    args = _inputs(tmp_path, monkeypatch)
    args["available_at"] = datetime.fromisoformat("2026-08-15T00:00:00+08:00")
    with pytest.raises(ValueError, match="conservative availability"):
        verify(**args)
