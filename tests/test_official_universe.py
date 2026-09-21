from io import BytesIO
import json
from zipfile import ZipFile, ZIP_DEFLATED

from openpyxl import Workbook
import pytest

from value_investment_agent.official_universe import parse_szse, parse_sse, parse_bse_page, reconcile_security_lists


def test_szse_reads_past_wrong_a1_dimension():
    wb = Workbook()
    wb.active.append(['板块','A股代码','A股简称','A股上市日期'])
    wb.active.append(['创业板','302132','中航成飞','2010-08-27'])
    raw = BytesIO(); wb.save(raw)
    broken = BytesIO()
    with ZipFile(raw) as original, ZipFile(broken,'w',ZIP_DEFLATED) as edited:
        for item in original.infolist():
            data = original.read(item.filename)
            if item.filename == 'xl/worksheets/sheet1.xml':
                data = data.replace(b'ref="A1:D2"',b'ref="A1"')
            edited.writestr(item,data)
    rows = parse_szse(broken.getvalue())
    assert len(rows) == 1
    assert rows[0]['symbol'] == '302132'
    assert rows[0]['board'] == '创业板'


def test_sse_requires_declared_full_count_and_marks_cdr():
    data = {'result':[{'A_STOCK_CODE':'689009','SEC_NAME_CN':'九号公司','LIST_DATE':'20201029'}],
            'pageHelp':{'total':1}}
    assert parse_sse(json.dumps(data).encode(),'科创板')[0]['security_type'] == '境内存托凭证'
    data['pageHelp']['total'] = 2
    with pytest.raises(ValueError,match='incomplete'):
        parse_sse(json.dumps(data).encode(),'科创板')


def test_bse_callback_is_json_not_executed_code():
    raw = b'null([{"content":[],"numberOfElements":0}])'
    assert parse_bse_page(raw)['content'] == []
    with pytest.raises((ValueError,KeyError)):
        parse_bse_page(b'evil([{"content":[],"numberOfElements":0}])')
    with pytest.raises(ValueError,match='count'):
        parse_bse_page(b'null([{"content":[],"numberOfElements":1}])')


def sample():
    rows = [{'symbol':'600001','name':'样例','board':'主板'}]
    official = {'complete':True,'records':rows,'fetched_at':'2026-09-07T01:00:00+00:00','scope':'test','sources':[]}
    market = {'fetched_at':'2026-09-07T08:00:00+00:00','coverage':{'decisions':[dict(r) for r in rows]}}
    return official,market


def test_reconciliation_requires_same_date_codes_and_boards():
    official,market = sample()
    assert reconcile_security_lists(official,market)['reconciled']
    market['coverage']['decisions'][0]['board'] = '创业板'
    assert not reconcile_security_lists(official,market)['reconciled']
    market['fetched_at'] = '2026-09-08T01:00:00+00:00'
    assert reconcile_security_lists(official,market)['status'] == 'different_dates'


def test_reconciliation_exposes_missing_extra_and_duplicate_codes():
    official,market = sample()
    market['coverage']['decisions'][0]['symbol'] = '600002'
    result = reconcile_security_lists(official,market)
    assert result['missing_in_market'][0]['symbol'] == '600001'
    assert result['not_in_official'][0]['symbol'] == '600002'
    assert result['coverage_ratio'] == 0
    official['records'] *= 2
    with pytest.raises(ValueError,match='Duplicate'):
        reconcile_security_lists(official,market)
