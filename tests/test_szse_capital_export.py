from datetime import date, datetime, timezone
import json

from openpyxl import Workbook
import pytest

from value_investment_agent.infrastructure.filings.szse_capital_export import replay_szse_capital_export


@pytest.mark.parametrize("catalog_date, expected_error", [
    ("2026-11-20", None),
    ("2026-11-19", "SZSE_CAPITAL_EXPORT_CATALOG_MISMATCH"),
])
def test_szse_paired_catalog_keeps_exact_export_shares(tmp_path, catalog_date, expected_error):
    symbol = "000568"
    base = "https://www.szse.cn/api/report/ShowReport"
    query = "&CATALOGID=1110&TABKEY=tab1&txtDMorJC=000568"
    capture = "2026-11-20T12:42:23Z"
    receipt = {
        "symbol": symbol, "catalog": "1110", "action": "no_order",
        "catalog_metadata_date": "2026-11-20",
        "sources": [
            {"path": "catalog.json", "sha256": "test-catalog", "saved_at": capture,
             "source_url": f"{base}/data?SHOWTYPE=JSON{query}"},
            {"path": "export.xlsx", "sha256": "test-export", "saved_at": capture,
             "source_url": f"{base}/?SHOWTYPE=xlsx{query}"},
        ],
    }
    (tmp_path / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    catalog = [{
        "metadata": {"tabkey": "tab1", "catalogid": "1110", "subname": catalog_date,
                     "cols": {"agzgb": "A股总股本<br>（亿股）"}},
        "data": [{"agdm": symbol, "agzgb": "14.71"}],
    }]
    (tmp_path / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "A股列表"
    sheet["E1"], sheet["H1"] = "A股代码", "A股总股本"
    sheet["E2"], sheet["H2"] = symbol, "1,471,901,463"
    workbook.save(tmp_path / "export.xlsx")
    kwargs = dict(binding={"path": "receipt.json"}, symbol=symbol, comparison_date=date(2026, 11, 20),
                  now=datetime(2026, 11, 20, 13, tzinfo=timezone.utc),
                  read=lambda binding: tmp_path / binding["path"])
    if expected_error:
        with pytest.raises(ValueError, match=expected_error):
            replay_szse_capital_export(**kwargs)
    else:
        result = replay_szse_capital_export(**kwargs)
        assert result["ordinary_a_shares"] == "1471901463"
        assert result["action"] == "no_order"
