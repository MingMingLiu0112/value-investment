"""Bounded, redacted audit of long decimal tokens in tracked Excel workbooks."""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import subprocess
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

from openpyxl import load_workbook

LONG_DIGITS = re.compile(r"(?<!\d)\d{16,19}(?!\d)")
HEX_DIGEST = re.compile(r"\b[0-9a-f]{32,128}\b", re.I)
OOXML_CELL = re.compile(r"<c\b[^>]*>.*?</c>", re.S)
PRIVATE = re.compile(r"姓名|身份证|银行卡|账户|账号|手机号|手机|电话|客户号|券商|资金账号|密码|现金余额|持仓成本|私人|个人|IPS", re.I)
PUBLIC = re.compile(r"营业收入|营收|总股本|市值|净利润|现金流|总资产|股本|财务|估值|报告期|公告编号|成交|价格|分红|利润|收入|资产|负债|权益|资本|数据源|来源|证据|审计|market|revenue|profit|cashflow|shares|valuation", re.I)
HASH = re.compile(r"sha-?256|hash|fingerprint|digest|receipt|校验|指纹", re.I)


def classify(
    *, context: str, cell_type: str, number_format: str, formula: bool,
    value: str | None = None,
) -> str:
    if value is not None and HEX_DIGEST.fullmatch(value.strip()) and HASH.search(context):
        return "HASH_OR_RECEIPT_FRAGMENT"
    if PRIVATE.search(context):
        return "REQUIRES_PRIVATE_REVIEW"
    if (
        value is not None
        and re.fullmatch(r"[0-9a-f]{64}", value.strip(), re.I)
        and re.search(r"[a-f]", value.strip(), re.I)
    ):
        return "HASH_OR_RECEIPT_FRAGMENT"
    if formula:
        return "FORMULA_OR_DERIVED_VALUE"
    if HASH.search(context):
        return "HASH_OR_RECEIPT_FRAGMENT"
    if cell_type == "n" and PUBLIC.search(context):
        return "POTENTIAL_PUBLIC_FINANCIAL_OR_MARKET_VALUE"
    if cell_type == "n" and ("yy" in number_format.lower() or "dd" in number_format.lower()):
        return "PUBLIC_DATE_OR_TIMESTAMP"
    return "UNKNOWN_LONG_NUMERIC"


def _column_number(column: str) -> int:
    value = 0
    for character in column:
        value = value * 26 + ord(character.upper()) - ord("A") + 1
    return value


def _nearby_row_context(labels: list[tuple[int, str]], column: int) -> str:
    return " ".join(
        label for label_column, label in labels
        if abs(label_column - column) <= 2
    )


def _nearby_grid_context(
    labels_by_row: dict[int, list[tuple[int, str]]], row: int, column: int,
) -> str:
    return " ".join(
        label
        for nearby_row in range(max(1, row - 2), row + 3)
        for label_column, label in labels_by_row.get(nearby_row, [])
        if abs(label_column - column) <= 2
    )


