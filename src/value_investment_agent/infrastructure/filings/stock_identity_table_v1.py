"""Bounded printed stock-identity labels/tables; no issuer/year/PIT admission."""
import re

_LABEL = re.compile(r"(?:公司|证券|股票)代码\s*[:：]?\s*([0-9]{6})(?!\d)")
_HEADER = ("股票种类", "股票上市交易所", "股票简称", "股票代码")
_EXCHANGES = {"上海证券交易所": ("6",), "深圳证券交易所": ("0", "3"),
              "北京证券交易所": ("4", "8", "9")}
_MAX_ROWS = 3
_NEXT_SECTION = re.compile(r"\s+[一二三四五六七八九十]{1,3}、\s*其他相关资料$")
_ROW_START = re.compile(r"^[ABH]\s*股(?:\s|$)")


def labelled_security_codes(pages, *, symbol) -> set[str]:
    """Return all explicit codes, including label/table conflicts for caller rejection.

    An exact single-line header and adjacent complete single-line table rows are
    supported. Ambiguous A-share rows, exchange/prefix conflicts and conflicting
    tables raise ValueError. No cross-page stitching or generic number search.
    A returned code set proves neither issuer name nor report period.
    """
    if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
        raise ValueError("INVALID_EXPECTED_SECURITY_CODE")
    if not isinstance(pages, (list, tuple)) or any(not isinstance(p, str) for p in pages):
        raise ValueError("ORDERED_PAGE_TEXTS_REQUIRED")
    codes = set(_LABEL.findall("\n".join(pages)))
    table_codes = []
    for page in pages:
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            tokens = line.split()
            if tokens not in [list(_HEADER), [*_HEADER, "变更前股票简称"]]:
                continue
            row_count = 0
            for row in lines[index+1:index+1+_MAX_ROWS+1]:
                if not _ROW_START.match(row):
                    break
                row_count += 1
                if row_count > _MAX_ROWS:
                    raise ValueError("STOCK_IDENTITY_TABLE_ROW_LIMIT")
                # PDF text may glue this exact following section heading to the row.
                # Remove only that anchored suffix; all preceding cells remain checked.
                next_section = _NEXT_SECTION.search(row)
                if next_section:
                    row = row[:next_section.start()]
                # A 股 is a permitted typography variant, not two table columns.
                cells = re.sub(r"^([ABH])\s+股", r"\1股", row).split()
                if cells[0] != "A股":
                    continue
                # Only the trailing former-name column may be absent in extraction.
                # The four identity columns remain mandatory; no cell is filled.
                allowed_lengths = {4, 5} if len(tokens) == 5 else {4}
                if len(cells) not in allowed_lengths:
                    raise ValueError("AMBIGUOUS_A_SHARE_TABLE_COLUMNS")
                exchange, name, code = cells[1:4]
                if (exchange not in _EXCHANGES or not name
                        or not re.fullmatch(r"[0-9]{6}", code)
                        or not code.startswith(_EXCHANGES[exchange])):
                    raise ValueError("A_SHARE_EXCHANGE_CODE_MISMATCH")
                table_codes.append(code)
                if len(table_codes) > 1:
                    raise ValueError("MULTIPLE_A_SHARE_ROWS_OR_CONFLICTING_TABLES")
                if next_section:
                    break
    return codes | set(table_codes)
