from openpyxl import Workbook

from scripts.current.audit_tracked_xlsx_privacy import _raw_ooxml_audit, classify


def test_private_context_takes_precedence():
    assert classify("1234567890123456", context="股票账户 总资产", cell_type="n", number_format="General", formula=False) == "REQUIRES_PRIVATE_REVIEW"


def test_public_financial_context_requires_numeric_cell():
    assert classify("1234567890123456", context="营业收入", cell_type="n", number_format="General", formula=False) == "POTENTIAL_PUBLIC_FINANCIAL_OR_MARKET_VALUE"
    assert classify("1234567890123456", context="营业收入", cell_type="s", number_format="General", formula=False) == "UNKNOWN_LONG_NUMERIC"


def test_unlabeled_number_stays_unknown():
    assert classify("1234567890123456", context="Sheet1", cell_type="n", number_format="General", formula=False) == "UNKNOWN_LONG_NUMERIC"


def test_hex_digest_overrides_ambiguous_private_keyword_context():
    assert classify(
        "1234567890123456", context="券商", cell_type="s", number_format="General",
        formula=False, value_text="a" * 64,
    ) == "HASH_OR_RECEIPT_FRAGMENT"


def test_raw_ooxml_audit_is_redacted_and_reports_private_context_count(tmp_path):
    workbook = Workbook()
    workbook.active["A1"] = "1234567890123456"
    path = tmp_path / "tracked.xlsx"
    workbook.save(path)
    report = _raw_ooxml_audit(tmp_path, [path.name], set())
    assert report["candidate_count"] == 1
    assert report["raw_only_unique_fingerprints"] == 1
    assert report["raw_only_private_context_fingerprints"] == 0
    assert "1234567890123456" not in str(report)