def audit(root: Path, *, include_raw_context: bool = False) -> dict:
    paths = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "*.xlsx"], cwd=root
    ).decode("utf-8").split("\0")
    counts: Counter[str] = Counter()
    unique: dict[str, set[str]] = defaultdict(set)
    examples: dict[str, list[dict[str, str]]] = defaultdict(list)
    for relative in filter(None, paths):
        workbook = load_workbook(root / relative, read_only=True, data_only=False)
        try:
            for sheet in workbook:
                headers: dict[int, list[str]] = defaultdict(list)
                for row in sheet.iter_rows():
                    labels = [
                        (cell.column, str(cell.value)) for cell in row
                        if isinstance(cell.value, str) and len(cell.value) < 100
                        and not LONG_DIGITS.search(cell.value)
                    ]
                    for cell in row:
                        value = cell.value
                        if value is None:
                            continue
                        if cell.row <= 4 and isinstance(value, str) and len(value) < 100:
                            label = value.strip()
                            if (
                                label
                                and not HEX_DIGEST.fullmatch(label)
                                and label not in headers[cell.column]
                            ):
                                headers[cell.column].append(label)
                        value_text = str(value)
                        matches = LONG_DIGITS.findall(value_text)
                        if not matches:
                            continue
                        row_context = _nearby_row_context(labels, cell.column)
                        context = " ".join((sheet.title, *headers.get(cell.column, []), row_context))
                        for token in matches:
                            category = classify(
                                context=context, cell_type=cell.data_type,
                                number_format=cell.number_format,
                                formula=cell.data_type == "f", value=value_text,
                            )
                            fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()[:16]
                            counts[category] += 1
                            unique[category].add(fingerprint)
                            if len(examples[category]) < 12:
                                example = {"workbook_sha256_12": hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12], "sheet": sheet.title, "cell": cell.coordinate, "fingerprint": fingerprint}
                                if category == "REQUIRES_PRIVATE_REVIEW":
                                    example["matched_keyword"] = PRIVATE.search(context).group(0)
                                examples[category].append(example)
        finally:
            workbook.close()
    visible = set().union(*unique.values()) if unique else set()
    raw = _raw_ooxml_audit(root, list(filter(None, paths)), visible)
    if include_raw_context:
        raw["context_classification"] = classify_raw_only_candidates(
            root, list(filter(None, paths)), visible_fingerprints=visible,
        )
    return {"status": "REQUIRES_PRIVATE_REVIEW" if counts["REQUIRES_PRIVATE_REVIEW"] else "INDEPENDENT_REVIEW_REQUIRED", "coverage": "openpyxl-visible cells plus raw OOXML parts; all token output is fingerprint-only", "workbook_count": len(list(filter(None, paths))), "candidate_count": sum(counts.values()), "unique_fingerprint_count": len(set().union(*unique.values())) if unique else 0, "categories": {key: {"occurrences": counts[key], "unique_fingerprints": len(unique[key]), "redacted_examples": examples[key]} for key in sorted(counts)}, "raw_ooxml": raw}


def _part_category(name: str) -> str:
    if name == "xl/sharedStrings.xml":
        return "SHARED_STRING_SERIALIZATION"
    if name.startswith("xl/charts/"):
        return "DRAWING_OR_CHART_CACHE"
    if name.startswith("xl/worksheets/"):
        return "WORKSHEET_OR_CACHED_FORMULA"
    if name.startswith("docProps/"):
        return "METADATA"
    return "OTHER_RAW_XML"


def _raw_ooxml_audit(root: Path, paths: list[str], visible: set[str]) -> dict:
    counts: Counter[str] = Counter()
    unique: dict[str, set[str]] = defaultdict(set)
    raw_only: set[str] = set()
    private_context: set[str] = set()
    examples: list[dict[str, str]] = []
    for relative in paths:
        with zipfile.ZipFile(root / relative) as archive:
            for name in archive.namelist():
                if not name.endswith(".xml"):
                    continue
                try:
                    text = archive.read(name).decode("utf-8", errors="ignore")
                except KeyError:
                    continue
                tokens: list[tuple[str, str]] = []
                if name.startswith("xl/worksheets/"):
                    for cell in OOXML_CELL.findall(text):
                        category = "CACHED_FORMULA_VALUE" if "<f" in cell else "WORKSHEET_RAW_VALUE"
                        tokens.extend((token, category) for token in LONG_DIGITS.findall(cell))
                else:
                    tokens = [(token, _part_category(name)) for token in LONG_DIGITS.findall(text)]
                for token, category in tokens:
                    fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()[:16]
                    counts[category] += 1
                    unique[category].add(fingerprint)
                    if fingerprint not in visible:
                        raw_only.add(fingerprint)
                    position = text.find(token)
                    context = text[max(0, position - 256): position + len(token) + 256] if position >= 0 else ""
                    if PRIVATE.search(context) and not HEX_DIGEST.search(context):
                        private_context.add(fingerprint)
                    if len(examples) < 20:
                        examples.append({"workbook_sha256_12": hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12], "part": name, "fingerprint": fingerprint, "context_category": category})
    return {"candidate_count": sum(counts.values()), "unique_fingerprint_count": len(set().union(*unique.values())) if unique else 0, "raw_only_unique_fingerprints": len(raw_only), "raw_only_private_context_fingerprints": len(private_context), "raw_private_context_fingerprint_samples": sorted(private_context)[:12], "part_categories": {key: {"occurrences": counts[key], "unique_fingerprints": len(unique[key])} for key in sorted(counts)}, "redacted_examples": examples, "reconciliation_basis": "raw-only values are bounded by OOXML part category; no raw token is emitted"}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _workbook_sheets(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        item.attrib["Id"]: item.attrib["Target"]
        for item in relationships
        if "Id" in item.attrib and "Target" in item.attrib
    }
    result = {}
    for sheet in workbook.iter():
        if _local_name(sheet.tag) != "sheet":
            continue
        name = sheet.attrib.get("name", "")
        rel_id = next(
            (value for key, value in sheet.attrib.items() if _local_name(key) == "id"),
            None,
        )
        target = targets.get(rel_id or "")
        if not name or not target:
            continue
        part = posixpath.normpath(
            target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target)
        )
        result[part] = name
    return result


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter() if _local_name(node.tag) == "t")
        for item in root
        if _local_name(item.tag) == "si"
    ]


