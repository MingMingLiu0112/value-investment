"""Verify original cumulative repurchase snapshots without inventing daily fills."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal as D
from pathlib import Path
import json
import re
from check_moutai_ttm_comparability import ROOT, sha, texts
from value_investment_agent.historical_asof import publication_date_upper_bound

BASE=ROOT/'runtime/company-research/600519-repurchase-progress-20260909T094654846950Z'
DATES={
    '1222472609':('2025-01-31','2025年1月'),
    '1222706937':('2025-02-28','截至2025年2月底'),
    '1222993918':('2025-03-31','截至2025年3月底'),
    '1223023904':('2025-04-07','截至2025年4月7日'),
    '1223490954':('2025-04-30','截至2025年4月底'),
    '1223569076':('2025-05-16','截至2025年5月16日'),
    '1223765024':('2025-05-31','截至2025年5月底'),
    '1224067388':('2025-06-30','截至2025年6月底'),
    '1224387017':('2025-07-31','截至2025年7月底'),
}


def main():
    manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    result=[]
    for entry in manifest:
        aid=entry['row']['announcementId']; pdf=BASE/(aid+'.pdf')
        if entry['status']!='archived_not_field_verified' or sha(pdf)!=entry['sha256']:
            raise ValueError('Original mismatch')
        if sha(ROOT/entry['index'])!=entry['index_sha256']:
            raise ValueError('Archived index changed')
        header=texts(pdf,1); body=texts(pdf,2)
        extracted=[]
        for text in header:
            shares=re.findall(r'累计已回购股数([\d,]+)股',text)
            money=re.findall(r'累计已回购金额([\d,.]+)元',text)
            if len(shares)!=1 or len(money)!=1:
                raise ValueError('Ambiguous cumulative table')
            extracted.append((shares[0],money[0]))
        if extracted[0]!=extracted[1]:
            raise ValueError('Decoder disagreement')
        cutoff,phrase=DATES[aid]
        count,amount=extracted[0]
        if any(phrase not in text or count+'股' not in text or amount+'元' not in text for text in body):
            raise ValueError('Body does not corroborate cumulative table and date')
        published=datetime.fromtimestamp(entry['row']['announcementTime']/1000,timezone(timedelta(hours=8))).date().isoformat()
        if published not in entry['row']['adjunctUrl'] or published<=cutoff:
            raise ValueError('Invalid publication chronology')
        result.append({'source_id':'cninfo:'+aid,'statistical_cutoff':cutoff,'published_date':published,
            'available_at':publication_date_upper_bound(published).isoformat(),
            'cumulative_shares':int(count.replace(',','')),'cumulative_cash_excluding_fees':amount.replace(',',''),
            'source_url':entry['url'],'source_sha256':entry['sha256'],
            'index_path':entry['index'],'index_sha256':entry['index_sha256'],
            'physical_pages':[1,2],'date_phrase':phrase})
    result.sort(key=lambda r:r['statistical_cutoff'])
    if len(result)!=9:
        raise ValueError('Snapshot inventory changed')
    previous=None
    for row in result:
        row['increment_from_previous_snapshot']=None
        if previous:
            shares=row['cumulative_shares']-previous['cumulative_shares']
            cash=D(row['cumulative_cash_excluding_fees'])-D(previous['cumulative_cash_excluding_fees'])
            if shares<0 or cash<0:
                raise ValueError('Unexpected cumulative reversal')
            row['increment_from_previous_snapshot']={'shares':shares,'cash_excluding_fees':str(cash)}
        previous=row
    out=ROOT/'runtime/strategy-validation'/('moutai-repurchase-snapshots-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    data={'snapshots':result,'daily_execution_known':False,'strategy_approved':False,
        'limitations':['Cumulative snapshots overlap and must not be summed.',
            'Adjacent snapshot differences are interval totals, not daily company fills.',
            'Available only after conservative publication bound; never backfill cutoff day.',
            'Excludes transaction costs; not exactly the treasury-stock accounting carrying amount.',
            'Does not cover January first-buy disclosure, August completion or the second repurchase program.']}
    (out/'evidence.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':sha(Path(__file__)),
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'verified_snapshots':len(result),'last_cutoff':result[-1]['statistical_cutoff']}))


if __name__=='__main__':
    main()
