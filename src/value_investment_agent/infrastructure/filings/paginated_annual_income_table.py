"""Adapt an explicitly identified annual report with pre-title table headers."""
import re

from . import operating_statement_basis_v1 as native


def parse_paginated_annual_income(*, pages, source, issuer_name):
    period = source["period"]
    if not re.fullmatch(r"[0-9]{4}-12-31", period):
        raise ValueError("EXACT_PAGINATED_ANNUAL_PERIOD_REQUIRED")
    normalized = list(pages)
    titles = {"合并利润表", "母公司利润表"}
    moved = set()
    owner = "".join(issuer_name.split())
    for index, page in enumerate(pages):
        lines = page.splitlines()
        for position, line in enumerate(lines):
            title = line.strip()
            if title not in titles or position < 2:
                continue
            interval, compiler = ("".join(item.split()).replace("：", ":").replace("—", "-")
                                  for item in lines[position-2:position])
            if interval != f"{period[:4]}年1-12月" or compiler != "编制单位:" + owner:
                continue
            if title in moved:
                raise ValueError("PAGINATED_INCOME_DUPLICATE_TITLE")
            moved.add(title)
            lines[position-2:position+1] = [line, lines[position-2], lines[position-1]]
        normalized[index] = "\n".join(lines)
    if moved != titles:
        raise ValueError("PAGINATED_INCOME_PRE_TITLE_HEADERS_NOT_PROVEN")
    result = native._parse(normalized, source)
    if (result["gaps"] or result.get("issuer_name") != owner
            or result["source_binding"] != source or result["financial_quality_granted"] is not False):
        raise ValueError("PAGINATED_ANNUAL_BASELINE_NOT_PROVEN")
    return result