def _cell_parts(cell: ET.Element, shared: list[str]) -> tuple[str, str, bool]:
    value_node = next((node for node in cell if _local_name(node.tag) == "v"), None)
    formula = any(_local_name(node.tag) == "f" for node in cell)
    cell_type = cell.attrib.get("t", "n")
    raw = "" if value_node is None else value_node.text or ""
    if cell_type == "s" and raw.isdigit() and int(raw) < len(shared):
        value = shared[int(raw)]
    elif cell_type == "inlineStr":
        value = "".join(
            node.text or "" for node in cell.iter() if _local_name(node.tag) == "t"
        )
    else:
        value = raw
    return value, cell_type, formula


def _safe_context_classification(
    *, context: str, cell_type: str, formula: bool,
) -> tuple[str, list[str], str]:
    signals = []
    if PRIVATE.search(context):
        signals.append("private_context")
    if HASH.search(context):
        signals.append("hash_context")
    if PUBLIC.search(context):
        signals.append("public_financial_context")
    if formula:
        signals.append("formula_cell")
    if cell_type == "n":
        signals.append("numeric_cell")
    category = classify(context=context, cell_type=cell_type, number_format="", formula=formula)
    reason = {
        "REQUIRES_PRIVATE_REVIEW": "PRIVATE_CONTEXT",
        "HASH_OR_RECEIPT_FRAGMENT": "HASH_CONTEXT",
        "FORMULA_OR_DERIVED_VALUE": "FORMULA_DERIVED",
        "POTENTIAL_PUBLIC_FINANCIAL_OR_MARKET_VALUE": "PUBLIC_FINANCIAL_CONTEXT_NUMERIC",
        "PUBLIC_DATE_OR_TIMESTAMP": "DATE_NUMBER_FORMAT",
        "UNKNOWN_LONG_NUMERIC": "INSUFFICIENT_CONTEXT",
    }[category]
    return category, signals, reason


