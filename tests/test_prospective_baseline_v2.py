from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from value_investment_agent.domain.research.prospective_registration import prospective_registration_from_payload

import pytest

from value_investment_agent.application.product import prospective_baseline as module


ROOT = Path(__file__).resolve().parents[1]
SPEC = Path("config/prospective-baseline-verification-v3.json")


class AfterObservationStart(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 27, 1, 0, tzinfo=timezone.utc)


def _project(tmp_path: Path, monkeypatch, spec_path: Path = SPEC) -> tuple[Path, dict]:
    monkeypatch.setattr(module, "datetime", AfterObservationStart)
    root = tmp_path / "project"
    spec = json.loads((ROOT / spec_path).read_text(encoding="utf-8"))
    paths = [spec_path, Path(spec["registration_receipt_path"]), Path(spec["plan_path"]), Path(spec["baseline_input_path"]), Path(spec["supplemental_facts_path"])]
    for binding in spec["verified_sources"].values():
        paths.extend(Path(binding[key]) for key in ("scan_evidence_path", "index_path", "source_path"))
    for path in paths:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, root / path)
    def verify_registration(root, spec):
        receipt = json.loads((root / spec["registration_receipt_path"]).read_text(encoding="utf-8"))
        policy = prospective_registration_from_payload({"schema_version": "prospective-research-registration-v2", **receipt["registration"]})
        return receipt, policy
    monkeypatch.setattr(module, "_verify_registration", verify_registration)
    return root, spec


def _build(root: Path, spec_path: Path = SPEC):
    return module.build_verified_prospective_baselines(
        root=root, input_path=root / spec_path, output_path=root / "runtime" / "snapshot-v2.json",
    )


def _update_spec(root: Path, spec: dict) -> None:
    spec_path = Path(spec.get("_test_spec_path", SPEC.as_posix()))
    spec = {key: value for key, value in spec.items() if key != "_test_spec_path"}
    (root / spec_path).write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")


