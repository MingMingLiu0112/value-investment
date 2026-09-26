"""Bounded, redacted audit of long decimal tokens in tracked Excel workbooks."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import load_workbook

LONG_DIGITS = re.compile(r"(?<!\d)\d{16,19}(?!\d)")
PRIVATE = re.compile(r"姓名|身份证|银行卡|账户|账号|手机号|手机|电话|客户号|券商|资金账号|密码|现金余额|持仓成本|私人|个人|IPS", re.I)
PUBLIC = re.compile(r"营业收入|营收|总股本|市值|净利润|现金流|总资产|股本|财务|估值|报告期|公告编号|成交|价格|分红|利润|收入|资产|负债|权益|资本|market|revenue|profit|cashflow|shares|valuation", re.I)
HASH = re.compile(r"sha256|hash|fingerprint|digest|receipt|校验|指纹", re.I)


def classify(token: str, *, context: str, cell_type: str, number_format: str, formula: bool) -> str:
    if PRIVATE.search(context):
        return "REQUIRES_PRIVATE_REVIEW"
    if formula:
        return "FORMULA_OR_DERIVED_VALUE"
    if HASH.search(context):
        return "HASH_OR_RECEIPT_FRAGMENT"
    if cell_type == "n" and PUBLIC.search(context):
        return "POTENTIAL_PUBLIC_FINANCIAL_OR_MARKET_VALUE"
    if cell_type == "n" and ("yy" in number_format.lower() or "dd" in number_format.lower()):
        return "PUBLIC_DATE_OR_TIMESTAMP"
    return "UNKNOWN_LONG_NUMERIC"


def audit(root: Path) -> dict:
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
                headers: dict[int, str] = {}
                for row in sheet.iter_rows():
                    labels = [str(cell.value) for cell in row if isinstance(cell.value, str) and len(cell.value) < 100 and not LONG_DIGITS.search(cell.value)]
                    row_context = " ".join(labels[:12])
                    for cell in row:
                        value = cell.value
                        if value is None:
                            continue
                        if cell.row <= 4 and isinstance(value, str) and len(value) < 100:
                            headers[cell.column] = value
                        value_text = str(value)
                        matches = LONG_DIGITS.findall(value_text)
                        if not matches:
                            continue
                        context = " ".join((sheet.title, headers.get(cell.column, ""), row_context))
                        for token in matches:
                            category = classify(token, context=context, cell_type=cell.data_type, number_format=cell.number_format, formula=cell.data_type == "f")
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
    return {"status": "REQUIRES_PRIVATE_REVIEW" if counts["REQUIRES_PRIVATE_REVIEW"] else "INCOMPLETE_CONTEXT_REVIEW", "coverage": "openpyxl-visible cells only; raw OOXML parts and cached values require separate reconciliation", "workbook_count": len(list(filter(None, paths))), "candidate_count": sum(counts.values()), "unique_fingerprint_count": len(set().union(*unique.values())) if unique else 0, "categories": {key: {"occurrences": counts[key], "unique_fingerprints": len(unique[key]), "redacted_examples": examples[key]} for key in sorted(counts)}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(audit(args.root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
