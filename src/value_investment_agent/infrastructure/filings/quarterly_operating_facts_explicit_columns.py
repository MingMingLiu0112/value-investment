"""Adapt explicitly dated nine-month consolidated table headings to the v1 reader."""
import re

from .native_capital_observation_v1 import _compact
from .quarterly_operating_facts_v1 import parse_quarterly_operating_facts

VERSION = "quarterly-operating-facts-explicit-columns-v1"


def parse_explicit_columns_quarterly_facts(pages, *, symbol, currency_basis):
    """Normalize table headers only, leaving source rows and physical pages intact."""
    if not isinstance(pages, list) or not pages or any(not isinstance(page, str) for page in pages):
        raise ValueError("BOUNDED_QUARTERLY_ORIGINAL_REQUIRED")
    title = re.search(r"(20[0-9]{2})年(?:第三|三)季度报告", _compact(pages[0]))
    if title is None:
        raise ValueError("FULL_QUARTERLY_ISSUER_REQUIRED")
    year = int(title[1])
    names = {
        "合并利润表": "2、合并年初到报告期末利润表",
        "合并现金流量表": "3、合并年初到报告期末现金流量表",
    }
    heading_locations = {}
    parent_locations = []
    lines_by_page = [page.splitlines(keepends=True) for page in pages]
    for index, lines in enumerate(lines_by_page):
        for offset, line in enumerate(lines):
            label = _compact(line)
            if label in names:
                if label in heading_locations:
                    raise ValueError("EXPLICIT_QUARTERLY_TABLE_AMBIGUOUS")
                heading_locations[label] = (index, offset)
            if label == "母公司资产负债表":
                parent_locations.append((index, offset))
    if (
        set(heading_locations) != set(names)
        or len(parent_locations) != 1
        or not heading_locations["合并利润表"] < heading_locations["合并现金流量表"] < parent_locations[0]
    ):
        raise ValueError("EXPLICIT_QUARTERLY_SCOPE_NOT_VERIFIED")
    for label, (index, offset) in heading_locations.items():
        lines = lines_by_page[index]
        header = [_compact(line) for line in lines[offset + 1:offset + 5]]
        if (
            len(header) != 4
            or header[0] not in {f"{year}年1—9月", f"{year}年1-9月"}
            or not header[1].startswith("编制单位:")
            or header[2] != "单位:元币种:人民币审计类型:未经审计"
            or header[3] != f"项目{year}年前三季度(1-9月){year - 1}年前三季度(1-9月)"
        ):
            raise ValueError("EXPLICIT_QUARTERLY_YTD_COLUMNS_NOT_VERIFIED")
        lines[offset:offset + 5] = [names[label] + "\n", "单位:元项目本期发生额上期发生额\n", "", "", ""]
    page_index, offset = parent_locations[0]
    lines_by_page[page_index][offset] = "(二)\n" + lines_by_page[page_index][offset]
    result = parse_quarterly_operating_facts(
        ["".join(lines) for lines in lines_by_page], symbol=symbol, currency_basis=currency_basis,
    )
    return {**result, "schema_version": VERSION}
