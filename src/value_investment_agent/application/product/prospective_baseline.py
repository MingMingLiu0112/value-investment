"""Build append-only public baseline cards for prospective research cases."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import hashlib
import re
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any, Mapping
from decimal import Decimal, InvalidOperation

from .common import load_json_object, require_inside, sha256_file, write_new_json
from .prospective_registration import verify_prospective_registration_receipt


def _verify_shenhua_h1_column_geometry(pdf_bytes: bytes, fact: Mapping[str, Any]) -> None:
    import pypdfium2

    document = pypdfium2.PdfDocument(pdf_bytes)
    try:
        page = document[int(fact["physical_page"]) - 1]
        text_page = page.get_textpage()
        text = text_page.get_text_range()
        if not text or len(text) != text_page.count_chars():
            raise ValueError("PDF text and coordinate indexes do not align")

        compact: list[str] = []
        source_indexes: list[int] = []
        for index, char in enumerate(text):
            if not char.isspace():
                compact.append(char)
                source_indexes.append(index)
        compact_text = "".join(compact)

        def bounds(start: int, end: int) -> tuple[float, float, float, float]:
            boxes = [text_page.get_charbox(source_indexes[index]) for index in range(start, end)]
            boxes = [box for box in boxes if box and len(box) == 4]
            if len(boxes) < end - start:
                raise ValueError("PDF character coordinates are incomplete")
            return (
                min(float(box[0]) for box in boxes), min(float(box[1]) for box in boxes),
                max(float(box[2]) for box in boxes), max(float(box[3]) for box in boxes),
            )

        def unique_bounds(needle: str) -> tuple[int, tuple[float, float, float, float]]:
            start = compact_text.find(needle)
            if start < 0 or compact_text.find(needle, start + 1) >= 0:
                raise ValueError(f"PDF coordinate text is missing or ambiguous: {needle}")
            return start, bounds(start, start + len(needle))

        _, current_header = unique_bounds("2026年上半年")
        _, comparison_header = unique_bounds("2025年上半年")
        current_center = (current_header[0] + current_header[2]) / 2
        comparison_center = (comparison_header[0] + comparison_header[2]) / 2
        if current_center >= comparison_center or current_header[2] >= comparison_header[0]:
            raise ValueError("current and comparative headers do not define distinct ordered columns")
        boundary = (current_header[2] + comparison_header[0]) / 2

        label = str(fact["source_label"])
        rows = [line for line in text.splitlines() if label in line]
        if len(rows) != 1:
            raise ValueError("fact label must resolve to one PDF coordinate row")
        line = rows[0]
        line_offset = text.find(line)
        if line_offset < 0:
            raise ValueError("fact row cannot be located in PDF text")
        label_offset = line.find(label) + len(label)
        number_matches = list(re.finditer(r"(?<![\d.])-?\d[\d,]*(?:\.\d+)?(?![\d.])", line[label_offset:]))
        if len(number_matches) < 3:
            raise ValueError("fact row lacks current and comparative period values")

        number_boxes = []
        for match in number_matches[:3]:
            start = line_offset + label_offset + match.start()
            end = line_offset + label_offset + match.end()
            source_positions = [i for i, original in enumerate(source_indexes) if start <= original < end]
            if not source_positions:
                raise ValueError("fact row number has no PDF coordinates")
            number_boxes.append(bounds(source_positions[0], source_positions[-1] + 1))

        centers = [(box[0] + box[2]) / 2 for box in number_boxes]
        if not (current_center < comparison_center and centers[0] < boundary < centers[1] <= centers[2]):
            raise ValueError("current and comparative fact values do not align under their period columns")
        if number_boxes[0][3] >= min(current_header[1], comparison_header[1]):
            raise ValueError("fact row does not appear below the period header")
    finally:
        document.close()


def _verify_fact_text(pdf_bytes: bytes, fact: Mapping[str, Any], binding: Mapping[str, Any]) -> None:
    from pypdf import PdfReader

    midea_h1 = (
        binding.get("report_period") == "2026H1"
        and fact.get("source_document_id") == "cninfo:1225531404"
        and fact.get("source_url") == "https://static.cninfo.com.cn/finalpage/2026-08-29/1225531404.PDF"
    )

    fact_contracts = {
        ("2026H1", "revenue"): ("营业收入", "合并利润表", "CNY", "consolidated"),
        ("2026H1", "parent_attributable_profit"): (
            "归属于母公司股东的净利润", "合并利润表", "CNY", "consolidated",
        ),
        ("2026H1", "operating_cash_flow"): (
            "经营活动产生的现金流量净额", "合并现金流量表", "CNY", "consolidated",
        ),
        ("2026H1", "asset_impairment_loss"): (
            "资产减值损失", "合并利润表", "CNY", "consolidated",
        ),
        ("2026H1", "short_term_borrowing"): (
            "短期借款", "合并资产负债表", "CNY", "consolidated",
        ),
        ("2026H1", "contract_liabilities"): (
            "合同负债", "合并资产负债表", "CNY", "consolidated",
        ),
        ("2025FY", "revenue"): (
            "营业收入（千元）", "主要会计数据和财务指标", "CNY_THOUSAND", "report_summary",
        ),
        ("2025FY", "parent_attributable_profit"): (
            "归属于上市公司股东的净利润（千元）",
            "主要会计数据和财务指标", "CNY_THOUSAND", "report_summary",
        ),
        ("2025FY", "operating_cash_flow"): (
            "经营活动产生的现金流量净额（千元）",
            "主要会计数据和财务指标", "CNY_THOUSAND", "report_summary",
        ),
        ("2025FY", "revenue_cny_million"): (
            "营业收入", "近三年主要会计数据和财务指标", "CNY_MILLION", "report_summary",
        ),
        ("2025FY", "parent_attributable_profit_cny_million"): (
            "归属于本公司股东的净利润", "近三年主要会计数据和财务指标", "CNY_MILLION", "report_summary",
        ),
        ("2025FY", "operating_cash_flow_cny_million"): (
            "经营活动产生的现金流量净额", "近三年主要会计数据和财务指标", "CNY_MILLION", "report_summary",
        ),
    }
    fact_type = fact.get("fact_type")
    report_period = binding.get("report_period")
    shenhua_h1 = (
        report_period == "2026H1"
        and fact.get("source_document_id") == "cninfo:1225531759"
        and fact.get("source_url") == "https://static.cninfo.com.cn/finalpage/2026-08-29/1225531759.PDF"
    )
    shenhua_h1_contracts = {
        "revenue": ("营业收入", "主要会计数据", "CNY_MILLION", "report_summary"),
        "parent_attributable_profit": (
            "归属于上市公司股东的净利润", "主要会计数据", "CNY_MILLION", "report_summary",
        ),
        "operating_cash_flow": (
            "经营活动产生的现金流量净额", "主要会计数据", "CNY_MILLION", "report_summary",
        ),
    }
    midea_h1_contracts = {
        "revenue": (
            "营业收入（千元）", "主要会计数据和财务指标", "CNY_THOUSAND", "report_summary",
        ),
        "parent_attributable_profit": (
            "归属于上市公司股东的净利润（千元）",
            "主要会计数据和财务指标", "CNY_THOUSAND", "report_summary",
        ),
        "operating_cash_flow": (
            "经营活动产生的现金流量净额（千元）",
            "主要会计数据和财务指标", "CNY_THOUSAND", "report_summary",
        ),
    }
    contract = (
        midea_h1_contracts.get(fact_type)
        if midea_h1
        else shenhua_h1_contracts.get(fact_type)
        if shenhua_h1
        else fact_contracts.get((report_period, fact_type))
    )
    if report_period == "2025FY" and fact.get("unit") == "CNY_MILLION":
        contracts_by_type = {
            "revenue": ("营业收入", "近三年主要会计数据和财务指标", "CNY_MILLION", "report_summary"),
            "parent_attributable_profit": (
                "归属于本公司股东的净利润", "近三年主要会计数据和财务指标", "CNY_MILLION", "report_summary",
            ),
            "operating_cash_flow": (
                "经营活动产生的现金流量净额", "近三年主要会计数据和财务指标", "CNY_MILLION", "report_summary",
            ),
        }
        contract = contracts_by_type.get(fact_type, contract)
    if contract is None:
        raise ValueError("unsupported item-level fact_type and report period")
    value = fact.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float, str)) or str(value).strip() in {"", "None"}:
        raise ValueError("item-level fact value is required")
    unit = fact.get("unit")
    scope = fact.get("scope")
    scope_label = fact.get("scope_label")
    expected_label, expected_scope_label, expected_unit, expected_scope = contract
    label = fact.get("source_label")
    physical_page = fact.get("physical_page")
    printed_page = fact.get("printed_page")
    if unit != expected_unit or scope != expected_scope or not isinstance(scope_label, str) or not scope_label.strip():
        raise ValueError("fact unit, report period, or consolidation scope is not verified")
    if label != expected_label or scope_label != expected_scope_label:
        raise ValueError("fact type does not match the canonical report line or statement scope")
    if expected_unit == "CNY_MILLION":
        expected_source = (
            ("cninfo:1225531759", "https://static.cninfo.com.cn/finalpage/2026-08-29/1225531759.PDF")
            if shenhua_h1
            else ("cninfo:1225064293", "https://static.cninfo.com.cn/finalpage/2026-03-31/1225064293.PDF")
        )
        if (fact.get("source_document_id"), fact.get("source_url")) != expected_source:
            raise ValueError("CNY_MILLION summary contract is restricted to the verified Shenhua source")
    if midea_h1 and (
        fact.get("source_document_id") != "cninfo:1225531404"
        or fact.get("source_url") != "https://static.cninfo.com.cn/finalpage/2026-08-29/1225531404.PDF"
    ):
        raise ValueError("Midea H1 summary contract is restricted to its verified CNINFO source")
    if not isinstance(physical_page, int) or physical_page < 1:
        raise ValueError("fact source label and physical page are required")
    if not isinstance(printed_page, int) or printed_page < 1:
        raise ValueError("fact printed page is required")
    reader = PdfReader(__import__("io").BytesIO(pdf_bytes))
    if physical_page > len(reader.pages):
        raise ValueError("fact physical page is outside the source PDF")
    text = reader.pages[physical_page - 1].extract_text() or ""
    adjacent = "\n".join(
        reader.pages[index].extract_text() or ""
        for index in range(max(0, physical_page - 2), physical_page)
    )
    page_marker = re.search(rf"(?m)^\s*{printed_page}\s*$", text)
    if midea_h1:
        page_marker = re.search(rf"(?m)^\s*{printed_page}\s*$", text)
    elif report_period == "2026H1" and not shenhua_h1:
        page_marker = re.search(rf"(?<!\d){printed_page}\s*/\s*\d+", text)
    if not page_marker:
        raise ValueError("printed page does not match the cited physical PDF page")
    context_compact = re.sub(r"\s+", "", adjacent)
    period_marker = (
        "本报告期" if midea_h1
        else "2026年上半年" if shenhua_h1
        else "2026年6月30日"
        if report_period == "2026H1" and fact_type in {"short_term_borrowing", "contract_liabilities"}
        else "2026年1—6月" if report_period == "2026H1"
        else "2025年" if expected_unit == "CNY_MILLION"
        else "主要会计数据和财务指标"
    )
    if re.sub(r"\s+", "", scope_label) not in context_compact or period_marker not in context_compact:
        raise ValueError("report scope or period is absent from the cited PDF page context")
    if report_period == "2026H1":
        if shenhua_h1 and not any(
            marker in context_compact for marker in ("单位：百万元", "单位：人民币百万元")
        ):
            raise ValueError("reported CNY million scale is absent from the cited Shenhua page")
        if shenhua_h1:
            current_column_header = "主要会计数据2026年上半年2025年上半年变动"
            if current_column_header not in re.sub(r"\s+", "", text):
                raise ValueError("current and comparative period columns are not explicitly ordered")
        if midea_h1 and "千元" not in context_compact:
            raise ValueError("reported CNY thousand scale is absent from the cited Midea page")
        if not shenhua_h1 and not midea_h1 and ("单位：元" not in context_compact or "人民币" not in context_compact):
            raise ValueError("reported currency unit is absent from the cited PDF page")
    if report_period == "2025FY":
        compact_text = re.sub(r"\s+", "", text)
        unit_marker = "百万元" if expected_unit == "CNY_MILLION" else "千元"
        if unit_marker not in compact_text:
            raise ValueError("reported CNY unit scale is absent from the cited PDF page")
    lines = text.splitlines()
    compact_chars: list[str] = []
    owner_lines: list[int] = []
    for line_index, line in enumerate(lines):
        for char in line:
            if not char.isspace():
                compact_chars.append(char)
                owner_lines.append(line_index)
    compact_page = "".join(compact_chars)
    positions: list[int] = []
    search_from = 0
    while True:
        found = compact_page.find(label, search_from)
        if found < 0:
            break
        positions.append(found)
        search_from = found + 1
    if len(positions) != 1:
        raise ValueError("fact label must resolve to exactly one table row on the cited PDF page")
    label_start = positions[0]
    label_end_line = owner_lines[label_start + len(label) - 1]
    start_line = owner_lines[label_start]
    row_parts = [line.strip() for line in lines[start_line:label_end_line + 1]]
    row_text = " ".join(row_parts)
    label_pattern = r"\s*".join(re.escape(char) for char in label)
    label_match = re.search(label_pattern, row_text)
    if label_match is None:
        raise ValueError("fact label could not be reconstructed across adjacent PDF lines")
    suffix = row_text[label_match.end():]
    if not re.search(r"\d", suffix):
        for following in lines[label_end_line + 1:label_end_line + 4]:
            suffix += " " + following.strip()
            if re.search(r"\d", following):
                break
    suffix = re.sub(r"七\s*[（(]\s*\d+\s*[）)]", "", suffix).replace("，", ",")
    number_tokens = re.findall(r"(?<![\d.])-?\d[\d,]*(?:\.\d+)?(?![\d.])", suffix)
    if len(number_tokens) < 2:
        raise ValueError("fact row does not contain current and comparative numeric columns")
    try:
        expected = Decimal(str(value).replace(",", "").replace("，", "").strip())
        current_column = Decimal(number_tokens[0].replace(",", ""))
    except InvalidOperation as error:
        raise ValueError("fact row contains an invalid decimal value") from error
    if current_column != expected:
        raise ValueError("fact value does not equal the first reported period column in its table row")
    if shenhua_h1:
        _verify_shenhua_h1_column_geometry(pdf_bytes, fact)


def _verify_registration(root: Path, spec: Mapping[str, Any]):
    return verify_prospective_registration_receipt(
        root=root, receipt_path=spec.get("registration_receipt_path"),
        receipt_sha256=spec.get("registration_receipt_sha256"), plan_path=spec.get("plan_path"),
    )


def _time(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def build_prospective_baselines(*, root: Path, input_path: Path, output_path: Path) -> dict[str, Any]:
    source = require_inside(root, input_path, "prospective baseline input")
    target = require_inside(root, output_path, "prospective baseline output")
    if not target.is_relative_to((root / "runtime").resolve()):
        raise ValueError("prospective baseline output must remain under runtime")
    payload = load_json_object(source, "prospective baseline input")
    if payload.get("schema_version") != "prospective-baseline-input-v1" or payload.get("action") != "no_order":
        raise ValueError("prospective baseline input must be v1 and action=no_order")
    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 3:
        raise ValueError("prospective baseline input must contain exactly three cases")
    now = datetime.now(timezone.utc)
    cards: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, Mapping):
            raise ValueError("baseline case must be an object")
        cutoff = _time(case.get("baseline_cutoff_at"), "baseline_cutoff_at")
        facts = case.get("known_facts", [])
        if not isinstance(facts, list):
            raise ValueError("known_facts must be a list")
        for fact in facts:
            if not isinstance(fact, Mapping):
                raise ValueError("known fact must be an object")
            available = _time(fact.get("available_at"), "fact.available_at")
            if available > cutoff:
                raise ValueError("future fact cannot enter baseline")
            required = ("fact_id", "source_url", "source_document_id", "source_sha256", "fact_type")
            if any(not isinstance(fact.get(field), str) or not fact[field].strip() for field in required):
                raise ValueError("known fact provenance is incomplete")
            ledger.append({
                "case_id": case["case_id"], "symbol": case["symbol"],
                "observation_id": f"baseline:{fact['fact_id']}",
                "observed_at": now.isoformat(), "source_available_at": available.isoformat(),
                "source_document_id": fact["source_document_id"], "source_sha256": fact["source_sha256"],
                "fact_type": fact["fact_type"], "dependency_nodes": fact.get("dependency_nodes", []),
                "classification": "BASELINE_FACT",
            })
        cards.append({
            "case_id": case["case_id"], "symbol": case["symbol"], "company": case["company"],
            "profile": case["profile"], "model_applicability": case["model_applicability"],
            "business_quality": case["business_quality"], "financial_quality": case["financial_quality"],
            "capital_allocation": case["capital_allocation"], "return_drivers": case["return_drivers"],
            "mispricing_hypothesis": case["mispricing_hypothesis"], "dividend_sustainability": case["dividend_sustainability"],
            "strongest_counterevidence": case["strongest_counterevidence"], "thesis_breakers": case["thesis_breakers"],
            "known_facts": facts, "unknowns": case["unknowns"], "next_evidence_trigger": case["next_evidence_trigger"],
            "research_status": case["research_status"], "valuation_status": case["valuation_status"], "action": "no_order",
        })
    result = {"schema_version": "prospective-baseline-snapshot-v1", "built_at": now.isoformat(), "action": "no_order", "cards": cards, "observation_ledger": ledger}
    write_new_json(target, result)
    return result | {"output_path": str(target), "output_sha256": sha256_file(target), "input_sha256": sha256_file(source)}


__all__ = ["build_prospective_baselines"]


def build_verified_prospective_baselines(
    *, root: Path, input_path: Path, output_path: Path,
) -> dict[str, Any]:
    """Create a successor snapshot; only byte-verified, receipt-bound facts enter PIT."""
    source = require_inside(root, input_path, "verified baseline input")
    target = require_inside(root, output_path, "verified baseline output")
    if not target.is_relative_to((root / "runtime").resolve()):
        raise ValueError("verified baseline output must remain under runtime")
    spec = load_json_object(source, "verified baseline input")
    spec_version = spec.get("schema_version")
    if spec_version not in {
        "prospective-baseline-verification-v2",
        "prospective-baseline-verification-v3",
        "prospective-baseline-verification-v4",
        "prospective-baseline-verification-v5",
        "prospective-baseline-verification-v6",
        "prospective-baseline-verification-v7",
        "prospective-baseline-verification-v8",
        "prospective-baseline-verification-v9",
    } or spec.get("action") != "no_order":
        raise ValueError("supported verified baseline spec and action=no_order are required")

    def pinned(path: object, digest: object, label: str) -> tuple[Path, bytes]:
        if not isinstance(path, str) or not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"{label} requires a pinned path and SHA-256")
        file = require_inside(root, root / path, label)
        data = file.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest.lower():
            raise ValueError(f"{label} byte hash mismatch")
        return file, data

    receipt, registration = _verify_registration(root, spec)
    created = _time(receipt.get("receipt_created_at"), "receipt_created_at")
    baseline_file, _ = pinned(spec.get("baseline_input_path"), spec.get("baseline_input_sha256"), "baseline input")
    baseline = load_json_object(baseline_file, "baseline input")
    if baseline.get("schema_version") != "prospective-baseline-input-v1" or baseline.get("action") != "no_order":
        raise ValueError("unsupported baseline input")
    supplemental: dict[str, list[dict[str, Any]]] = {}
    supplement_digest = None
    if spec_version in {
        "prospective-baseline-verification-v3",
        "prospective-baseline-verification-v4",
        "prospective-baseline-verification-v5",
        "prospective-baseline-verification-v6",
        "prospective-baseline-verification-v7",
        "prospective-baseline-verification-v8",
        "prospective-baseline-verification-v9",
    }:
        supplement_file, _ = pinned(
            spec.get("supplemental_facts_path"), spec.get("supplemental_facts_sha256"),
            "supplemental baseline facts",
        )
        supplement = load_json_object(supplement_file, "supplemental baseline facts")
        supported_fact_schemas = {"prospective-baseline-facts-v1"}
        if spec_version in {
            "prospective-baseline-verification-v5",
            "prospective-baseline-verification-v6",
            "prospective-baseline-verification-v7",
            "prospective-baseline-verification-v8",
            "prospective-baseline-verification-v9",
        }:
            supported_fact_schemas.add("prospective-baseline-facts-v2")
        if supplement.get("schema_version") not in supported_fact_schemas or supplement.get("action") != "no_order":
            raise ValueError("unsupported supplemental facts input")
        entries = supplement.get("facts")
        if not isinstance(entries, list):
            raise ValueError("supplemental facts must be a list")
        for entry in entries:
            if not isinstance(entry, Mapping) or not isinstance(entry.get("case_id"), str) or not isinstance(entry.get("fact"), Mapping):
                raise ValueError("supplemental fact entry must bind a case_id and fact object")
            supplemental.setdefault(entry["case_id"], []).append(dict(entry["fact"]))
        supplement_digest = spec["supplemental_facts_sha256"]
    cases = baseline.get("cases")
    if (
        not isinstance(cases, list)
        or any(not isinstance(case, Mapping) or not isinstance(case.get("case_id"), str) for case in cases)
        or len({case["case_id"] for case in cases}) != len(cases)
        or {case["case_id"] for case in cases} != {case.case_id for case in registration.cases}
    ):
        raise ValueError("baseline cases differ from registration")
    if set(supplemental) - {case["case_id"] for case in cases}:
        raise ValueError("supplemental facts reference a case outside the baseline")
    verification = spec.get("verified_sources")
    if not isinstance(verification, dict):
        raise ValueError("verified_sources must be an object")
    now = datetime.now(timezone.utc)
    cards: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    for case in cases:
        registered = next(item for item in registration.cases if item.case_id == case["case_id"])
        if (
            case["symbol"] != registered.symbol or case["company"] != registered.name
            or case["profile"] != registered.profile_id
            or _time(case["baseline_cutoff_at"], "baseline cutoff") != registered.baseline_cutoff_at
        ):
            raise ValueError("baseline identity or cutoff differs from registration")
        if created > registered.observation_start_at or now < registered.observation_start_at:
            raise ValueError("baseline must follow a timely registration and observation start")
        admitted: list[dict[str, Any]] = []
        unadmitted: list[str] = []
        source_facts = [*case.get("known_facts", []), *supplemental.get(case["case_id"], [])]
        if len({fact.get("fact_id") for fact in source_facts if isinstance(fact, Mapping)}) != len(source_facts):
            raise ValueError("baseline case contains duplicate fact IDs")
        for fact in source_facts:
            binding = verification.get(fact["fact_id"])
            if binding is None:
                unadmitted.append(fact["fact_id"])
                continue
            _, evidence_bytes = pinned(binding.get("scan_evidence_path"), binding.get("scan_evidence_sha256"), "scan evidence")
            scan = json.loads(evidence_bytes)
            if scan.get("symbol") != case["symbol"] or scan.get("coverage_status") != "COMPLETE":
                raise ValueError("scan evidence does not cover the registered issuer")
            _, index_bytes = pinned(binding.get("index_path"), binding.get("index_sha256"), "announcement index")
            index = json.loads(index_bytes)
            refs = scan.get("evidence_refs") or []
            if not any(ref.get("path") == binding["index_path"] and ref.get("sha256") == binding["index_sha256"] for ref in refs):
                raise ValueError("scan does not bind announcement index")
            document_id = fact["source_document_id"].split(":")[-1]
            matches = [item for item in scan.get("announcements") or [] if item.get("announcement_id") == document_id]
            index_matches = [item for item in index.get("announcements") or [] if item.get("announcementId") == document_id]
            if len(matches) != 1 or len(index_matches) != 1 or index_matches[0].get("secCode") != case["symbol"]:
                raise ValueError("announcement identity is not independently indexed")
            announcement = matches[0]
            if fact.get("source_document_id") != f"cninfo:{announcement['announcement_id']}":
                raise ValueError("source document namespace differs from the registered CNINFO index")
            indexed_at = datetime.fromtimestamp(index_matches[0]["announcementTime"] / 1000, timezone.utc)
            source_date = indexed_at.astimezone(ZoneInfo("Asia/Shanghai")).date()
            safe_available = datetime.combine(
                source_date + timedelta(days=1), time.min, tzinfo=ZoneInfo("Asia/Shanghai")
            )
            published = _time(announcement.get("published_at"), "source published_at")
            fact_published_value = fact.get("published_at", fact.get("available_at"))
            declared_published = _time(fact_published_value, "fact published_at")
            available = _time(fact.get("available_at"), "fact available_at")
            retrieved = _time(scan.get("retrieved_at"), "scan retrieved_at")
            safe_input_time = safe_available if "published_at" in fact else indexed_at
            if (
                declared_published != indexed_at or published != indexed_at
                or available != safe_input_time or safe_available > registered.baseline_cutoff_at
                or retrieved > now
            ):
                raise ValueError(f"source availability is not valid at baseline cutoff: {fact['fact_id']}")
            source_refs = announcement.get("evidence_refs") or []
            if not any(ref.get("path") == binding.get("source_path") and ref.get("sha256") == fact["source_sha256"] and ref.get("source_url") == fact["source_url"] for ref in source_refs):
                raise ValueError("scan does not bind source artifact")
            _, source_bytes = pinned(binding.get("source_path"), fact["source_sha256"], "source artifact")
            admitted_fact = dict(fact) | {
                "source_path": binding["source_path"], "published_at": published.isoformat(),
                "retrieved_at": retrieved.isoformat(), "report_period": binding.get("report_period"),
                "scan_evidence_sha256": binding["scan_evidence_sha256"],
                "available_at": safe_available.isoformat(),
                "availability_precision": "DATE_ONLY_CONSERVATIVE_NEXT_DAY",
            }
            if not isinstance(admitted_fact["report_period"], str) or not admitted_fact["report_period"]:
                raise ValueError("report period is required")
            if fact.get("fact_type") in {"financial_report", "annual_report"} and "value" not in fact:
                unadmitted.append(fact["fact_id"])
                continue
            _verify_fact_text(source_bytes, fact, binding)
            admitted.append(admitted_fact)
            ledger.append({
                "case_id": case["case_id"], "symbol": case["symbol"],
                "observation_id": f"baseline:{fact['fact_id']}", "observed_at": now.isoformat(),
                "source_available_at": safe_available.isoformat(), "source_document_id": fact["source_document_id"],
                "source_sha256": fact["source_sha256"], "fact_type": fact["fact_type"],
                "dependency_nodes": fact.get("dependency_nodes", []), "classification": "BASELINE_FACT",
            })
        card = dict(case)
        card["known_facts"] = admitted
        card["unadmitted_fact_ids"] = unadmitted
        card["research_status"] = "BASELINE_PARTIAL" if admitted else "BASELINE_EXPLICIT_NOT_READY"
        card["valuation_status"] = "VALUATION_NOT_READY"
        card["action"] = "no_order"
        cards.append(card)
    unknown_bindings = set(verification) - {fact["fact_id"] for case in cases for fact in case.get("known_facts", [])}
    if supplemental:
        unknown_bindings -= {fact["fact_id"] for facts in supplemental.values() for fact in facts}
    if unknown_bindings:
        raise ValueError("verification contains facts outside the baseline")
    result = {
        "schema_version": "prospective-baseline-snapshot-v2", "built_at": now.isoformat(),
        "registration_receipt_sha256": spec["registration_receipt_sha256"],
        "baseline_input_sha256": spec["baseline_input_sha256"], "action": "no_order",
        "registration_time_assurance": "PROCESS_CLOCK_ONLY_UNATTESTED",
        "strict_pit_admissible": False,
        "cards": cards, "observation_ledger": ledger,
    }
    if supplement_digest is not None:
        result["supplemental_facts_sha256"] = supplement_digest
    write_new_json(target, result)
    return result | {"output_path": str(target), "output_sha256": sha256_file(target)}


__all__.append("build_verified_prospective_baselines")