def classify_raw_only_candidates(
    root: Path, paths: list[str] | None = None,
    visible_fingerprints: set[str] | None = None,
) -> dict:
    """Classify OOXML fingerprints absent from the openpyxl-visible set."""
    if paths is None:
        paths = subprocess.check_output(
            ["git", "ls-files", "-z", "--", "*.xlsx"], cwd=root
        ).decode("utf-8").split("\0")
    paths = list(filter(None, paths))
    visible_fingerprints = visible_fingerprints or set()
    occurrences: dict[str, list[dict[str, str]]] = defaultdict(list)

    for relative in paths:
        workbook_fingerprint = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12]
        with zipfile.ZipFile(root / relative) as archive:
            sheets = _workbook_sheets(archive)
            shared = _shared_strings(archive)
            sheet_text: dict[str, dict[str, tuple[str, str, bool]]] = {}
            for part, sheet_name in sheets.items():
                if part not in archive.namelist():
                    continue
                xml = ET.fromstring(archive.read(part))
                cells: dict[str, tuple[str, str, bool]] = {}
                for cell in xml.iter():
                    if _local_name(cell.tag) != "c":
                        continue
                    coordinate = cell.attrib.get("r")
                    if coordinate:
                        cells[coordinate] = _cell_parts(cell, shared)
                sheet_text[sheet_name] = cells

            for part, sheet_name in sheets.items():
                cells = sheet_text.get(sheet_name, {})
                headers_by_column: dict[str, list[str]] = defaultdict(list)
                labels_by_row: dict[int, list[tuple[int, str]]] = defaultdict(list)
                for coordinate, (other_value, _type, _formula) in cells.items():
                    other_match = re.fullmatch(r"([A-Z]+)(\d+)", coordinate)
                    if (not other_match or LONG_DIGITS.search(other_value)
                        or len(other_value) >= 100):
                        continue
                    other_column, other_row = other_match.group(1), int(other_match.group(2))
                    column_number = _column_number(other_column)
                    if other_row <= 5:
                        headers_by_column[other_column].append(other_value)
                    labels_by_row[other_row].append((column_number, other_value))
                for coordinate, (value, cell_type, formula) in cells.items():
                    tokens = LONG_DIGITS.findall(value)
                    if not tokens:
                        continue
                    match = re.fullmatch(r"([A-Z]+)(\d+)", coordinate)
                    if not match:
                        continue
                    column, row = match.group(1), int(match.group(2))
                    header_labels = headers_by_column[column]
                    row_labels = _nearby_grid_context(
                        labels_by_row, row, _column_number(column),
                    )
                    context = " ".join([sheet_name, *header_labels, *row_labels])
                    category, signals, reason = _safe_context_classification(
                        context=context, cell_type=cell_type, formula=formula,
                    )
                    for token in tokens:
                        fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()[:16]
                        if fingerprint in visible_fingerprints:
                            continue
                        occurrences[fingerprint].append({
                            "workbook_fingerprint": workbook_fingerprint,
                            "part_category": "CACHED_FORMULA_VALUE" if formula else "WORKSHEET_RAW_VALUE",
                            "sheet": sheet_name,
                            "cell": coordinate,
                            "classification": category,
                            "reason": reason,
                            "signals": ",".join(signals),
                        })

            for part in archive.namelist():
                if not part.endswith(".xml") or part.startswith("xl/worksheets/"):
                    continue
                text = archive.read(part).decode("utf-8", errors="ignore")
                for match in LONG_DIGITS.finditer(text):
                    token = match.group(0)
                    fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()[:16]
                    if fingerprint in visible_fingerprints:
                        continue
                    position = match.start()
                    context = text[max(0, position - 256):position + len(token) + 256]
                    category, signals, reason = _safe_context_classification(
                        context=context, cell_type="s", formula=False,
                    )
                    occurrences[fingerprint].append({
                        "workbook_fingerprint": workbook_fingerprint,
                        "part_category": _part_category(part),
                        "part": part,
                        "classification": category,
                        "reason": reason,
                        "signals": ",".join(signals),
                    })

    candidates = []
    category_counts: Counter[str] = Counter()
    for fingerprint, evidence in sorted(occurrences.items()):
        classes = {item["classification"] for item in evidence}
        if "REQUIRES_PRIVATE_REVIEW" in classes:
            category = "REQUIRES_PRIVATE_REVIEW"
        elif "UNKNOWN_LONG_NUMERIC" in classes or len(classes) != 1:
            category = "UNKNOWN_LONG_NUMERIC"
        else:
            category = next(iter(classes))
        category_counts[category] += 1
        candidates.append({
            "fingerprint": fingerprint,
            "classification": category,
            "occurrences": len(evidence),
            "evidence": evidence,
        })
    return {
        "status": "REQUIRES_PRIVATE_REVIEW" if category_counts["REQUIRES_PRIVATE_REVIEW"] else "INDEPENDENT_REVIEW_REQUIRED",
        "coverage": "tracked xlsx OOXML fingerprints absent from openpyxl-visible cells; each occurrence is context-classified without source tokens or context labels",
        "workbook_count": len(paths),
        "raw_only_unique_fingerprints": len(candidates),
        "context_occurrence_count": sum(item["occurrences"] for item in candidates),
        "category_fingerprint_counts": dict(sorted(category_counts.items())),
        "candidates": candidates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--context-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.root, include_raw_context=args.context_only)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
        print(json.dumps({key: report[key] for key in (
            "status", "workbook_count", "candidate_count", "unique_fingerprint_count",
        ) if key in report}, ensure_ascii=False))
    else:
        print(output)


if __name__ == "__main__":
    main()
