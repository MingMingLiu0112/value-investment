"""TEST_ONLY text examples plus explicit real-public-PDF replay (not PIT)."""
import hashlib
import os
from pathlib import Path

import pytest

from value_investment_agent.infrastructure.filings.stock_identity_table_v1 import labelled_security_codes
from value_investment_agent.infrastructure.filings.pdf_text import extract_pages

HEADER = "股票种类 股票上市交易所 股票简称 股票代码 变更前股票简称"
ROW = "A股 上海证券交易所 海澜之家 600398 凯诺科技"


def codes(text, symbol="600398"):
    return labelled_security_codes(["TEST_ONLY\n"+text], symbol=symbol)


@pytest.mark.parametrize("label", ["公司代码：600398", "证券代码 600398", "股票代码: 600398"])
def test_explicit_legacy_labels_preserved(label):
    assert codes(label) == {"600398"}


@pytest.mark.parametrize("header,row", [
    (HEADER, ROW),
    ("股票种类 股票上市交易所 股票简称 股票代码", "A股 上海证券交易所 海澜之家 600398"),
    (HEADER, ROW.replace("A股", "A 股")),
    (HEADER, ROW.replace("上海证券交易所 海澜之家 600398", "深圳证券交易所 测试公司 000001")),
    (HEADER, ROW.replace("上海证券交易所 海澜之家 600398", "深圳证券交易所 测试公司 300001")),
    (HEADER, ROW.replace("上海证券交易所 海澜之家 600398", "北京证券交易所 测试公司 430001")),
    (HEADER, ROW.replace("上海证券交易所 海澜之家 600398", "北京证券交易所 测试公司 830001")),
    (HEADER, ROW.replace("上海证券交易所 海澜之家 600398", "北京证券交易所 测试公司 920001")),
])
def test_exact_column_and_exchange_prefix(header, row):
    expected = row.split()[-2] if header == HEADER else row.split()[-1]
    assert codes(header+"\n"+row) == {expected}


@pytest.mark.parametrize("text", [
    "联系邮箱 600398@hla.com.cn",
    "目录 股票代码与股本情况 600398",
    "宣传 海澜之家 600398",
    ROW,
    "股票代码 股票简称 股票上市交易所 股票种类\n"+ROW,
    HEADER+"\nB股 上海证券交易所 测试公司 900001 旧名",
    HEADER+"\nH股 香港联合交易所 测试公司 060398 旧名",
    HEADER+"\n其他事项\n"+ROW,
])
def test_no_number_email_promotional_wrong_header_or_non_a_inference(text):
    assert codes(text) == set()


@pytest.mark.parametrize("row", [
    ROW.replace("上海证券交易所", "深圳证券交易所"),
    ROW.replace("上海证券交易所", "北京证券交易所"),
    ROW.replace("600398", "000398"),
    ROW.replace("600398", "600398@hla.com.cn"),
    "A股 海澜之家 上海证券交易所 600398 凯诺科技",
    "A股 上海证券交易所 600398 海澜之家 凯诺科技",
    ROW+" 多余列",
])
def test_wrong_columns_or_exchange_fail_closed(row):
    with pytest.raises(ValueError):
        codes(HEADER+"\n"+row)


@pytest.mark.parametrize("second", [ROW, ROW.replace("600398", "600519")])
def test_duplicate_or_conflicting_a_rows_and_tables_rejected(second):
    with pytest.raises(ValueError, match="MULTIPLE_A_SHARE"):
        codes(HEADER+"\n"+ROW+"\n"+second)
    with pytest.raises(ValueError, match="MULTIPLE_A_SHARE"):
        labelled_security_codes([HEADER+"\n"+ROW, HEADER+"\n"+second], symbol="600398")


def test_label_table_conflict_retains_all_codes_without_filtering_expected():
    assert codes("公司代码：600519\n"+HEADER+"\n"+ROW) == {"600519", "600398"}
    assert codes(HEADER+"\n"+ROW, symbol="600519") == {"600398"}


def test_table_does_not_stitch_pages_and_bounded_rows():
    assert labelled_security_codes([HEADER, ROW], symbol="600398") == set()
    non_a = "H股 香港联合交易所 测试公司 060398 旧名"
    with pytest.raises(ValueError, match="ROW_LIMIT"):
        codes(HEADER+"\n"+("\n".join([non_a]*3+[ROW])))


def test_real_600398_public_original_identity_not_pit():
    configured = os.environ.get("STOCK_IDENTITY_REAL_ROOT") or os.environ.get("OFFICIAL_FUNDING_REAL_ROOT")
    if not configured:
        if os.environ.get("STOCK_IDENTITY_REAL_REQUIRED") == "1":
            pytest.fail("STOCK_IDENTITY_REAL_ROOT required")
        pytest.skip("Explicit real public PDF root opt-in")
    root = Path(configured)
    path = root / "runtime/sse-value-research/sse-research-20261102T122836/queue-inputs/enrichment/600398-official-original/original.pdf"
    raw = path.read_bytes()
    stamp = path.stat().st_mtime_ns
    assert hashlib.sha256(raw).hexdigest() == "0e4c730ce906d8ebf9d2d33eacd848a25751050ecd6f077dcc16131f1c2a5a13"
    pages = extract_pages(path, limit=12)
    assert HEADER in pages[6] and ROW in pages[6]
    assert labelled_security_codes(pages, symbol="600398") == {"600398"}
    assert path.read_bytes() == raw and path.stat().st_mtime_ns == stamp


def test_five_column_header_allows_only_missing_trailing_former_name():
    assert codes(HEADER+"\nA股 上海证券交易所 海澜之家 600398") == {"600398"}


@pytest.mark.parametrize("row", [
    "A股 海澜之家 600398",
    "A股 上海证券交易所 600398",
    "A股 上海证券交易所 海澜之家",
    "A股 上海证券交易所 600398 凯诺科技",
    "A股 海澜之家 600398 凯诺科技",
    "A股 上海证券交易所 海澜之家 凯诺科技",
])
def test_missing_required_identity_column_cannot_use_trailing_name(row):
    with pytest.raises(ValueError):
        codes(HEADER+"\n"+row)


def test_missing_stock_type_is_not_an_identity_row():
    assert codes(HEADER+"\n上海证券交易所 海澜之家 600398 凯诺科技") == set()


@pytest.mark.parametrize("index,symbol,digest", [
    ("0", "600519", "474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288"),
    ("1", "600887", "d17b8c541c42f65d092317093eb0cfbb5aeed4f44eafa2d2f6182041cdcdbaac"),
])
def test_real_retained_annual_identity_compatibility(index, symbol, digest):
    configured = os.environ.get("STOCK_IDENTITY_REAL_ROOT") or os.environ.get("OFFICIAL_FUNDING_REAL_ROOT")
    if not configured:
        if os.environ.get("STOCK_IDENTITY_REAL_REQUIRED") == "1":
            pytest.fail("STOCK_IDENTITY_REAL_ROOT required")
        pytest.skip("Explicit real public PDF root opt-in")
    path = Path(configured) / ("runtime/public-evidence/20261030-a-first/"+index+"/acquisition/original.pdf")
    raw, stamp = path.read_bytes(), path.stat().st_mtime_ns
    assert hashlib.sha256(raw).hexdigest() == digest
    pages = extract_pages(path, limit=12)
    assert labelled_security_codes(pages, symbol=symbol) == {symbol}
    if symbol == "600519":
        assert HEADER in pages[4]
        assert "A股 上海证券交易所 贵州茅台 600519" in pages[4]
    assert path.read_bytes() == raw and path.stat().st_mtime_ns == stamp
