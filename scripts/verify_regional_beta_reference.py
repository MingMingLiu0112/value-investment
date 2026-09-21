"""Recompute author workbook beta transformations from archived numeric cells."""
from datetime import datetime, timezone
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
import xlrd

ROOT=Path('D:/GPTProject/value-investment')
SOURCE=ROOT/'runtime/valuation-research/damodaran-regional-beta-20260909T120634559642Z'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest=json.loads((SOURCE/'manifest.json').read_text(encoding='utf-8'))
    results=[]
    for region, filename in [('China','betaChina.xls'),('Global','betaGlobal.xls')]:
        path=SOURCE/filename
        if sha(path)!=manifest['outputs'][filename]:
            raise ValueError('Original changed')
        book=xlrd.open_workbook(path)
        sheet=book.sheet_by_name('Industry Averages')
        if sheet.cell_type(0,1)!=xlrd.XL_CELL_DATE:
            raise ValueError('Update date is not a typed Excel date')
        update=xlrd.xldate_as_datetime(sheet.cell_value(0,1),book.datemode).date().isoformat()
        if update!='2026-01-05' or sheet.cell_value(2,5)!=region or sheet.cell_value(7,5)!='Marginal':
            raise ValueError('Date, region or tax convention changed')
        headers=[str(v).strip() for v in sheet.row_values(9)]
        if headers[2:8]!=['Beta','D/E Ratio','Effective Tax rate','Unlevered beta','Cash/Firm value','Unlevered beta corrected for cash']:
            raise ValueError('Header mapping changed')
        candidates=[i for i in range(sheet.nrows) if sheet.cell_value(i,0)=='Beverage (Alcoholic)']
        if len(candidates)!=1:
            raise ValueError('Sector identity ambiguous')
        row=candidates[0]
        beta,de,effective,unlevered,cash,corrected=[D(str(sheet.cell_value(row,c))) for c in range(2,8)]
        marginal=D(str(sheet.cell_value(8,5)))
        recomputed=beta/(1+(1-marginal)*de)
        recash=recomputed/(1-cash)
        if abs(recomputed-unlevered)>D('1e-12') or abs(recash-corrected)>D('1e-12'):
            raise ValueError('Published transformations do not reconcile')
        wrong=beta/(1+(1-effective)*de)/(1-cash)
        if abs(wrong-corrected)<D('1e-6'):
            raise ValueError('Tax-convention counterexample ineffective')
        results.append({'region':region,'date':update,'sheet':sheet.name,'excel_row':row+1,
            'firm_count':int(sheet.cell_value(row,1)),'marginal_tax':str(marginal),
            'effective_tax':str(effective),'levered_beta':str(beta),'debt_equity_ratio':str(de),
            'cash_fraction':str(cash),'unlevered_beta':str(unlevered),'cash_corrected_beta':str(corrected),
            'recomputed_cash_corrected_beta':str(recash),'effective_tax_misuse_result':str(wrong),
            'original_sha256':sha(path)})
    out=ROOT/'runtime/valuation-research'/('regional-beta-verified-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    payload={'results':results,'formula_checks_passed':True,'company_beta_approved':False,
        'interpretation':['Global and China samples overlap; no independent two-source claim.',
            'Do not average regional betas as a company estimate without sample and benchmark justification.',
            'Displayed global historical average header conflicts with adjacent year labels; not used.',
            'Data are author-calculated sector statistics, not measured Moutai operating beta.',
            'Original beta 0.8/1/1.2 sensitivity misses both observed global and China sector points; retain it only as an earlier experiment.']}
    (out/'evidence.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):sha(p) for p in [SOURCE/'betaChina.xls',SOURCE/'betaGlobal.xls',Path(__file__)]},
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'results':results}))


if __name__=='__main__':
    main()
