from hashlib import sha256
from zipfile import ZipFile
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from value_investment_agent.workbook_compat import load_wps_workbook


def test_wps_nonstacked_chart_preserves_original_and_cells(tmp_path):
    source = tmp_path / 'source.xlsx'
    wps = tmp_path / 'wps.xlsx'
    wb = Workbook()
    wb.active.append(['manual note', 42])
    chart = BarChart()
    chart.add_data(Reference(wb.active, min_col=2, min_row=1))
    wb.active.add_chart(chart, 'D1')
    wb.save(source)
    with ZipFile(source) as src, ZipFile(wps, 'w') as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == 'xl/charts/chart1.xml':
                assert b'grouping val="clustered"' in data
                data = data.replace(b'grouping val="clustered"', b'grouping val="none"')
            dst.writestr(info, data)
    before = sha256(wps.read_bytes()).hexdigest()
    result = load_wps_workbook(wps)
    assert result.active['A1'].value == 'manual note'
    assert result.active['B1'].value == 42
    assert result.active._charts[0].grouping == 'standard'
    assert sha256(wps.read_bytes()).hexdigest() == before
