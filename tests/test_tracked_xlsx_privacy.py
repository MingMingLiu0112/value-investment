import hashlib
import zipfile

from openpyxl import Workbook

from scripts.current.audit_tracked_xlsx_privacy import (
    _raw_ooxml_audit, classify, classify_raw_only_candidates,
)


def test_private_context_takes_precedence():
    assert classify(context="股票账户 总资产", cell_type="n", number_format="General", formula=False) == "REQUIRES_PRIVATE_REVIEW"


def test_public_financial_context_requires_numeric_cell():
    assert classify(context="营业收入", cell_type="n", number_format="General", formula=False) == "POTENTIAL_PUBLIC_FINANCIAL_OR_MARKET_VALUE"
    assert classify(context="营业收入", cell_type="s", number_format="General", formula=False) == "UNKNOWN_LONG_NUMERIC"


def test_unlabeled_number_stays_unknown():
    assert classify(context="Sheet1", cell_type="n", number_format="General", formula=False) == "UNKNOWN_LONG_NUMERIC"


def test_unrelated_hash_context_does_not_override_private_keyword():
    assert classify(
        context="券商 sha256", cell_type="s", number_format="General",
        formula=False,
    ) == "REQUIRES_PRIVATE_REVIEW"


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


def test_raw_only_context_classifier_redacts_cached_formula_values(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = "账户"
    sheet["A2"] = "=1"
    sheet["B1"] = "财务审计摘要"
    sheet["B2"] = "=1"
    path = tmp_path / "tracked.xlsx"
    workbook.save(path)

    with zipfile.ZipFile(path) as source:
        parts = {name: source.read(name) for name in source.namelist()}
    xml = parts["xl/worksheets/sheet1.xml"].decode("utf-8")
    xml = xml.replace(
        "<c r=\"A2\"><f>1</f><v></v></c>",
        "<c r=\"A2\"><f>1</f><v>1234567890123456</v></c>",
    )
    xml = xml.replace(
        "<c r=\"B2\"><f>1</f><v></v></c>",
        "<c r=\"B2\"><f>1</f><v>9876543210987654</v></c>",
    )
    parts["xl/worksheets/sheet1.xml"] = xml.encode("utf-8")
    with zipfile.ZipFile(path, "w") as target:
        for name, content in parts.items():
            target.writestr(name, content)

    report = classify_raw_only_candidates(tmp_path, [path.name])
    assert report["raw_only_unique_fingerprints"] == 2
    assert report["category_fingerprint_counts"] == {
        "FORMULA_OR_DERIVED_VALUE": 1,
        "REQUIRES_PRIVATE_REVIEW": 1,
    }
    serialized = str(report)
    assert "1234567890123456" not in serialized
    assert "9876543210987654" not in serialized


def test_raw_only_classifier_excludes_openpyxl_visible_fingerprints(tmp_path):
    workbook = Workbook()
    workbook.active["A1"] = "账户"
    workbook.active["A2"] = "=1"
    path = tmp_path / "tracked.xlsx"
    workbook.save(path)
    with zipfile.ZipFile(path) as source:
        parts = {name: source.read(name) for name in source.namelist()}
    xml = parts["xl/worksheets/sheet1.xml"].decode("utf-8").replace(
        "<c r=\"A2\"><f>1</f><v></v></c>",
        "<c r=\"A2\"><f>1</f><v>1234567890123456</v></c>",
    )
    parts["xl/worksheets/sheet1.xml"] = xml.encode("utf-8")
    with zipfile.ZipFile(path, "w") as target:
        for name, content in parts.items():
            target.writestr(name, content)
    visible = {hashlib.sha256(b"1234567890123456").hexdigest()[:16]}
    report = classify_raw_only_candidates(
        tmp_path, [path.name], visible_fingerprints=visible,
    )
    assert report["raw_only_unique_fingerprints"] == 0