def _current_verified_project(tmp_path: Path, monkeypatch) -> tuple[Path, dict]:
    """Use a minimal, byte-consistent Yili slice of the successor evidence chain."""
    spec_path = Path("config/prospective-baseline-verification-v8.json")
    root, spec = _project(tmp_path, monkeypatch, spec_path)
    spec["_test_spec_path"] = spec_path.as_posix()
    class AfterSuccessorEvidence(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 27, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(module, "datetime", AfterSuccessorEvidence)

    baseline_path = root / spec["baseline_input_path"]
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    yili = next(case for case in baseline["cases"] if case["symbol"] == "600887")
    yili["known_facts"] = []
    for case in baseline["cases"]:
        if case is not yili:
            case["known_facts"] = []
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
    spec["baseline_input_sha256"] = hashlib.sha256(baseline_path.read_bytes()).hexdigest()

    supplement_path = root / spec["supplemental_facts_path"]
    supplement = json.loads(supplement_path.read_text(encoding="utf-8"))
    supplement["facts"] = [
        item for item in supplement["facts"] if item["case_id"] == yili["case_id"]
    ]
    supplement_path.write_text(json.dumps(supplement, ensure_ascii=False), encoding="utf-8")
    spec["supplemental_facts_sha256"] = hashlib.sha256(supplement_path.read_bytes()).hexdigest()
    active_fact_ids = {item["fact"]["fact_id"] for item in supplement["facts"]}
    spec["verified_sources"] = {
        fact_id: binding for fact_id, binding in spec["verified_sources"].items()
        if fact_id in active_fact_ids
    }
    _update_spec(root, spec)
    return root, spec


def test_verified_baseline_admits_only_byte_bound_public_fact(tmp_path, monkeypatch):
    root, spec = _current_verified_project(tmp_path, monkeypatch)
    result = _build(root, Path(spec["_test_spec_path"]))
    cards = {card["symbol"]: card for card in result["cards"]}
    assert result["schema_version"] == "prospective-baseline-snapshot-v2"
    assert result["action"] == "no_order"
    assert result["registration_time_assurance"] == "PROCESS_CLOCK_ONLY_UNATTESTED"
    assert result["strict_pit_admissible"] is False
    assert len(result["observation_ledger"]) == 6
    assert len(cards["600887"]["known_facts"]) == 6
    assert cards["600887"]["unadmitted_fact_ids"] == []
    assert result["supplemental_facts_sha256"] == spec["supplemental_facts_sha256"]
    assert {fact["fact_type"] for fact in cards["600887"]["known_facts"]} == {
        "revenue", "parent_attributable_profit", "operating_cash_flow",
        "asset_impairment_loss", "short_term_borrowing", "contract_liabilities",
    }
    assert all(fact["available_at"] == "2026-08-28T00:00:00+08:00" for fact in cards["600887"]["known_facts"])
    assert all(card["valuation_status"] == "VALUATION_NOT_READY" for card in cards.values())


def test_verified_shenhua_h1_facts_are_admitted_without_graduating_readiness(tmp_path, monkeypatch):
    spec_path = Path("config/prospective-baseline-verification-v8.json")
    root, _ = _project(tmp_path, monkeypatch, spec_path)
    class AfterGapfillScan(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 27, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(module, "datetime", AfterGapfillScan)
    result = _build(root, spec_path)
    shenhua = next(card for card in result["cards"] if card["symbol"] == "601088")
    h1 = {fact["fact_id"]: fact for fact in shenhua["known_facts"] if fact["report_period"] == "2026H1"}

    assert {fact_id: fact["value"] for fact_id, fact in h1.items()} == {
        "shenhua-2026h1-revenue": "189338",
        "shenhua-2026h1-parent-profit": "28715",
        "shenhua-2026h1-operating-cash-flow": "54664",
    }
    assert all(fact["unit"] == "CNY_MILLION" for fact in h1.values())
    assert all(fact["source_document_id"] == "cninfo:1225531759" for fact in h1.values())
    assert all(fact["available_at"] == "2026-08-30T00:00:00+08:00" for fact in h1.values())
    assert shenhua["unadmitted_fact_ids"] == ["shenhua-2025-operating-facts"]
    assert shenhua["valuation_status"] == "VALUATION_NOT_READY"
    assert result["strict_pit_admissible"] is False
    assert result["action"] == "no_order"


def test_verified_midea_h1_facts_are_admitted_without_graduating_readiness(tmp_path, monkeypatch):
    spec_path = Path("config/prospective-baseline-verification-v9.json")
    root, _ = _project(tmp_path, monkeypatch, spec_path)

    class AfterMideaScan(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 27, 10, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(module, "datetime", AfterMideaScan)
    result = _build(root, spec_path)
    cards = {card["symbol"]: card for card in result["cards"]}
    midea = cards["000333"]
    h1 = {fact["fact_id"]: fact for fact in midea["known_facts"] if fact["report_period"] == "2026H1"}

    assert {fact_id: fact["value"] for fact_id, fact in h1.items()} == {
        "midea-2026h1-revenue": "260042490",
        "midea-2026h1-parent-attributable-profit": "26446037",
        "midea-2026h1-operating-cash-flow": "37552090",
    }
    assert all(fact["unit"] == "CNY_THOUSAND" for fact in h1.values())
    assert all(fact["source_document_id"] == "cninfo:1225531404" for fact in h1.values())
    assert all(fact["available_at"] == "2026-08-30T00:00:00+08:00" for fact in h1.values())
    assert len(cards["600887"]["known_facts"]) == 6
    assert len(cards["601088"]["known_facts"]) == 6
    assert all(card["valuation_status"] == "VALUATION_NOT_READY" for card in cards.values())
    assert result["strict_pit_admissible"] is False
    assert result["action"] == "no_order"


def test_tampered_source_bytes_fail_closed(tmp_path, monkeypatch):
    root, spec = _current_verified_project(tmp_path, monkeypatch)
    source_binding = next(iter(spec["verified_sources"].values()))
    path = root / source_binding["source_path"]
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="source artifact byte hash mismatch"):
        _build(root, Path(spec["_test_spec_path"]))


def test_wrong_case_identity_fails_even_with_rehashed_input(tmp_path, monkeypatch):
    root, spec = _project(tmp_path, monkeypatch)
    source = root / spec["baseline_input_path"]
    baseline = json.loads(source.read_text(encoding="utf-8"))
    baseline["cases"][1]["symbol"] = "000333"
    source.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
    spec["baseline_input_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    _update_spec(root, spec)
    with pytest.raises(ValueError, match="identity or cutoff"):
        _build(root)


def test_wrong_company_name_fails_even_with_rehashed_input(tmp_path, monkeypatch):
    root, spec = _project(tmp_path, monkeypatch)
    source = root / spec["baseline_input_path"]
    baseline = json.loads(source.read_text(encoding="utf-8"))
    baseline["cases"][1]["company"] = "贵州茅台"
    source.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
    spec["baseline_input_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    _update_spec(root, spec)
    with pytest.raises(ValueError, match="identity or cutoff"):
        _build(root)


def test_future_claim_fails_even_with_rehashed_input(tmp_path, monkeypatch):
    root, spec = _current_verified_project(tmp_path, monkeypatch)
    source = root / spec["supplemental_facts_path"]
    supplement = json.loads(source.read_text(encoding="utf-8"))
    supplement["facts"][0]["fact"]["available_at"] = "2026-10-01T00:00:00+08:00"
    source.write_text(json.dumps(supplement, ensure_ascii=False), encoding="utf-8")
    spec["supplemental_facts_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    _update_spec(root, spec)
    with pytest.raises(ValueError, match="source availability"):
        _build(root, Path(spec["_test_spec_path"]))


def test_prestart_build_is_rejected(tmp_path, monkeypatch):
    root, _ = _project(tmp_path, monkeypatch)
    class BeforeObservationStart(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 27, 0, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(module, "datetime", BeforeObservationStart)
    with pytest.raises(ValueError, match="observation start"):
        _build(root)


def test_real_registration_commit_contains_unchanged_plan():
    spec = json.loads((ROOT / SPEC).read_text(encoding="utf-8"))
    receipt, registration = module.verify_prospective_registration_receipt(
        root=ROOT, receipt_path=spec["registration_receipt_path"],
        receipt_sha256=spec["registration_receipt_sha256"], plan_path=spec["plan_path"],
    )
    assert receipt["git_commit"]
    assert len(registration.cases) == 3


def test_untrusted_registration_commit_fails_closed(tmp_path, monkeypatch):
    root, _ = _project(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "_verify_registration", lambda *args: (_ for _ in ()).throw(ValueError("registration commit ancestry is not verified")))
    with pytest.raises(ValueError, match="commit ancestry"):
        _build(root)


def test_duplicate_baseline_case_ids_are_rejected(tmp_path, monkeypatch):
    root, spec = _project(tmp_path, monkeypatch)
    path = root / spec["baseline_input_path"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cases"][1]["case_id"] = payload["cases"][0]["case_id"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    spec["baseline_input_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    _update_spec(root, spec)
    with pytest.raises(ValueError, match="baseline cases differ"):
        _build(root)


def test_pdf_page_binding_rejects_rehashed_fabricated_value():
    spec = json.loads((ROOT / SPEC).read_text(encoding="utf-8"))
    binding = spec["verified_sources"]["yili-2026h1-financial-quality"]
    pdf = (ROOT / binding["source_path"]).read_bytes()
    fact = {
        "fact_type": "revenue", "value": "999999999999.99", "unit": "CNY",
        "scope": "consolidated", "scope_label": "合并利润表",
        "physical_page": 52, "printed_page": 49, "source_label": "营业收入",
    }
    with pytest.raises(ValueError, match="first reported period column"):
        module._verify_fact_text(pdf, fact, binding)


def test_pdf_page_binding_rejects_fact_type_label_mismatch():
    spec = json.loads((ROOT / SPEC).read_text(encoding="utf-8"))
    binding = spec["verified_sources"]["yili-2026h1-financial-quality"]
    pdf = (ROOT / binding["source_path"]).read_bytes()
    fact = {
        "fact_type": "revenue", "value": "2,455,875,173.02", "unit": "CNY",
        "scope": "consolidated", "scope_label": "合并利润表",
        "physical_page": 52, "printed_page": 49, "source_label": "资产减值损失",
    }
    with pytest.raises(ValueError, match="canonical report line"):
        module._verify_fact_text(pdf, fact, binding)


@pytest.mark.parametrize("forged_value", ["61776746682.68", "5"])
def test_pdf_page_binding_rejects_comparative_or_substring_values(forged_value):
    spec = json.loads((ROOT / SPEC).read_text(encoding="utf-8"))
    binding = spec["verified_sources"]["yili-2026h1-financial-quality"]
    pdf = (ROOT / binding["source_path"]).read_bytes()
    fact = {
        "fact_type": "revenue", "value": forged_value, "unit": "CNY",
        "scope": "consolidated", "scope_label": "合并利润表",
        "physical_page": 52, "printed_page": 49, "source_label": "营业收入",
    }
    with pytest.raises(ValueError, match="first reported period column"):
        module._verify_fact_text(pdf, fact, binding)


def test_pdf_page_binding_accepts_cited_report_value():
    spec = json.loads((ROOT / SPEC).read_text(encoding="utf-8"))
    binding = spec["verified_sources"]["yili-2026h1-financial-quality"]
    pdf = (ROOT / binding["source_path"]).read_bytes()
    fact = {
        "fact_type": "revenue", "value": "64,330,936,547.38", "unit": "CNY",
        "scope": "consolidated", "scope_label": "合并利润表",
        "physical_page": 52, "printed_page": 49, "source_label": "营业收入",
    }
    module._verify_fact_text(pdf, fact, binding)


def test_pdf_page_binding_supports_each_explicit_fact_contract():
    spec = json.loads((ROOT / SPEC).read_text(encoding="utf-8"))
    binding = spec["verified_sources"]["yili-2026h1-financial-quality"]
    pdf = (ROOT / binding["source_path"]).read_bytes()
    rows = [
        ("revenue", "64,330,936,547.38", 52, 49, "营业收入", "合并利润表"),
        ("parent_attributable_profit", "5,758,628,097.79", 53, 50, "归属于母公司股东的净利润", "合并利润表"),
        ("operating_cash_flow", "9,759,147,483.18", 55, 52, "经营活动产生的现金流量净额", "合并现金流量表"),
        ("asset_impairment_loss", "-2,455,875,173.02", 52, 49, "资产减值损失", "合并利润表"),
        ("short_term_borrowing", "64,677,193,034.15", 49, 46, "短期借款", "合并资产负债表"),
        ("contract_liabilities", "4,948,856,599.18", 49, 46, "合同负债", "合并资产负债表"),
    ]
    for fact_type, value, physical_page, printed_page, label, scope_label in rows:
        module._verify_fact_text(pdf, {
            "fact_type": fact_type, "value": value, "unit": "CNY",
            "scope": "consolidated", "scope_label": scope_label,
            "physical_page": physical_page, "printed_page": printed_page,
            "source_label": label,
        }, binding)


@pytest.mark.parametrize("fact_type,value,label", [
    ("revenue", "189338", "营业收入"),
    ("parent_attributable_profit", "28715", "归属于上市公司股东的净利润"),
    ("operating_cash_flow", "54664", "经营活动产生的现金流量净额"),
])
def test_shenhua_2026h1_facts_bind_to_page_six_and_current_column(fact_type, value, label):
    source_path = ROOT / "runtime/prospective-public-event-20260927/gapfill-601088-20260927T070618883648Z/1225531759.pdf"
    binding = {"report_period": "2026H1"}
    fact = {
        "fact_type": fact_type,
        "value": value,
        "unit": "CNY_MILLION",
        "scope": "report_summary",
        "scope_label": "主要会计数据",
        "physical_page": 6,
        "printed_page": 6,
        "source_label": label,
        "source_document_id": "cninfo:1225531759",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-08-29/1225531759.PDF",
    }
    module._verify_fact_text(source_path.read_bytes(), fact, binding)


def test_shenhua_2026h1_fact_rejects_restated_comparative_column():
    source_path = ROOT / "runtime/prospective-public-event-20260927/gapfill-601088-20260927T070618883648Z/1225531759.pdf"
    fact = {
        "fact_type": "revenue", "value": "175423", "unit": "CNY_MILLION",
        "scope": "report_summary", "scope_label": "主要会计数据",
        "physical_page": 6, "printed_page": 6, "source_label": "营业收入",
        "source_document_id": "cninfo:1225531759",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-08-29/1225531759.PDF",
    }
    with pytest.raises(ValueError, match="first reported period column"):
        module._verify_fact_text(source_path.read_bytes(), fact, {"report_period": "2026H1"})


@pytest.mark.parametrize("headers", [
    "主要会计数据 2026年上半年 2025年上半年 变动",
    "主要会计数据 2025年上半年 2026年上半年 变动",
    "主要会计数据 2025年上半年 变动",
])
def test_shenhua_h1_current_value_requires_explicit_ordered_period_headers(headers, monkeypatch):
    import pypdf

    class Page:
        def extract_text(self):
            return (
                "6\n主要会计数据\n单位：人民币百万元\n2026年上半年\n"
                f"{headers}\n营业收入 189,338 175,423 138,109 7.9\n"
            )

    class Reader:
        pages = [Page() for _ in range(6)]

        def __init__(self, _):
            pass

    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    fact = {
        "fact_type": "revenue", "value": "189338", "unit": "CNY_MILLION",
        "scope": "report_summary", "scope_label": "主要会计数据",
        "physical_page": 6, "printed_page": 6, "source_label": "营业收入",
        "source_document_id": "cninfo:1225531759",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-08-29/1225531759.PDF",
    }
    if headers.startswith("主要会计数据 2026年上半年 2025年上半年"):
        monkeypatch.setattr(module, "_verify_shenhua_h1_column_geometry", lambda *_: None)
        module._verify_fact_text(b"synthetic PDF", fact, {"report_period": "2026H1"})
    else:
        with pytest.raises(ValueError, match="period columns are not explicitly ordered"):
            module._verify_fact_text(b"synthetic PDF", fact, {"report_period": "2026H1"})


@pytest.mark.parametrize("value", ["189,338", "28,715", "54,664"])
def test_shenhua_h1_column_geometry_rejects_current_value_under_comparison_column(monkeypatch, value):
    import pypdfium2

    source_path = ROOT / "runtime/prospective-public-event-20260927/gapfill-601088-20260927T070618883648Z/1225531759.pdf"
    pdf = source_path.read_bytes()
    real_document_type = pypdfium2.PdfDocument
    source_document = real_document_type(pdf)
    source_text_page = source_document[5].get_textpage()
    source_text = source_text_page.get_text_range()
    token_start = source_text.index(value)

    class TextPage:
        def get_text_range(self):
            return source_text

        def count_chars(self):
            return source_text_page.count_chars()

        def get_charbox(self, index):
            box = source_text_page.get_charbox(index)
            if token_start <= index < token_start + len(value):
                return (box[0] + 100, box[1], box[2] + 100, box[3])
            return box

    class Page:
        def get_textpage(self):
            return TextPage()

    class Document:
        def __getitem__(self, _):
            return Page()

        def close(self):
            source_document.close()

    monkeypatch.setattr(pypdfium2, "PdfDocument", lambda _: Document())
    with pytest.raises(ValueError, match="do not align under their period columns"):
        module._verify_shenhua_h1_column_geometry(pdf, {
            "physical_page": 6,
            "source_label": {
                "189,338": "营业收入",
                "28,715": "归属于上市公司股东的净利润",
                "54,664": "经营活动产生的现金流量净额",
            }[value],
        })


def test_shenhua_h1_column_geometry_rejects_missing_fact_character_coordinates(monkeypatch):
    import pypdfium2

    source_path = ROOT / "runtime/prospective-public-event-20260927/gapfill-601088-20260927T070618883648Z/1225531759.pdf"
    pdf = source_path.read_bytes()
    real_document_type = pypdfium2.PdfDocument
    source_document = real_document_type(pdf)
    source_text_page = source_document[5].get_textpage()
    source_text = source_text_page.get_text_range()
    token_start = source_text.index("54,664")

    class TextPage:
        def get_text_range(self):
            return source_text

        def count_chars(self):
            return source_text_page.count_chars()

        def get_charbox(self, index):
            if token_start <= index < token_start + len("54,664"):
                return None
            return source_text_page.get_charbox(index)

    class Page:
        def get_textpage(self):
            return TextPage()

    class Document:
        def __getitem__(self, _):
            return Page()

        def close(self):
            source_document.close()

    monkeypatch.setattr(pypdfium2, "PdfDocument", lambda _: Document())
    with pytest.raises(ValueError, match="PDF character coordinates are incomplete"):
        module._verify_shenhua_h1_column_geometry(pdf, {
            "physical_page": 6,
            "source_label": "经营活动产生的现金流量净额",
        })


@pytest.mark.parametrize("fact_type,value,label", [
    ("revenue", "456451731", "营业收入（千元）"),
    ("parent_attributable_profit", "43945411", "归属于上市公司股东的净利润（千元）"),
    ("operating_cash_flow", "53345930", "经营活动产生的现金流量净额（千元）"),
])
def test_annual_summary_fact_contract_uses_native_thousand_cny_units(
    fact_type, value, label, monkeypatch,
):
    import pypdf

    class Page:
        def extract_text(self):
            return (
                "2025 年年度报告全文\n8\n六、主要会计数据和财务指标\n"
                "2025 年 2024 年 本年比上年\n"
                f"{label} {value} 123456 1.0% 789012\n"
            )

    class Reader:
        pages = [Page()]

        def __init__(self, _):
            pass

    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    module._verify_fact_text(
        b"synthetic pdf bytes",
        {
            "fact_type": fact_type,
            "value": value,
            "unit": "CNY_THOUSAND",
            "scope": "report_summary",
            "scope_label": "主要会计数据和财务指标",
            "physical_page": 1,
            "printed_page": 8,
            "source_label": label,
        },
        {"report_period": "2025FY"},
    )


def test_annual_summary_fact_rejects_comparative_period_value(monkeypatch):
    import pypdf

    class Page:
        def extract_text(self):
            return (
                "2025 年年度报告全文\n8\n六、主要会计数据和财务指标\n"
                "2025 年 2024 年 本年比上年\n营业收入（千元） 456451731 407149600 12.11% 372037280\n"
            )

    class Reader:
        pages = [Page()]

        def __init__(self, _):
            pass

    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    with pytest.raises(ValueError, match="first reported period column"):
        module._verify_fact_text(
            b"synthetic pdf bytes",
            {
                "fact_type": "revenue",
                "value": "407149600",
                "unit": "CNY_THOUSAND",
                "scope": "report_summary",
                "scope_label": "主要会计数据和财务指标",
                "physical_page": 1,
                "printed_page": 8,
                "source_label": "营业收入（千元）",
            },
            {"report_period": "2025FY"},
        )


@pytest.mark.parametrize("fact_type,value,label", [
    ("revenue", "294916", "营业收入"),
    ("parent_attributable_profit", "52849", "归属于本公司股东的净利润"),
    ("operating_cash_flow", "75059", "经营活动产生的现金流量净额"),
])
def test_annual_summary_cny_million_fact_contract(fact_type, value, label, monkeypatch):
    import pypdf

    class Page:
        def extract_text(self):
            return (
                "2025 年年度报告全文\n8\n近三年主要会计数据和财务指标\n"
                "单位：百万元\n2025 年 2024 年 2023 年\n"
                f"{label[:8]}\n{label[8:]}\n{value} 123456 234567\n"
            )

    class Reader:
        pages = [Page()]

        def __init__(self, _):
            pass

    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    module._verify_fact_text(
        b"synthetic pdf bytes",
        {
            "fact_type": fact_type, "value": value, "unit": "CNY_MILLION",
            "scope": "report_summary", "scope_label": "近三年主要会计数据和财务指标",
            "physical_page": 1, "printed_page": 8, "source_label": label,
            "source_document_id": "cninfo:1225064293",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-31/1225064293.PDF",
        },
        {"report_period": "2025FY"},
    )


def test_annual_summary_cny_million_rejects_comparative_period_value(monkeypatch):
    import pypdf

    class Page:
        def extract_text(self):
            return (
                "2025 年年度报告全文\n8\n近三年主要会计数据和财务指标\n单位：百万元\n"
                "2025 年 2024 年 2023 年\n营业\n收入\n294916 316059 354790\n"
            )

    class Reader:
        pages = [Page()]

        def __init__(self, _):
            pass

    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    with pytest.raises(ValueError, match="first reported period column"):
        module._verify_fact_text(
            b"synthetic pdf bytes",
            {
                "fact_type": "revenue", "value": "316059", "unit": "CNY_MILLION",
                "scope": "report_summary", "scope_label": "近三年主要会计数据和财务指标",
                "physical_page": 1, "printed_page": 8, "source_label": "营业收入",
                "source_document_id": "cninfo:1225064293",
                "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-31/1225064293.PDF",
            },
            {"report_period": "2025FY"},
        )


@pytest.mark.parametrize(("fact_type", "value", "label"), [
    ("revenue", "260042490", "营业收入（千元）"),
    ("parent_attributable_profit", "26446037", "归属于上市公司股东的净利润（千元）"),
    ("operating_cash_flow", "37552090", "经营活动产生的现金流量净额（千元）"),
])
def test_midea_2026h1_summary_facts_bind_to_official_page_seven(fact_type, value, label):
    source = Path(
        "runtime/prospective-public-event-20260927/gapfill-000333-20260927T091704729284Z/1225531404.pdf"
    )
    fact = {
        "fact_type": fact_type,
        "value": value,
        "unit": "CNY_THOUSAND",
        "scope": "report_summary",
        "scope_label": "主要会计数据和财务指标",
        "source_label": label,
        "physical_page": 7,
        "printed_page": 7,
        "source_document_id": "cninfo:1225531404",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-08-29/1225531404.PDF",
    }
    module._verify_fact_text(source.read_bytes(), fact, {"report_period": "2026H1"})

    fact["value"] = {
        "revenue": "251123714",
        "parent_attributable_profit": "26013690",
        "operating_cash_flow": "37281015",
    }[fact_type]
    with pytest.raises(ValueError, match="first reported period column"):
        module._verify_fact_text(source.read_bytes(), fact, {"report_period": "2026H1"})


def test_wrong_source_namespace_fails_even_with_rehashed_supplement(tmp_path, monkeypatch):
    root, spec = _current_verified_project(tmp_path, monkeypatch)
    supplement_path = root / spec["supplemental_facts_path"]
    supplement = json.loads(supplement_path.read_text(encoding="utf-8"))
    supplement["facts"][0]["fact"]["source_document_id"] = "hkex:1225511409"
    supplement_path.write_text(json.dumps(supplement, ensure_ascii=False), encoding="utf-8")
    spec["supplemental_facts_sha256"] = hashlib.sha256(supplement_path.read_bytes()).hexdigest()
    _update_spec(root, spec)
    with pytest.raises(ValueError, match="namespace differs"):
        _build(root, Path(spec["_test_spec_path"]))
