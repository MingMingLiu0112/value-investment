"""Reconcile original parent equity and cancellation accounting, not daily fair value."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts


def main():
    source=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    expected='0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6'
    if sha(source)!=expected:
        raise ValueError('Original changed')
    checks={37:['44,528,418,839.89','-2,880,061,147.37','-35,032,574,305.20',
                '244,637,811,032.18','251,253,594,419.50'],
            72:['股票回购120,112,601.532,880,061,147.373,000,173,748.90'],
            73:['应付普通股股利35,032,574,305.2064,671,799,277.95',
                '期末未分配利润199,683,216,816.20191,905,148,832.21',
                '法定盈余公积50,543,176,610.941,706,238,132.672,997,985,134.9049,251,429,608.71']}
    for page,phrases in checks.items():
        pair=texts(source,page)
        for phrase in phrases:
            if any(phrase not in text for text in pair):
                raise ValueError(f'Original mismatch p{page}: {phrase}')
    calculations={
        'parent_equity':(['244637811032.18','44528418839.89','-2880061147.37','-35032574305.20'],'251253594419.50'),
        'retained_earnings':(['191905148832.21','44516880421.86','-1706238132.67','-35032574305.20'],'199683216816.20'),
        'statutory_surplus':(['50543176610.94','1706238132.67','-2997985134.90'],'49251429608.71'),
        'treasury_carrying_value':(['120112601.53','2880061147.37','-3000173748.90'],'0'),
        'cancellation_equity_effect':(['-2188614','-2997985134.90','3000173748.90'],'0'),
    }
    output={}
    for name,(values,total) in calculations.items():
        actual=sum(map(D,values),D(0));independent=sum(map(Fraction,values),Fraction(0))
        if actual!=D(total) or independent!=Fraction(total):
            raise ValueError(f'Rollforward failed: {name}')
        output[name]={'signed_inputs':values,'sum':str(actual),'fraction_check_passed':True}
    result={'symbol':'600519','period':'2026H1','unit':'CNY','source_sha256':expected,
        'source_path':str(source.relative_to(ROOT)),
        'source_url':'https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF',
        'physical_page_checks':checks,'calculations':output,
        'valuation_treatment':['The reported closing parent equity already includes period dividends and treasury purchases.',
            'Cancellation transfers treasury cost into capital/surplus; it does not incur the purchase cost again.',
            'Statutory reserve transfer reduces retained earnings but does not itself reduce total parent equity.',
            'Reported dividend recognition is not proof of payment or a daily declaration date.',
            'Do not use this 2026 disclosure as a fact known in the 2015-2025 strategy window.'],
        'daily_equity_bridge_approved':False,'valuation_approved':False}
    out=ROOT/'runtime/company-research'/('600519-equity-rollforward-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'source_sha256':expected,'script_sha256':sha(Path(__file__)),
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'reconciliations':len(output),'cancellation_incremental_equity_effect':output['cancellation_equity_effect']['sum']}))


if __name__=='__main__':
    main()
