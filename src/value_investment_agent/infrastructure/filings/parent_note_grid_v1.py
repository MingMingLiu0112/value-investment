"""Read four ruled cells (item, note, current, comparative) in a signed parent table."""
from datetime import date
import re

import pypdfium2 as pdfium

from .pdfium_runtime import serialized_pdfium


def compact(text):
    return re.sub(r"\s+", "", text)


def _matches(text, phrase):
    search = text.search(phrase)
    try:
        while match := search.get_next():
            yield text.get_charbox(match[0])[1]
    finally:
        search.close()


def _cells(page, text, lower, upper):
    bounds = [obj.get_bounds() for obj in page.get_objects() if obj.type == pdfium.raw.FPDF_PAGEOBJ_PATH]
    rules = [(left, (bottom + top) / 2, right) for left, bottom, right, top in bounds
             if right - left > page.get_width() * .65 and top - bottom < 2
             and lower < (bottom + top) / 2 < upper]
    rules.sort(key=lambda row: -row[1])
    for (left, top, right), (left2, bottom, right2) in zip(rules, rules[1:]):
        if abs(left - left2) > 1 or abs(right - right2) > 1 or top - bottom < 3:
            continue
        middle = (top + bottom) / 2
        borders = sorted((l + r) / 2 for l, b, r, t in bounds
                         if r - l < 2 and b < middle < t and left - 1 <= l <= right)
        if len(borders) != 5 or abs(borders[0] - left) > 2 or abs(borders[-1] - right) > 2:
            continue  # Merged captions have no four-column data cells.
        cells = [compact(text.get_text_bounded(left=a+.6, right=b-.6,
                                               bottom=bottom+.6, top=top-.6))
                 for a, b in zip(borders, borders[1:])]
        yield borders, cells


@serialized_pdfium
def read_parent_grid(path, pages, title, issuer, period):
    day = date.fromisoformat(period)
    annual = period.endswith("-12-31")
    if not annual and not period.endswith("-06-30"):
        raise ValueError("NOTE_GRID_FY_OR_H1_REQUIRED")
    header = issuer + str(day.year) + ("年年度报告" if annual else "年半年度报告")
    starts = [i for i, page in enumerate(pages) for line in page.splitlines() if compact(line) == title]
    if len(starts) != 1:
        raise ValueError("NOTE_GRID_PARENT_TABLE_NOT_UNIQUE:" + title)
    index = starts[0]
    first = compact(pages[index]).split(title, 1)[1].split("项目", 1)[0]
    if "单位：元币种：人民币" not in first:
        raise ValueError("NOTE_GRID_CURRENCY_OR_UNIT_CHANGED")
    if title == "母公司资产负债表":
        current = f"{day.year}年{day.month}月{day.day}日"
        prior = f"{day.year-1}年12月31日"
        if "编制单位：" + issuer not in first or current not in first:
            raise ValueError("NOTE_GRID_PARENT_OR_DATE_CHANGED")
    else:
        suffix = "年度" if annual else "年半年度"
        current, prior = (str(year) + suffix for year in (day.year, day.year-1))
        if not re.search(fr"{day.year}年1[—－–-]{day.month}月", first):
            raise ValueError("NOTE_GRID_FLOW_PERIOD_CHANGED")
    rows, columns = [], None
    with pdfium.PdfDocument(path) as document:
        for number in range(index, min(index + 4, len(pages))):
            if compact(pages[number].splitlines()[0]) != header:
                raise ValueError("NOTE_GRID_REPORT_HEADER_CHANGED")
            page = document[number]
            text = page.get_textpage()
            try:
                upper = page.get_height()
                if number == index:
                    title_positions = list(_matches(text, title))
                    if len(title_positions) != 1:
                        raise ValueError("NOTE_GRID_TITLE_POSITION_AMBIGUOUS")
                    upper = title_positions[0]
                signatures = [y for y in _matches(text, "公司负责人") if y < upper]
                lower = max(signatures, default=0)
                for borders, cells in _cells(page, text, lower, upper):
                    if columns is None:
                        if cells != ["项目", "附注十九", current, prior]:
                            raise ValueError("NOTE_GRID_PERIOD_OR_NOTE_COLUMNS_CHANGED")
                        columns = borders
                    elif any(abs(a-b) > 1 for a, b in zip(borders, columns)) or cells[0] == "项目":
                        raise ValueError("NOTE_GRID_COLUMN_GEOMETRY_CHANGED")
                    else:
                        rows.append((number+1, cells))
                if signatures:
                    if columns is None or not rows:
                        raise ValueError("NOTE_GRID_EMPTY")
                    return rows
            finally:
                text.close()
                page.close()
    raise ValueError("NOTE_GRID_SIGNED_TABLE_END_MISSING")
